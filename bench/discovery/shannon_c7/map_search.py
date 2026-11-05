#!/usr/bin/env python3
"""Arbitrary projections: per coordinate an ARBITRARY map phi_i: Z_n -> Z_7 (not only arc cuts), applied to the
over-packed cyclic set {t * g mod n}, followed by an exact maximum-independent-subset repair (MILP).
Local search on the maps: move = change phi_i(x) for one x (to a neighbouring or random symbol); accept if the
repaired size does not drop. Starts from arc cuts. Usage: map_search.py n a seconds seed save.npy
"""
import json
import sys
import time
import numpy as np
from overpack_repair import conflict_edges, mis

n, a, secs, seed, save = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
m = 5
rng = np.random.default_rng(seed)
g = np.array([pow(a, i, n) for i in range(m)])
W = (np.arange(n)[:, None] * g[None, :]) % n
cuts = [[52, 110, 160, 218, 268, 326, 379], [0, 56, 109, 164, 218, 272, 329], [1, 55, 110, 164, 218, 272, 328],
        [52, 109, 160, 217, 268, 325, 378], [3, 56, 111, 165, 219, 275, 329]]  # 365 for n=382, a=7 (round 2)
phi = np.zeros((m, n), dtype=int)
for i in range(m):
    c = np.sort(cuts[i])
    phi[i] = (np.searchsorted(c, np.arange(n), side="right") - 1) % 7


def score(phi_):
    img = np.stack([phi_[i][W[:, i]] for i in range(m)], axis=1)
    E = conflict_edges(img)
    s, x = mis(n, E, time_limit=30)
    return s, img[x]


best, S = score(phi)
print(f"start {best}", flush=True)
t0, it = time.time(), 0
while time.time() - t0 < secs:
    it += 1
    i, x = rng.integers(m), rng.integers(n)
    trial = phi.copy()
    trial[i, x] = (trial[i, x] + (rng.choice([-1, 1]) if rng.random() < 0.7 else rng.integers(1, 7))) % 7
    s, St = score(trial)
    if s >= best:
        if s > best:
            np.save(save, St)
            print(f"  improved: {s} at {time.time() - t0:.0f}s (iter {it})", flush=True)
        best, phi = s, trial
print(f"final {best} after {it} moves", flush=True)
json.dump(phi.tolist(), open(save.replace(".npy", "_phi.json"), "w"))
