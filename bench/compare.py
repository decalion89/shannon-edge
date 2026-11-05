#!/usr/bin/env python3
"""Benchmark sedge against the standard compressors at their strongest settings.

Every sedge result is verified by decompressing and comparing bit-for-bit.

Usage:
    cargo build --release
    python3 bench/compare.py FILE [FILE ...] [--markdown results.md] [--sedge PATH]

Optional competitors are used when their Python modules are installed:
    pip install zstandard brotli
"""

from __future__ import annotations

import argparse
import bz2
import lzma
import os
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

try:
    import zstandard
except ImportError:  # pragma: no cover
    zstandard = None
try:
    import brotli
except ImportError:  # pragma: no cover
    brotli = None


def competitors():
    yield "gzip -9", lambda d: zlib.compress(d, 9)
    yield "bzip2 -9", lambda d: bz2.compress(d, 9)
    yield "xz -9e", lambda d: lzma.compress(d, preset=9 | lzma.PRESET_EXTREME)
    if zstandard is not None:
        yield "zstd -19", lambda d: zstandard.ZstdCompressor(level=19).compress(d)
    if brotli is not None:
        yield "brotli -11", lambda d: brotli.compress(d, quality=11, lgwin=24)


def run_sedge(binary: str, path: Path, mem: int | None) -> tuple[int, float, float]:
    """Compress and decompress with sedge; return (size, comp_s, decomp_s)."""
    with tempfile.TemporaryDirectory() as tmp:
        packed = Path(tmp) / "x.sedge"
        restored = Path(tmp) / "x.out"
        cmd = [binary, "compress", str(path), "-o", str(packed), "-f"]
        if mem is not None:
            cmd += ["-m", str(mem)]
        t = time.perf_counter()
        subprocess.run(cmd, check=True, capture_output=True)
        tc = time.perf_counter() - t
        t = time.perf_counter()
        subprocess.run(
            [binary, "decompress", str(packed), "-o", str(restored), "-f"],
            check=True,
            capture_output=True,
        )
        td = time.perf_counter() - t
        if restored.read_bytes() != path.read_bytes():
            sys.exit(f"ROUND-TRIP MISMATCH on {path}")
        return packed.stat().st_size, tc, td


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--sedge", default=str(Path(__file__).resolve().parent.parent / "target/release/sedge"))
    ap.add_argument("-m", "--mem", type=int, default=None, help="sedge memory level (16..24)")
    ap.add_argument("--markdown", type=Path, help="also write a Markdown table here")
    args = ap.parse_args()

    if not os.access(args.sedge, os.X_OK):
        sys.exit(f"sedge binary not found at {args.sedge} (run `cargo build --release`)")

    names = [n for n, _ in competitors()] + ["**sedge**"]
    rows = []
    totals = {n: 0 for n in names}
    total_in = 0
    speeds = []
    for path in args.files:
        data = path.read_bytes()
        total_in += len(data)
        sizes = {}
        for name, fn in competitors():
            sizes[name] = len(fn(data))
            print(f"  {path.name}: {name} done", file=sys.stderr)
        size, tc, td = run_sedge(args.sedge, path, args.mem)
        sizes["**sedge**"] = size
        speeds.append((path.name, len(data), tc, td))
        print(f"  {path.name}: sedge done ({tc:.1f}s / {td:.1f}s, verified)", file=sys.stderr)
        for n in names:
            totals[n] += sizes[n]
        rows.append((path.name, len(data), sizes))

    def fmt(sizes: dict, n: int) -> list[str]:
        best = min(sizes.values())
        cells = []
        for name in names:
            pct = 100.0 * sizes[name] / max(n, 1)
            cell = f"{sizes[name]:,} ({pct:.2f}%)"
            cells.append(f"**{cell}**" if sizes[name] == best else cell)
        return cells

    lines = ["| File | Original | " + " | ".join(names) + " |",
             "|---|---:|" + "---:|" * len(names)]
    for name, n, sizes in rows:
        lines.append(f"| {name} | {n:,} | " + " | ".join(fmt(sizes, n)) + " |")
    if len(rows) > 1:
        lines.append(f"| **Total** | {total_in:,} | " + " | ".join(fmt(totals, total_in)) + " |")
    lines += ["", "| File | sedge compress | sedge decompress |", "|---|---:|---:|"]
    for name, n, tc, td in speeds:
        mib = n / 1048576
        lines.append(f"| {name} | {mib / tc:.2f} MiB/s | {mib / td:.2f} MiB/s |")
    lines += ["", "Every sedge result above was decompressed and verified bit-for-bit."]

    table = "\n".join(lines)
    print(table)
    if args.markdown:
        args.markdown.write_text(table + "\n")


if __name__ == "__main__":
    main()
