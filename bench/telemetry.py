#!/usr/bin/env python3
"""Spacecraft telemetry benchmark: sedge vs CCSDS 121 (the space standard) and zstd.

Data: ESA Anomaly Dataset (ESA-AD), real telemetry from ESA missions,
https://doi.org/10.5281/zenodo.12528696, licence CC BY 3.0 IGO
(Kotowski et al., "European Space Agency Benchmark for Anomaly Detection in
Satellite Telemetry", arXiv:2406.17826). Download ESA-Mission1.zip and unzip
the channel files you want (each channel_N.zip holds one pickled DataFrame).

The channel files are pickles. Unpickling can run arbitrary code, so they are
loaded with a whitelist unpickler that only allows the pandas/numpy
reconstruction functions these files use; anything else is refused.

Each channel is sent as packets of consecutive samples, the way telemetry is
downlinked. Methods:

* CCSDS 121.0-B (libaec, via imagecodecs) with its unit-delay preprocessor,
  each packet independent (as flown)
* zstd -19 per packet, and zstd -19 streaming with context across packets
* sedge Session (learns across packets of the same channel), with full
  frames (sequence number + CRC-32 per packet) and lean frames (kind and
  length only; integrity left to the link layer, as for CCSDS 121)

Two sample representations are measured, both lossless:

* f32: the published float32 values (4 bytes per sample)
* codes: each value replaced by its rank among the channel's distinct values
  (uint16) plus the codebook of distinct values (counted in every total);
  this gives CCSDS 121 the integer samples it was designed for.

Every packet is decompressed and verified for every method.

Usage:
    cargo build --release
    pip install imagecodecs zstandard pandas numpy
    python3 bench/telemetry.py CHANNEL_FILE [CHANNEL_FILE ...] [--samples 1000000] [--packet 256]
"""

from __future__ import annotations

import argparse
import pickle
import sys
import time
from pathlib import Path

import imagecodecs
import numpy as np
import zstandard

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
import shannon_edge as se  # noqa: E402

ALLOWED = {
    ("numpy.core.multiarray", "_reconstruct"), ("numpy._core.multiarray", "_reconstruct"),
    ("numpy.core.numeric", "_frombuffer"), ("numpy._core.numeric", "_frombuffer"),
    ("numpy", "dtype"), ("numpy", "ndarray"), ("builtins", "slice"),
    ("pandas._libs.arrays", "__pyx_unpickle_NDArrayBacked"),
    ("pandas._libs.internals", "_unpickle_block"),
    ("pandas.core.arrays.datetimes", "DatetimeArray"),
    ("pandas.core.frame", "DataFrame"),
    ("pandas.core.indexes.base", "_new_Index"), ("pandas.core.indexes.base", "Index"),
    ("pandas.core.indexes.datetimes", "_new_DatetimeIndex"),
    ("pandas.core.indexes.datetimes", "DatetimeIndex"),
    ("pandas.core.internals.managers", "BlockManager"),
}


class SafeUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if (module, name) not in ALLOWED:
            raise pickle.UnpicklingError(f"refused to load {module}.{name}")
        if module.startswith("numpy.core"):
            module = module.replace("numpy.core", "numpy._core", 1)
        return super().find_class(module, name)


def load_channel(path: Path) -> np.ndarray:
    with open(path, "rb") as f:
        df = SafeUnpickler(f).load()
    return df.iloc[:, 0].to_numpy()


def ccsds(packets: list[bytes], bits: int) -> int:
    flags = imagecodecs.AEC.FLAG.DATA_PREPROCESS
    total = 0
    for p in packets:
        c = imagecodecs.aec_encode(p, bitspersample=bits, flags=flags, blocksize=16, rsi=128)
        n = len(p) * 8 // bits
        back = imagecodecs.aec_decode(c, bitspersample=bits, flags=flags, blocksize=16, rsi=128,
                                      out=n * (bits // 8))
        assert bytes(back) == p, "CCSDS round trip"
        total += len(c)
    return total


def zstd_each(packets: list[bytes]) -> int:
    c, d = zstandard.ZstdCompressor(level=19), zstandard.ZstdDecompressor()
    total = 0
    for p in packets:
        z = c.compress(p)
        assert d.decompress(z) == p
        total += len(z)
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


def sedge_session(packets: list[bytes], lean: bool = False) -> int:
    tx, rx = se.Session(lean=lean), se.Session(lean=lean)
    total = 0
    for p in packets:
        f = tx.compress(p)
        assert rx.decompress(f) == p
        total += len(f)
    return total


def run(name: str, data: bytes, sample_bytes: int, packet: int, extra: int, rows: list) -> None:
    step = packet * sample_bytes
    packets = [data[i:i + step] for i in range(0, len(data), step)]
    packets = [p for p in packets if len(p) == step]  # whole packets only
    raw = sum(map(len, packets))
    results = {}
    for label, fn in [("CCSDS 121", lambda: ccsds(packets, sample_bytes * 8)),
                      ("zstd -19 per packet", lambda: zstd_each(packets)),
                      ("zstd -19 stream", lambda: zstd_stream(packets)),
                      ("sedge session", lambda: sedge_session(packets)),
                      ("sedge session (lean)", lambda: sedge_session(packets, lean=True))]:
        t = time.perf_counter()
        results[label] = fn() + extra
        print(f"  {name} {label}: {results[label]:,} ({time.perf_counter() - t:.1f}s)", file=sys.stderr)
    rows.append((name, raw + extra, results))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("channels", nargs="+", type=Path)
    ap.add_argument("--samples", type=int, default=1_000_000)
    ap.add_argument("--packet", type=int, default=256, help="samples per packet")
    args = ap.parse_args()

    rows: list = []
    for path in args.channels:
        v = load_channel(path)[: args.samples]
        print(f"{path.name}: {len(v):,} samples, {len(np.unique(v)):,} distinct values", file=sys.stderr)
        f32 = np.ascontiguousarray(v.astype(np.float32))
        run(f"{path.name} f32", f32.tobytes(), 4, args.packet, 0, rows)
        uniq, codes = np.unique(f32, return_inverse=True)
        if len(uniq) <= 65536:
            run(f"{path.name} codes", codes.astype("<u2").tobytes(), 2, args.packet, uniq.nbytes, rows)

    names = ["CCSDS 121", "zstd -19 per packet", "zstd -19 stream", "sedge session", "sedge session (lean)"]
    print(f"| Channel, representation ({args.packet}-sample packets) | Raw | " + " | ".join(names) + " |")
    print("|---|---:|" + "---:|" * len(names))
    totals = {n: 0 for n in names}
    for name, raw, res in rows:
        best = min(res.values())
        cells = []
        for n in names:
            cell = f"{res[n]:,} ({100 * res[n] / raw:.1f}%)"
            cells.append(f"**{cell}**" if res[n] == best else cell)
            totals[n] += res[n]
        print(f"| {name} | {raw:,} | " + " | ".join(cells) + " |")
    print("\nEvery packet decompressed and verified for every method. 'codes' totals include the codebook.")


if __name__ == "__main__":
    main()
