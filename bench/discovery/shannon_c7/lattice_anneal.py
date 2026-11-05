#!/usr/bin/env python3
"""Search over ALL cyclic lattices: g in Z_n^m arbitrary. Independent set {t*g mod n} in C7^m (lossless via
phi(x) = floor(7x/n)) iff for every t != 0 some coordinate has circular distance >= k = ceil(2n/7).
Equivalently: the lattice Z^m + Z g/n has no nonzero point in the open cube (-k/n, k/n)^m mod 1.
Simulated annealing on the number of violating t. Usage: lattice_anneal.py m n seconds [seed]
"""
import sys
import time
import numpy as np

m, n, secs = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3])
seed = int(sys.argv[4]) if len(sys.argv) > 4 else 0
rng = np.random.default_rng(seed)
k = -(-2 * n // 7)
t = np.arange(1, n // 2 + 1, dtype=np.int64)


def near(gi):  # boolean over t: coordinate i is "close" (distance < k)
    r = (t * gi) % n
    return np.minimum(r, n - r) < k


g = rng.integers(1, n, size=m)
g[0] = 1
C = np.array([near(x) for x in g])
viol = C.all(axis=0).sum()
best, bestg = viol, g.copy()
T0, t_start = 2.0, time.time()
it = 0
while time.time() - t_start < secs and best > 0:
    it += 1
    i = rng.integers(1, m)  # keep g[0] = 1 (WLOG up to units when n prime; harmless otherwise)
    new = rng.integers(1, n)
    Ci = near(new)
    others = np.delete(C, i, axis=0).all(axis=0)
    nv = (others & Ci).sum()
    temp = T0 * (1 - (time.time() - t_start) / secs) + 1e-3
    if nv <= viol or rng.random() < np.exp((viol - nv) / temp):
        g[i], C[i], viol = new, Ci, nv
        if viol < best:
            best, bestg = viol, g.copy()
print(f"m={m} n={n} k={k} seed={seed}: best violations {best} after {it} moves; g={bestg.tolist()}", flush=True)
if best == 0:
    W = (np.arange(n)[:, None] * bestg[None, :]) % n
    img = (7 * W) // n
    # full pairwise check of independence in C7^m
    ok = True
    for a in range(n):
        d = (img - img[a]) % 7
        dist = np.minimum(d, 7 - d)
        good = (dist >= 2).any(axis=1)
        good[a] = True
        if not good.all():
            ok = False
            break
    print("VERIFIED independent set of size", n, "in C7^", m, ":", ok, "| alpha^(1/m) >=", n ** (1 / m))
