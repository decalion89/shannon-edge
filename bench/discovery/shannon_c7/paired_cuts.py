#!/usr/bin/env python3
"""Paired breaking rule observed in antipodal_cuts.py (two independent runs): coordinates {0,3} share an odd cut,
{2,4} share another, coordinate 1 has its own. 9 parameters. Best-improvement local search over the FULL
neighbourhood (each parameter +-1..+-4) with exact repair, with random restarts.
Usage: paired_cuts.py n a seconds seed"""
import sys
import time
import numpy as np
from overpack_repair import conflict_edges, mis

n, a, secs, seed = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
m = 5
groups = [0, 1, 2, 0, 2]  # coordinate -> cut group
rng = np.random.default_rng(seed)
g = np.array([pow(a, i, n) for i in range(m)])
W = (np.arange(n)[:, None] * g[None, :]) % n
X = np.where(W > n // 2, W - n, W)
cache = {}


def score(C):
    key = tuple(map(tuple, C))
    if key in cache:
        return cache[key]
    img = np.empty_like(X)
    for i in range(m):
        b0, b1, b2 = C[groups[i]]
        ax = np.abs(X[:, i])
        sym = np.where(ax <= b0, 0, np.where(ax <= b1, 1, np.where(ax <= b2, 2, 3)))
        img[:, i] = np.where(X[:, i] < 0, (-sym) % 7, sym)
    E = conflict_edges(img)
    s, _ = mis(n, E, time_limit=20)
    cache[key] = s
    return s


t0, best_overall = time.time(), 0
while time.time() - t0 < secs:
    C = np.array([[27, 80, 135]] * 3) + rng.integers(-3, 4, size=(3, 3))
    cur = score(C)
    improved = True
    while improved and time.time() - t0 < secs:
        improved = False
        best_move = (cur, None)
        for gi in range(3):
            for j in range(3):
                for d in (-4, -3, -2, -1, 1, 2, 3, 4):
                    T = C.copy(); T[gi, j] += d
                    if not all(0 <= T[k, 0] < T[k, 1] < T[k, 2] < n // 2 for k in range(3)):
                        continue
                    s = score(T)
                    if s > best_move[0]:
                        best_move = (s, T)
        if best_move[1] is not None:
            cur, C = best_move
            improved = True
    if cur > best_overall:
        best_overall = cur
        print(f"restart local optimum {cur}  cuts {C.tolist()}  [{time.time() - t0:.0f}s]", flush=True)
print(f"final best {best_overall}", flush=True)
