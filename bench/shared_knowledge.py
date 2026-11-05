#!/usr/bin/env python3
"""Shared knowledge in practice: compress files with and without a dictionary.

If sender and receiver already share some data K, the cost of sending X drops
from H(X) towards the conditional information H(X | K). `sedge -D K` makes
that real: the model reads K before coding X, and K is never stored.

All sizes are real .sedge files (including the 8-byte dictionary id), and
every one is decompressed with the dictionary and verified bit-for-bit.

Usage:
    python3 bench/shared_knowledge.py --knowledge K1 [K2 ...] --targets X1 [X2 ...]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import brotli
except ImportError:  # pragma: no cover
    brotli = None


def sedge_size(binary: str, src: Path, tmp: Path, dict_path: Path | None) -> int:
    dst, back = tmp / "out.sedge", tmp / "back"
    extra = ["-D", str(dict_path)] if dict_path else []
    subprocess.run([binary, "compress", str(src), "-o", str(dst), "-f", *extra], check=True, capture_output=True)
    subprocess.run([binary, "decompress", str(dst), "-o", str(back), "-f", *extra], check=True, capture_output=True)
    if back.read_bytes() != src.read_bytes():
        sys.exit(f"ROUND-TRIP MISMATCH on {src}")
    return dst.stat().st_size


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--knowledge", nargs="+", type=Path, required=True)
    ap.add_argument("--targets", nargs="+", type=Path, required=True)
    ap.add_argument("--sedge", default=str(Path(__file__).resolve().parent.parent / "target/release/sedge"))
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        dict_path = tmp / "dict"
        dict_path.write_bytes(b"".join(p.read_bytes() for p in args.knowledge))
        size = dict_path.stat().st_size
        print(f"Dictionary: {size:,} bytes ({', '.join(p.name for p in args.knowledge)})\n")
        cols = ["File", "Original"] + (["brotli -11"] if brotli else []) + ["sedge", "sedge -D"]
        print("| " + " | ".join(cols) + " |")
        print("|---|" + "---:|" * (len(cols) - 1))
        for p in args.targets:
            row = [p.name, f"{p.stat().st_size:,}"]
            if brotli:
                row.append(f"{len(brotli.compress(p.read_bytes(), quality=11)):,}")
            row.append(f"{sedge_size(args.sedge, p, tmp, None):,}")
            row.append(f"**{sedge_size(args.sedge, p, tmp, dict_path):,}**")
            print("| " + " | ".join(row) + " |")
        print("\nEvery sedge result was decompressed and verified bit-for-bit.")


if __name__ == "__main__":
    main()
