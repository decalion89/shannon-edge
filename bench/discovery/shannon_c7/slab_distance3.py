#!/usr/bin/env python3
"""Compression test in C7^3: for a maximum independent set A (33 points), how many points must change to obtain a maximum
set B lying inside some (1,1,3)-slab? For every direction u with |u| = (1,1,3) (12 up to overall sign) and every slab
offset c, solve exactly: maximise |A cap B| over independent B of size 33 inside {<u,x> - c in {0,1,2,3}}.
distance(A) = 33 - max overlap. Usage: slab_distance3.py set1.npy [...]"""
import itertools
import sys
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
import scipy.sparse as sp

m = 3
V = np.array(list(itertools.product(range(7), repeat=m)))
w = 7 ** np.arange(m)[::-1]
E = np.array(list(itertools.product((0, 1), repeat=m)))
dirs = set()
for perm in itertools.permutations([1, 1, 3]):
    for s in itertools.product((1, -1), repeat=3):
        v = tuple((np.array(perm) * np.array(s)) % 7)
        if tuple((-np.array(v)) % 7) not in dirs:
            dirs.add(v)
dirs = [np.array(d) for d in sorted(dirs)]
for f in sys.argv[1:]:
    A = np.load(f) % 7
    Acodes = set((A @ w).tolist())
    best = 0
    for u in dirs:
        for c in range(7):
            S = V[((V @ u - c) % 7) <= 3]
            codes = S @ w
            pos = {cd: i for i, cd in enumerate(codes)}
            rows = [[pos[cd] for cd in ((a + E) % 7) @ w if cd in pos] for a in V]
            rows = [r for r in rows if len(r) > 1]
            r = np.concatenate([np.full(len(q), i) for i, q in enumerate(rows)])
            M = sp.csr_matrix((np.ones(len(r)), (r, np.concatenate(rows))), shape=(len(rows), len(S)))
            obj = -np.array([1.0 if cd in Acodes else 0.0 for cd in codes])
            if -obj.sum() <= best:
                continue
            res = milp(c=obj, constraints=[LinearConstraint(M, -np.inf, 1), LinearConstraint(np.ones((1, len(S))), 33, 33)],
                       integrality=np.ones(len(S)), bounds=Bounds(0, 1), options={"time_limit": 30})
            if res.x is not None:
                best = max(best, int(round(-res.fun)))
    print(f"{f.split('/')[-1]}: max overlap with a slab-optimum = {best}  -> distance {33 - best}", flush=True)
