#!/usr/bin/env python3
"""Negacyclic-symmetric projections for the cyclic set {t * g mod n}, g = (1, a, ..., a^(m-1)), a^m = -1 (mod n).
All coordinates use the SAME cut, symmetric under x -> -x: symbol 0 on |x| <= b0, symbol 1 on b0 < x <= b1,
symbol 2 on b1 < x <= b2, symbol 3 on b2 < x <= n/2 (negatives -> 6, 5, 4). Then the projected set is invariant
under the rotate-and-negate symmetry. Exhaustive scan of (b0, b1, b2) near the uniform cut, exact repair.
Usage: symmetric_cuts.py m n a radius
"""
import sys
import numpy as np
from overpack_repair import conflict_edges, mis

m, n, a, rad = (int(x) for x in sys.argv[1:5])
g = np.array([pow(a, i, n) for i in range(m)])
W = (np.arange(n)[:, None] * g[None, :]) % n
X = np.where(W > n // 2, W - n, W)  # signed representative
u = n / 7
best = (0, None)
c0, c1, c2 = round(u / 2), round(1.5 * u), round(2.5 * u)
for b0 in range(c0 - rad, c0 + rad + 1):
    for b1 in range(c1 - rad, c1 + rad + 1):
        for b2 in range(c2 - rad, c2 + rad + 1):
            if not (0 <= b0 < b1 < b2 < n // 2):
                continue
            ax = np.abs(X)
            sym = np.where(ax <= b0, 0, np.where(ax <= b1, 1, np.where(ax <= b2, 2, 3)))
            img = np.where(X < 0, (-sym) % 7, sym)
            E = conflict_edges(img)
            if len(E) > n // 3:
                continue
            s, _ = mis(n, E, time_limit=20)
            if s > best[0]:
                best = (s, (b0, b1, b2))
                print(f"m={m} n={n} a={a}: cuts {best[1]} -> conflicts {len(E)}, repaired {s}", flush=True)
print("BEST", best, flush=True)
