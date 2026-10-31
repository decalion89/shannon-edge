#!/usr/bin/env python3
"""Small-message benchmark: sedge -M vs zstd with a trained dictionary.

Small records (API payloads, events, log lines) are where shared knowledge
matters most, and where the industry standard is zstd with a dictionary
trained on samples. This script compresses each test record *separately*,
the way a service would, and compares total sizes at equal knowledge
budgets:

* zstd -19 without and with a dictionary trained by zstd's own trainer
  (`zstandard.train_dictionary`, COVER) on the training records
* brotli -11 (has a built-in web/text dictionary)
* sedge without knowledge, and sedge -M with a model primed on the most
  recent training records, truncated to the same budget

Every sedge result is decompressed and verified (by `sedge bench`).

Usage:
    python3 bench/small_messages.py --train TRAIN.jsonl --test TEST.jsonl \\
        [--n 1000] [--budget 112640] [--seed 1] [--mem 22]

Input files hold one record per line (e.g. GH Archive hourly dumps).
"""

from __future__ import annotations

import argparse
import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import zstandard

try:
    import brotli
except ImportError:  # pragma: no cover
    brotli = None


def read_records(path: Path) -> list[bytes]:
    return [line for line in path.read_bytes().split(b"\n") if line.strip()]


def sedge_total(binary: str, files: list[Path], extra: list[str]) -> tuple[int, float]:
    """Total compressed size over files (verified by `sedge bench`), and seconds."""
    t = time.perf_counter()
    out = subprocess.run([binary, "bench", *map(str, files), *extra], check=True, capture_output=True, text=True).stdout
    secs = time.perf_counter() - t
    if "All files verified bit-for-bit." not in out:
        sys.exit("sedge verification failed")
    total = re.search(r"^TOTAL\s+(\d+)\s+(\d+)", out, re.M)
    return int(total.group(2)), secs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--test", type=Path, required=True)
    ap.add_argument("--n", type=int, default=1000, help="number of test records")
    ap.add_argument("--budget", type=int, default=112_640, help="knowledge budget in bytes (zstd default: 110 KiB)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--mem", type=int, default=22, help="sedge memory level for the primed model")
    ap.add_argument("--sedge", default=str(Path(__file__).resolve().parent.parent / "target/release/sedge"))
    args = ap.parse_args()

    train = read_records(args.train)
    test_all = read_records(args.test)
    rng = random.Random(args.seed)
    test = rng.sample(test_all, min(args.n, len(test_all)))
    raw = sum(map(len, test))
    print(f"train: {len(train):,} records from {args.train.name}; test: {len(test):,} records "
          f"({raw:,} bytes) from {args.test.name}; knowledge budget {args.budget:,} bytes\n", file=sys.stderr)

    rows = []

    # zstd without and with a trained dictionary (zstd's own COVER trainer).
    plain = zstandard.ZstdCompressor(level=19)
    rows.append(("zstd -19", sum(len(plain.compress(r)) for r in test)))
    # zstd recommends ~100x the dictionary size in samples; its parameter
    # search gets very slow far beyond that.
    samples = train[-5_000:]
    t = time.perf_counter()
    zdict = zstandard.train_dictionary(args.budget, samples, level=19, threads=-1)
    print(f"zstd dictionary trained in {time.perf_counter() - t:.1f}s ({len(zdict.as_bytes()):,} bytes)", file=sys.stderr)
    zc = zstandard.ZstdCompressor(level=19, dict_data=zdict)
    zd = zstandard.ZstdDecompressor(dict_data=zdict)
    total = 0
    for r in test:
        c = zc.compress(r)
        assert zd.decompress(c) == r
        total += len(c)
    rows.append((f"zstd -19 + trained dict ({args.budget // 1024} KiB)", total))

    if brotli is not None:
        rows.append(("brotli -11", sum(len(brotli.compress(r, quality=11)) for r in test)))

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        files = []
        for i, r in enumerate(test):
            f = tmp / f"m{i:05d}"
            f.write_bytes(r)
            files.append(f)
        size, secs = sedge_total(args.sedge, files, [])
        rows.append(("sedge", size))
        print(f"sedge (no knowledge): {secs:.1f}s", file=sys.stderr)

        # Knowledge for sedge: the most recent training records, same budget.
        know = bytearray()
        for r in reversed(train):
            if len(know) + len(r) + 1 > args.budget:
                break
            know[:0] = r + b"\n"
        kpath = tmp / "knowledge.jsonl"
        kpath.write_bytes(bytes(know))
        mpath = tmp / "knowledge.sedgem"
        subprocess.run([args.sedge, "prime", str(kpath), "-o", str(mpath), "-m", str(args.mem)], check=True,
                       capture_output=True)
        size, secs = sedge_total(args.sedge, files, ["-M", str(mpath)])
        rows.append((f"sedge -M ({len(know) // 1024} KiB of recent records)", size))
        print(f"sedge -M recent: {secs:.1f}s for {len(test)} records (compress + decompress + verify)",
              file=sys.stderr)

        # Same knowledge as zstd: prime sedge on zstd's own trained dictionary.
        zpath = tmp / "zstd.dict"
        zpath.write_bytes(zdict.as_bytes())
        zmodel = tmp / "zstd.sedgem"
        subprocess.run([args.sedge, "prime", str(zpath), "-o", str(zmodel), "-m", str(args.mem)], check=True,
                       capture_output=True)
        size, secs = sedge_total(args.sedge, files, ["-M", str(zmodel)])
        rows.append((f"**sedge -M (zstd's trained dict, {args.budget // 1024} KiB)**", size))
        print(f"sedge -M zstd-dict: {secs:.1f}s", file=sys.stderr)

    best_zstd = rows[1][1]
    print(f"| Compressor ({len(test):,} records compressed one by one) | Total bytes | % of original | vs zstd+dict |")
    print("|---|---:|---:|---:|")
    for name, size in rows:
        print(f"| {name} | {size:,} | {100 * size / raw:.2f}% | {100 * (size / best_zstd - 1):+.1f}% |")
    print(f"\nOriginal: {raw:,} bytes. Every sedge record was decompressed and verified bit-for-bit.")


if __name__ == "__main__":
    main()
