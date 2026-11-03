#!/usr/bin/env python3
"""Over-pack and repair, with the projection optimised: per coordinate, the circle Z_n is cut into 7 arcs
by 7 cut points (arc lengths free, not necessarily equal; uniform cuts with offset as start). Coordinate
descent on the cut points, exact MIS repair at every step. Usage: repair_search.py n a seconds seed [m]
"""
import sys
import time
import numpy as np
from overpack_repair import conflict_edges, mis

n, a, secs, seed = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
m = int(sys.argv[5]) if len(sys.argv) > 5 else 5
rng = np.random.default_rng(seed)
g = np.array([pow(a, i, n) for i in range(m)])
W = (np.arange(n)[:, None] * g[None, :]) % n


def project(cuts):  # cuts[i]: sorted 7 cut points in [0,n); symbol = index of arc containing x
    img = np.empty_like(W)
    for i in range(m):
        cpt = np.sort(cuts[i])
        img[:, i] = (np.searchsorted(cpt, W[:, i], side="right") - 1) % 7
    return img


def score(cuts):
    img = project(cuts)
    E = conflict_edges(img)
    s, _ = mis(n, E, time_limit=30)
    return s


cuts = [np.round(np.arange(7) * n / 7).astype(int) for _ in range(m)]
best = score(cuts)
print(f"m={m} n={n} a={a}: uniform cuts -> {best}", flush=True)
t0 = time.time()
while time.time() - t0 < secs:
    i, j = rng.integers(m), rng.integers(7)
    trial = [c.copy() for c in cuts]
    trial[i][j] = (trial[i][j] + rng.integers(-3, 4)) % n
    if len(set(trial[i])) < 7:
        continue
    s = score(trial)
    if s >= best:
        if s > best:
            print(f"  improved: {s} at {time.time() - t0:.0f}s", flush=True)
        best, cuts = s, trial
print(f"m={m} n={n} a={a} seed={seed}: best repaired size {best}; cuts={[sorted(c.tolist()) for c in cuts]}", flush=True)
