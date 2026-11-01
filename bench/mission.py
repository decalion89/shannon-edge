#!/usr/bin/env python3
"""How much information is there in a satellite's whole life?

Runs every channel of an ESA Anomaly Dataset mission (e.g. ESA-Mission1.zip,
CC BY 3.0 IGO, doi:10.5281/zenodo.12528696) through CCSDS 121.0-B (libaec)
and the sedge flight profile, in 256-sample packets, verifying every packet,
and reports per-channel and total sizes.

A lossless compressor's output is an upper bound on the information the data
contains (for that model), so the total is a verifiable upper bound on the
new information in the mission's telemetry values. Timestamps are not
included (values only), for every codec alike.

Channels are read straight from the mission zip, one at a time, through the
whitelist unpickler of bench/telemetry.py (no arbitrary code execution).
Values are coded as 16-bit ranks among each channel's distinct values, plus
the codebook (counted in every total). Channels with more than 65,536
distinct values are reported and skipped.

Usage:
    cargo build --release --example flight_bench
    pip install imagecodecs pandas numpy
    python3 bench/mission.py ESA-Mission1.zip [--table-bits 14]
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import imagecodecs
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from telemetry import SafeUnpickler  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PACKET = 256


def ccsds_size(codes: np.ndarray, bits: int) -> int:
    flags = imagecodecs.AEC.FLAG.DATA_PREPROCESS
    total = 0
    n = len(codes) // PACKET * PACKET
    for i in range(0, n, PACKET):
        p = codes[i:i + PACKET].tobytes()
        c = imagecodecs.aec_encode(p, bitspersample=bits, flags=flags, blocksize=16, rsi=128)
        back = imagecodecs.aec_decode(c, bitspersample=bits, flags=flags, blocksize=16, rsi=128, out=PACKET * 2)
        assert bytes(back) == p, "CCSDS round trip"
        total += len(c)
    tail = len(codes) - n
    if tail:
        total += tail * 2  # a final partial packet sent raw
    return total


def flight_size(codes: np.ndarray, table_bits: int) -> int:
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "codes.u16"
        codes.tofile(path)
        out = subprocess.run([str(ROOT / "target/release/examples/flight_bench"), str(path), "0", str(table_bits)],
                             check=True, capture_output=True, text=True).stdout
    return int(re.search(r"samples \(\d+-bit\), (\d+) bytes", out).group(1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mission_zip", type=Path)
    ap.add_argument("--table-bits", type=int, default=14)
    ap.add_argument("--only", nargs="*", help="channel names to run (default: all)")
    args = ap.parse_args()

    outer = zipfile.ZipFile(args.mission_zip)
    names = sorted((n for n in outer.namelist() if re.search(r"/channels/channel_\d+\.zip$", n)),
                   key=lambda n: int(re.search(r"(\d+)\.zip$", n).group(1)))
    rows, skipped = [], []
    print("| Channel | Samples | Distinct | float32 raw | CCSDS 121 | flight | flight % of raw |")
    print("|---|---:|---:|---:|---:|---:|---:|", flush=True)
    for name in names:
        ch = Path(name).stem
        if args.only and ch not in args.only:
            continue
        t = time.perf_counter()
        inner = zipfile.ZipFile(io.BytesIO(outer.read(name)))
        df = SafeUnpickler(io.BytesIO(inner.read(inner.namelist()[0]))).load()
        v = df.iloc[:, 0].to_numpy().astype(np.float32)
        del df
        uniq, codes = np.unique(v, return_inverse=True)
        if len(uniq) > 65536:
            skipped.append((ch, len(v), len(uniq)))
            print(f"| {ch} | {len(v):,} | {len(uniq):,} | skipped: more than 65,536 distinct values |||", flush=True)
            continue
        codes = codes.astype("<u2")
        bits = max(1, int(codes.max()).bit_length())
        raw = v.nbytes
        cc = ccsds_size(codes, 16) + uniq.nbytes
        fl = flight_size(codes, args.table_bits) + uniq.nbytes
        rows.append((ch, len(v), len(uniq), raw, cc, fl))
        print(f"| {ch} | {len(v):,} | {len(uniq):,} | {raw:,} | {cc:,} | {fl:,} | {100 * fl / raw:.3f}% |",
              flush=True)
        print(f"  {ch}: {bits}-bit codes, {time.perf_counter() - t:.0f}s", file=sys.stderr, flush=True)

    raw = sum(r[3] for r in rows)
    cc = sum(r[4] for r in rows)
    fl = sum(r[5] for r in rows)
    below = sum(1 for r in rows if r[5] < 0.01 * r[3])
    print()
    print(f"Channels: {len(rows)} measured, {len(skipped)} skipped; samples: {sum(r[1] for r in rows):,}")
    print(f"float32 raw:  {raw:,} bytes")
    print(f"CCSDS 121:    {cc:,} bytes ({100 * cc / raw:.3f}% of raw)")
    print(f"flight:       {fl:,} bytes ({100 * fl / raw:.3f}% of raw, {100 * (fl / cc - 1):+.1f}% vs CCSDS 121)")
    print(f"Channels below 1% of raw with flight: {below}/{len(rows)}")
    print("Every packet verified for both codecs (flight: by flight_bench).")


if __name__ == "__main__":
    main()
