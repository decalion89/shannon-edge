#!/usr/bin/env python3
"""sedge vs CCSDS 124.0-B-1 (POCKET+), the CCSDS standard for housekeeping
telemetry, on the real Venus Express packets of its public test vectors.

The CCSDS 124 numbers are not recomputed: they are the sizes of the
reference outputs shipped with the test vectors (generated with the ESA
reference implementation; github.com/tanagraspace/ccsds124, MIT), read from
`expected-output/<name>-metadata.json`. sedge compresses the same input,
packet by packet (each 90-byte packet coded as it arrives, as POCKET+ does),
and every packet is decompressed and verified.

Usage:
    cargo build --release
    git clone https://github.com/tanagraspace/ccsds124
    python3 bench/ccsds124.py ccsds124/test-vectors [--vector venus-express]
"""

from __future__ import annotations

import argparse
import json
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("vectors", type=Path, help="ccsds124/test-vectors directory")
    ap.add_argument("--vector", default="venus-express")
    args = ap.parse_args()

    meta = json.loads((args.vectors / "expected-output" / f"{args.vector}-metadata.json").read_text())
    inp = next(p for p in (args.vectors / "input").iterdir() if p.name.startswith(args.vector))
    data = inp.read_bytes()
    assert len(data) == meta["input"]["size"]
    plen = meta["compression"]["packet_length"]
    params = meta["compression"]["parameters"]
    packets = [data[i:i + plen] for i in range(0, len(data), plen)]
    ref = meta["output"]["compressed"]["size"]

    rows = [(f"CCSDS 124.0-B-1 / POCKET+ (ESA reference output, R={params['robustness']})", ref)]
    t = time.perf_counter()
    rows.append(("zstd -19, streaming, flushed per packet", zstd_stream(packets)))
    rows.append(("sedge lean session", session_total(packets)))
    rows.append((f"**sedge lean session, record model ({plen}-byte packets)**",
                 session_total(packets, record_len=plen)))
    print(f"{len(packets):,} packets of {plen} bytes ({len(data):,} bytes), {time.perf_counter() - t:.0f}s",
          file=sys.stderr)

    print(f"| {args.vector}: {len(packets):,} × {plen}-byte packets, coded packet by packet | Bytes | Ratio | vs CCSDS 124 |")
    print("|---|---:|---:|---:|")
    for name, size in rows:
        print(f"| {name} | {size:,} | {len(data) / size:.2f}× | {100 * (size / ref - 1):+.1f}% |")
    print(f"\nWhole-file references (not packet by packet): xz -9e {len(lzma.compress(data, preset=9 | lzma.PRESET_EXTREME)):,}"
          f", sedge (record length auto-detected) {len(se.compress(data)):,} bytes.")
    print("Every sedge and zstd packet decompressed and verified; CCSDS 124 size from the reference output.")


if __name__ == "__main__":
    main()
