#!/usr/bin/env python3
"""Ground-learned field relations: find fields that are an exact integer
function of two other fields, and remove them before compression.

    python3 bench/analysis/relations.py IN.bin LAYOUT.json OUT.bin [--learn-frac 0.1]

LAYOUT.json lists the record's fields as [name, numpy dtype] (as written by
the bench/general converters). On the first --learn-frac of the records
only (what the ground has already received), for every integer field k,
try r = x_k - floor((a*x_i + b*x_j) / 2) for pairs of other fields and a, b
in -4..4. The candidate kept is the one whose residual has the lowest
empirical entropy, if that is below 2 bits per sample. Targets are never
used as predictors, so decoding is ordered. The transform is exact and
reversible (mod 2^bits): the decoder recomputes floor(...) from fields it
already has. Writes the transformed file and prints the relations; --check
inverts it and verifies.
"""
import argparse
import json
import sys

import numpy as np


def entropy(v):
    _, c = np.unique(v, return_counts=True)
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("layout")
    ap.add_argument("out")
    ap.add_argument("--learn-frac", type=float, default=0.1)
    ap.add_argument("--max-bits", type=float, default=2.0)
    args = ap.parse_args()
    lay = json.load(open(args.layout))
    dt = np.dtype([(n, t) for n, t in lay["fields"]])
    rec = np.fromfile(args.inp, dtype=dt)
    ints = [n for n, t in lay["fields"] if np.dtype(t).kind in "iu"]
    learn = rec[: int(len(rec) * args.learn_frac)]
    L = {n: learn[n].astype(np.int64) for n in ints}
    rels, targets = [], set()
    order = sorted(ints, key=lambda n: -entropy(np.diff(L[n])))  # most expensive first
    for k in order:
        if any(k in (i, j) for _, i, j, *_ in rels):
            continue
        best = (entropy(np.diff(L[k])), None)
        pool = [n for n in ints if n != k and n not in targets]
        for ii, i in enumerate(pool):
            for j in pool[ii + 1:]:
                for a in range(-4, 5):
                    for b in range(-4, 5):
                        if a == 0 and b == 0:
                            continue
                        r = L[k] - ((a * L[i] + b * L[j]) >> 1)
                        h = entropy(r)
                        if h < best[0]:
                            best = (h, (i, j, a, b))
        if best[1] is not None and best[0] < args.max_bits:
            i, j, a, b = best[1]
            rels.append((k, i, j, a, b, best[0]))
            targets.add(k)
    out = rec.copy()
    for k, i, j, a, b, h in rels:
        bits = np.dtype(dt[k]).itemsize * 8
        r = rec[k].astype(np.int64) - ((a * rec[i].astype(np.int64) + b * rec[j].astype(np.int64)) >> 1)
        out[k] = (r % (1 << bits)).astype(np.uint64).astype(dt[k]) if dt[k].kind == "u" else \
            (((r + (1 << (bits - 1))) % (1 << bits)) - (1 << (bits - 1))).astype(dt[k])
        print(f"{k} = floor(({a}*{i} + {b}*{j})/2) + r   (residual entropy on learning part {h:.2f} bits)")
    # verify the inverse
    back = out.copy()
    for k, i, j, a, b, h in rels:
        bits = np.dtype(dt[k]).itemsize * 8
        x = out[k].astype(np.int64) + ((a * back[i].astype(np.int64) + b * back[j].astype(np.int64)) >> 1)
        back[k] = (((x + (1 << (bits - 1))) % (1 << bits)) - (1 << (bits - 1))).astype(dt[k]) if dt[k].kind == "i" else \
            (x % (1 << bits)).astype(dt[k])
    assert back.tobytes() == rec.tobytes(), "inverse transform failed"
    out.tofile(args.out)
    print(f"{len(rels)} relations; transform verified reversible on all {len(rec):,} records", file=sys.stderr)


if __name__ == "__main__":
    main()
