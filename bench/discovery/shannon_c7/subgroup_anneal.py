#!/usr/bin/env python3
"""Independent sets in C7^m from subgroups of Z_N^m, N a multiple of 7 (lossless: k = 2N/7 exactly).
H = <g_1..g_r> subset Z_N^m is independent (after phi(x)=floor(7x/N)) iff every nonzero h in H has a coordinate
with circular distance >= 2N/7. Annealing on the generators: minimise W*violations - |H|.
Usage: subgroup_anneal.py m N r seconds seed
"""
import itertools
import sys
import time
import numpy as np

m, N, r, secs, seed = (int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]),
                       int(sys.argv[5]))
rng = np.random.default_rng(seed)
k = 2 * N // 7
assert N % 7 == 0
coef = np.array(list(itertools.product(range(N), repeat=r)), dtype=np.int64)  # N^r combinations


def evaluate(G):
    H = np.unique((coef @ G) % N, axis=0)
    D = np.minimum(H, N - H)
    nonzero = H.any(axis=1)
    viol = (nonzero & (D < k).all(axis=1)).sum()
    return viol, len(H)


W = 50
G = rng.integers(0, N, size=(r, m))
v, s = evaluate(G)
score = W * v - s
best = (np.inf, 0, None)
t0 = time.time()
while time.time() - t0 < secs:
    G2 = G.copy()
    i, j = rng.integers(r), rng.integers(m)
    G2[i, j] = rng.integers(N)
    v2, s2 = evaluate(G2)
    sc2 = W * v2 - s2
    temp = 30 * (1 - (time.time() - t0) / secs) + 0.5
    if sc2 <= score or rng.random() < np.exp((score - sc2) / temp):
        G, v, s, score = G2, v2, s2, sc2
        if v == 0 and s > best[1]:
            best = (0, s, G.copy())
print(f"m={m} N={N} r={r} seed={seed}: largest violation-free subgroup {best[1]} "
      f"(alpha^(1/m) >= {best[1] ** (1 / m) if best[1] else 0:.5f}); target to beat 367^(1/5)=3.25787",
      flush=True)
if best[2] is not None:
    print("generators:", best[2].tolist())
