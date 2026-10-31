#!/usr/bin/env python3
"""Stream benchmark: a sedge Session vs zstd's best modes for record streams.

A stream of records sent one after another over one connection (webhooks,
telemetry, a device talking to a server). Both sides can remember earlier
records, so this compares:

* zstd -19 per record, without and with a trained dictionary
* zstd -19 in streaming mode with context kept across records ("context
  takeover", as in WebSocket permessage-deflate), flushed after every
  record so each one can be delivered immediately; without and with the
  trained dictionary
* sedge Session (keeps learning from every record), without and with
  sedge's own trained dictionary

Every record is decompressed and verified for all methods.

Usage:
    cargo build --release --example session_bench
    python3 bench/streams.py --records STREAM.jsonl --samples TRAIN.jsonl [--n 1000]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import zstandard

ROOT = Path(__file__).resolve().parent.parent


def zstd_stream(records: list[bytes], dict_data=None) -> int:
    params = zstandard.ZstdCompressionParameters.from_level(19)
    c = zstandard.ZstdCompressor(compression_params=params, dict_data=dict_data).compressobj()
    d = zstandard.ZstdDecompressor(dict_data=dict_data).decompressobj()
    total = 0
    for r in records:
        chunk = c.compress(r) + c.flush(zstandard.COMPRESSOBJ_FLUSH_BLOCK)
        total += len(chunk)
        assert d.decompress(chunk) == r
    return total


def zstd_each(records: list[bytes], dict_data=None) -> int:
    c = zstandard.ZstdCompressor(level=19, dict_data=dict_data)
    d = zstandard.ZstdDecompressor(dict_data=dict_data)
    total = 0
    for r in records:
        p = c.compress(r)
        assert d.decompress(p) == r
        total += len(p)
    return total


def sedge_session(binary: Path, records_path: Path, n: int, dict_path: Path | None) -> tuple[int, str]:
    cmd = [str(binary), str(records_path), str(n)] + ([str(dict_path)] if dict_path else [])
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    size = int(re.search(r"-> (\d+) bytes", out).group(1))
    return size, out.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", type=Path, required=True, help="stream: one record per line, in order")
    ap.add_argument("--samples", type=Path, required=True, help="earlier records to train dictionaries on")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--samples-n", type=int, default=5000)
    ap.add_argument("--budget", type=int, default=112_640)
    args = ap.parse_args()

    records = [l for l in args.records.read_bytes().split(b"\n") if l.strip()][: args.n]
    samples = [l for l in args.samples.read_bytes().split(b"\n") if l.strip()][-args.samples_n :]
    raw = sum(map(len, records))
    binary = ROOT / "target/release/examples/session_bench"
    sedge = ROOT / "target/release/sedge"
    for b in (binary, sedge):
        if not b.exists():
            sys.exit(f"missing {b}: run `cargo build --release --example session_bench`")

    t = time.perf_counter()
    zdict = zstandard.train_dictionary(args.budget, samples, level=19, threads=-1)
    print(f"zstd dictionary: {time.perf_counter() - t:.0f} s", file=sys.stderr)

    rows = [
        ("zstd -19, each record alone", zstd_each(records)),
        (f"zstd -19, each record alone + trained dict ({args.budget // 1024} KiB)", zstd_each(records, zdict)),
        ("zstd -19, streaming with context across records", zstd_stream(records)),
        ("zstd -19, streaming with context + trained dict", zstd_stream(records, zdict)),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        rec_path = Path(tmp) / "records.jsonl"
        rec_path.write_bytes(b"\n".join(records) + b"\n")
        size, info = sedge_session(binary, rec_path, len(records), None)
        print(f"sedge session: {info}", file=sys.stderr)
        rows.append(("**sedge session**", size))
        spath = Path(tmp) / "samples.jsonl"
        spath.write_bytes(b"\n".join(samples) + b"\n")
        dpath = Path(tmp) / "sedge.dict"
        subprocess.run([str(sedge), "train", str(spath), "--lines", "--budget", str(args.budget), "-o", str(dpath)],
                       check=True, capture_output=True)
        size, info = sedge_session(binary, rec_path, len(records), dpath)
        print(f"sedge session + dict: {info}", file=sys.stderr)
        rows.append((f"**sedge session + sedge-trained dict ({args.budget // 1024} KiB)**", size))

    best_zstd = min(size for name, size in rows if name.startswith("zstd"))
    print(f"| {len(records):,} records in order ({raw:,} bytes) | Total bytes | % of original | vs best zstd |")
    print("|---|---:|---:|---:|")
    for name, size in rows:
        print(f"| {name} | {size:,} | {100 * size / raw:.2f}% | {100 * (size / best_zstd - 1):+.1f}% |")
    print("\nEvery record decompressed and verified, for every method. sedge frames include a CRC-32 per record;"
          " zstd frames here carry no checksum.")


if __name__ == "__main__":
    main()
