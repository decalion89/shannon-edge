#!/usr/bin/env python3
"""Partial symmetry breaking: keep only the antipodal symmetry -I of the negacyclic structure.
Each coordinate i has its own ODD cut (phi_i(-x) = -phi_i(x)) given by (b0_i, b1_i, b2_i); 15 parameters for m=5.
The cyclic set is antipodal ({t g} = {-t g}), so the projection is -I invariant. Local search with exact repair.
Usage: antipodal_cuts.py n a seconds seed b0 b1 b2
"""
import sys
import time
import numpy as np
from overpack_repair import conflict_edges, mis

n, a, secs, seed = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
start = [int(x) for x in sys.argv[5:8]]
m = 5
rng = np.random.default_rng(seed)
g = np.array([pow(a, i, n) for i in range(m)])
W = (np.arange(n)[:, None] * g[None, :]) % n
X = np.where(W > n // 2, W - n, W)


def score(B):
    img = np.empty_like(X)
    for i in range(m):
        b0, b1, b2 = B[i]
        ax = np.abs(X[:, i])
        sym = np.where(ax <= b0, 0, np.where(ax <= b1, 1, np.where(ax <= b2, 2, 3)))
        img[:, i] = np.where(X[:, i] < 0, (-sym) % 7, sym)
    E = conflict_edges(img)
    s, x = mis(n, E, time_limit=20)
    return s, img[x]


B = np.array([start] * m)
best, S = score(B)
print(f"start {best}", flush=True)
t0 = time.time()
while time.time() - t0 < secs:
    T = B.copy()
    i, j = rng.integers(m), rng.integers(3)
    T[i, j] += rng.choice([-3, -2, -1, 1, 2, 3])
    if not (0 <= T[i, 0] < T[i, 1] < T[i, 2] < n // 2):
        continue
    s, St = score(T)
    if s >= best:
        if s > best:
            np.save(f"/tmp/claude-0/-home-user/f5214594-0f71-5d98-9550-f6c6aba4b49e/scratchpad/antipodal_{n}_{seed}.npy", St)
            print(f"  improved: {s} at {time.time() - t0:.0f}s  cuts {T.tolist()}", flush=True)
        best, B = s, T
print(f"final {best}  cuts {B.tolist()}", flush=True)
