#!/usr/bin/env python3
"""Preliminary experiment: how much does shared knowledge lower the cost?

If sender and receiver already share some data K, the cost of sending X is
the conditional information H(X | K), which can be far below H(X). We estimate
it with sedge itself:

    cost(X | K)  ≈  size(sedge(K + X)) - size(sedge(K))

This is an upper-bound style estimate from an adaptive model primed on K, not
a finished feature: real "knowledge packs" are Phase 3 of the roadmap.

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


def sedge_size(binary: str, data: bytes, tmp: Path) -> int:
    src, dst = tmp / "in", tmp / "out.sedge"
    src.write_bytes(data)
    subprocess.run([binary, "compress", str(src), "-o", str(dst), "-f"], check=True, capture_output=True)
    # Verify the round trip as everywhere else in this project.
    back = tmp / "back"
    subprocess.run([binary, "decompress", str(dst), "-o", str(back), "-f"], check=True, capture_output=True)
    if back.read_bytes() != data:
        sys.exit("ROUND-TRIP MISMATCH")
    return dst.stat().st_size


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--knowledge", nargs="+", type=Path, required=True)
    ap.add_argument("--targets", nargs="+", type=Path, required=True)
    ap.add_argument("--sedge", default=str(Path(__file__).resolve().parent.parent / "target/release/sedge"))
    args = ap.parse_args()

    knowledge = b"".join(p.read_bytes() for p in args.knowledge)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        base = sedge_size(args.sedge, knowledge, tmp)
        print(f"Shared knowledge K: {len(knowledge):,} bytes ({', '.join(p.name for p in args.knowledge)})\n")
        cols = ["File", "Original"] + (["brotli -11"] if brotli else []) + ["sedge", "sedge given K"]
        print("| " + " | ".join(cols) + " |")
        print("|---|" + "---:|" * (len(cols) - 1))
        for p in args.targets:
            x = p.read_bytes()
            alone = sedge_size(args.sedge, x, tmp)
            given = sedge_size(args.sedge, knowledge + x, tmp) - base
            row = [p.name, f"{len(x):,}"]
            if brotli:
                row.append(f"{len(brotli.compress(x, quality=11)):,}")
            row += [f"{alone:,}", f"**{given:,}**"]
            print("| " + " | ".join(row) + " |")


if __name__ == "__main__":
    main()
