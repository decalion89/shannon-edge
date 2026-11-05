#!/usr/bin/env python3
"""sedge vs CCSDS 124.0-B-1 (POCKET+), the CCSDS standard for housekeeping
telemetry, on the real Venus Express packets of its public test vectors.

The CCSDS 124 numbers are not recomputed: they are the sizes of the
reference outputs shipped with the test vectors (generated with the ESA
reference implementation; github.com/tanagraspace/ccsds124, MIT), read from
`expected-output/<name>-metadata.json`. sedge compresses the same input,
packet by packet (each 90-byte packet coded as it arrives, as POCKET+ does),
and every packet is decompressed and verified.

With --cli (the CLI built from that repository's C implementation), the
script also sweeps CCSDS 124 parameters (robustness R=0..2, mask/full/reset
periods) and reports its best configuration, verifying the round trip, so
the comparison does not rest on the test vector's default settings.

Usage:
    cargo build --release --example packet_bench
    git clone https://github.com/tanagraspace/ccsds124
    python3 bench/ccsds124.py ccsds124/test-vectors [--vector venus-express]
        [--cli ccsds124/implementations/c/build/ccsds124]
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import subprocess
import tempfile
import lzma
import sys
import time
from pathlib import Path

import zstandard

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
import shannon_edge as se  # noqa: E402


def session_total(packets: list[bytes], **kw) -> int:
    tx, rx = se.Session(lean=True, **kw), se.Session(lean=True, **kw)
    total = 0
    for p in packets:
        f = tx.compress(p)
        assert rx.decompress(f) == p, "round trip"
        total += len(f)
    return total


def zstd_stream(packets: list[bytes]) -> int:
    c = zstandard.ZstdCompressor(level=19).compressobj()
    d = zstandard.ZstdDecompressor().decompressobj()
    total = 0
    for p in packets:
        z = c.compress(p) + c.flush(zstandard.COMPRESSOBJ_FLUSH_BLOCK)
        assert d.decompress(z) == p
        total += len(z)
    return total


def packet_profile(path: Path, plen: int, table_bits: int, v2: bool = False) -> tuple[int, float, float]:
    """Size, compress speed (MB/s) and memory (KiB) of the packet profile."""
    binary = Path(__file__).resolve().parent.parent / "target/release/examples/packet_bench"
    env = dict(os.environ, SEDGE_PACKET_V2="1") if v2 else {k: v for k, v in os.environ.items()
                                                              if k != "SEDGE_PACKET_V2"}
    out = subprocess.run([str(binary), str(path), str(plen), str(table_bits)], check=True,
                         capture_output=True, text=True, env=env).stdout
    return (int(re.search(r"-> (\d+) bytes", out).group(1)),
            float(re.search(r"compress ([\d.]+) MB/s", out).group(1)),
            float(re.search(r"memory (\d+) KiB", out).group(1)))


def ccsds124_best(cli: Path, data: bytes, plen: int) -> tuple[int, str, float]:
    """Smallest verified CCSDS 124 output over a parameter sweep."""
    best = (None, "", 0.0)
    with tempfile.TemporaryDirectory() as t:
        src = Path(t) / "in.bin"
        src.write_bytes(data)
        grid = itertools.product((0, 1, 2), (5, 10, 12, 14, 16, 20, 50), (50, 1000, 100000), (100, 100000, 1000000))
        for r, pt, ft, rt in grid:
            if not pt <= ft <= rt:
                continue
            t0 = time.perf_counter()
            res = subprocess.run([str(cli), str(src), str(plen), str(pt), str(ft), str(rt), str(r)], capture_output=True)
            secs = time.perf_counter() - t0
            if res.returncode != 0:
                continue
            size = (Path(t) / "in.bin.pkt").stat().st_size
            if best[0] is None or size < best[0]:
                best = (size, f"R={r}, pt={pt}, ft={ft}, rt={rt}", len(data) / secs / 1e6)
        r, pt, ft, rt = (int(v) for v in re.findall(r"\d+", best[1]))
        subprocess.run([str(cli), str(src), str(plen), str(pt), str(ft), str(rt), str(r)], check=True, capture_output=True)
        subprocess.run([str(cli), "-d", str(Path(t) / "in.bin.pkt"), str(plen), str(r)], check=True, capture_output=True)
        assert (Path(t) / "in.bin.depkt").read_bytes() == data, "CCSDS 124 round trip"
    return best


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vectors", type=Path, help="ccsds124/test-vectors directory")
    ap.add_argument("--vector", default="venus-express")
    ap.add_argument("--cli", type=Path, help="CCSDS 124 CLI for a parameter sweep (optional)")
    args = ap.parse_args()

    meta = json.loads((args.vectors / "expected-output" / f"{args.vector}-metadata.json").read_text())
    inp = next(p for p in (args.vectors / "input").iterdir() if p.name.startswith(args.vector))
    data = inp.read_bytes()
    assert len(data) == meta["input"]["size"]
    plen = meta["compression"]["packet_length"]
    params = meta["compression"]["parameters"]
    packets = [data[i:i + plen] for i in range(0, len(data), plen)]
    ref = meta["output"]["compressed"]["size"]

    rows = [(f"CCSDS 124.0-B-1 / POCKET+ (ESA reference output, R={params['robustness']}, "
             f"pt={params['pt']}, ft={params['ft']}, rt={params['rt']})", ref)]
    if args.cli:
        size, cfg, speed = ccsds124_best(args.cli, data, plen)
        rows.append((f"CCSDS 124, best of a parameter sweep ({cfg}; {speed:.0f} MB/s compress)", size))
        ref = size
    t = time.perf_counter()
    rows.append(("zstd -19, streaming, flushed per packet", zstd_stream(packets)))
    rows.append(("sedge lean session", session_total(packets)))
    rows.append((f"sedge lean session, record model ({plen}-byte packets)",
                 session_total(packets, record_len=plen)))
    for v2, tb in ((False, 14), (False, 18), (True, 12), (True, 18)):
        size, speed, mem = packet_profile(inp, plen, tb, v2)
        rows.append((f"**sedge packet profile {'v2' if v2 else 'v1'}, tables 2^{tb} "
                     f"({mem:,.0f} KiB; compress {speed:.1f} MB/s)**", size))
    print(f"{len(packets):,} packets of {plen} bytes ({len(data):,} bytes), {time.perf_counter() - t:.0f}s",
          file=sys.stderr)

    print(f"| {args.vector}: {len(packets):,} × {plen}-byte packets, coded packet by packet | Bytes | Ratio | "
          f"vs {'best ' if args.cli else ''}CCSDS 124 |")
    print("|---|---:|---:|---:|")
    for name, size in rows:
        print(f"| {name} | {size:,} | {len(data) / size:.2f}× | {100 * (size / ref - 1):+.1f}% |")
    print(f"\nWhole-file references (not packet by packet): xz -9e {len(lzma.compress(data, preset=9 | lzma.PRESET_EXTREME)):,}"
          f", sedge (record length auto-detected) {len(se.compress(data)):,} bytes.")
    print("Every sedge and zstd packet decompressed and verified. CCSDS 124: reference output size"
          + ("; best sweep configuration round-trip verified." if args.cli else "."))


if __name__ == "__main__":
    main()
