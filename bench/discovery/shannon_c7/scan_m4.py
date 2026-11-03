#!/usr/bin/env python3
"""m = 4: for every n in a range and every power generator a, uniform-cut repair; print top pairs."""
import sys
import numpy as np
from overpack_repair import conflict_edges, mis

m = 4
res = []
for n in range(int(sys.argv[1]), int(sys.argv[2]) + 1):
    for a in range(2, n):
        g = np.array([pow(a, i, n) for i in range(m)])
        if len(set(g.tolist())) < m:
            continue
        W = (np.arange(n)[:, None] * g[None, :]) % n
        img = (7 * W) // n
        E = conflict_edges(img)
        s, _ = mis(n, E, time_limit=10)
        res.append((s, n, a))
res.sort(reverse=True)
for s, n, a in res[:15]:
    print(f"m=4 n={n} a={a}: uniform-cut repaired {s}", flush=True)
