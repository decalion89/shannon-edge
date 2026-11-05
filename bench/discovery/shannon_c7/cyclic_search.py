#!/usr/bin/env python3
"""Cyclic independent sets in strong powers of C7 (exploration).

S = { t*g mod n : t in Z_n } subset Z_n^m with g = (1, a, a^2, ..., a^(m-1)) mod n.
Map phi: Z_n -> Z_7, phi(x) = floor(7x/n). If two words differ in some coordinate by circular distance
>= k = ceil(2n/7), their images differ there by 2..5 mod 7, i.e. are distinguishable in C7. So if every
t != 0 has some coordinate with circular distance(t*g_i, 0) >= k, phi(S) is an independent set of size n in
C7^{boxtimes m} (phi is injective on S because coordinate 1 is t itself and phi is injective... not
necessarily: checked explicitly below).
Usage: cyclic_search.py m n_min n_max
"""
import sys
import numpy as np

m, n_min, n_max = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
best = None
for n in range(n_min, n_max + 1):
    k = -(-2 * n // 7)
    t = np.arange(1, n // 2 + 1, dtype=np.int64)
    found = []
    for a in range(2, n):
        g = [pow(a, i, n) for i in range(m)]
        ok = np.zeros_like(t, dtype=bool)
        for gi in g:
            r = (t * gi) % n
            ok |= np.minimum(r, n - r) >= k
            if ok.all():
                break
        if ok.all():
            found.append(a)
    if found:
        # explicit check: images distinct and pairwise distinguishable in C7^m (sample-based full check for small n)
        a = found[0]
        g = np.array([pow(a, i, n) for i in range(m)])
        W = (np.arange(n)[:, None] * g[None, :]) % n
        img = (7 * W) // n
        uniq = len({tuple(r) for r in img})
        print(f"m={m} n={n} k={k}: {len(found)} generators, e.g. a={a}; distinct images {uniq}; "
              f"bound alpha^(1/m) = {n ** (1 / m):.6f}", flush=True)
        best = n
print("largest n found:", best)
