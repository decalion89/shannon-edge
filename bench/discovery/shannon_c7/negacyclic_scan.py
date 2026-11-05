#!/usr/bin/env python3
"""Law-guided scan: only (n, a) with a^m = -1 (mod n) (negacyclic generator g = (1, a, ..., a^(m-1)): multiplying
the cyclic set by a rotates coordinates and flips one sign). Uniform cuts + exact repair; print best pairs.
Motivation: the C7^5 record (n=382, a=7) satisfies 7^5 = -1 mod 382; for m=6, n=905 (7^6 = -1 mod 905) repairs
818/905 while 7^6 = +1 moduli collapse. Usage: negacyclic_scan.py m n_min n_max top
"""
import sys
import numpy as np
from overpack_repair import conflict_edges, mis

m, n_min, n_max, top = (int(x) for x in sys.argv[1:5])
res = []
for n in range(n_min, n_max + 1):
    for a in range(2, n):
        if pow(a, m, n) != n - 1:
            continue
        g = np.array([pow(a, i, n) for i in range(m)])
        W = (np.arange(n)[:, None] * g[None, :]) % n
        img = (7 * W) // n
        E = conflict_edges(img)
        if len(E) > 2 * n:
            res.append((0, n, a, len(E)))
            continue
        s, _ = mis(n, E, time_limit=60)
        res.append((s, n, a, len(E)))
        print(f"m={m} n={n} a={a}: conflicts {len(E)}, repaired {s}", flush=True)
res.sort(reverse=True)
print("TOP:", res[:top], flush=True)
