#!/usr/bin/env python3
"""Scan (n, a) with uniform cuts + exact repair; print every pair reaching >= threshold.
Usage: scan_na.py n_min n_max threshold"""
import sys
import numpy as np
from overpack_repair import conflict_edges, mis

n_min, n_max, thr = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
m = 5
for n in range(n_min, n_max + 1):
    best = (0, None)
    for a in range(2, n):
        g = np.array([pow(a, i, n) for i in range(m)])
        if len(set(g.tolist())) < m:
            continue
        W = (np.arange(n)[:, None] * g[None, :]) % n
        img = (7 * W) // n
        d0 = np.minimum(img, 7 - img)
        if ((d0 <= 1).all(axis=1).sum()) > n // 5:  # too many words near 0: hopeless, skip
            continue
        E = conflict_edges(img)
        if len(E) > 3 * n:
            continue
        s, _ = mis(n, E, time_limit=20)
        if s > best[0]:
            best = (s, a)
        if s >= thr:
            print(f"n={n} a={a}: uniform-cut repaired size {s} (conflicts {len(E)})", flush=True)
    print(f"# n={n}: best {best}", flush=True)
