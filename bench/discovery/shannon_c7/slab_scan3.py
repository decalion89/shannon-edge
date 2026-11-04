#!/usr/bin/env python3
"""Exhaustive slab law check in C7^3: for every direction u (one per line through 0 in Z_7^3: 57 lines), the exact
maximum independent set inside the slab {x : <u,x> mod 7 in {0,1,2,3}} (196 points), HiGHS MILP to optimality."""
import itertools
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
import scipy.sparse as sp

m = 3
V = np.array(list(itertools.product(range(7), repeat=m)))
w = 7 ** np.arange(m)[::-1]
E = np.array(list(itertools.product((0, 1), repeat=m)))
lines, seen = [], set()
for u in itertools.product(range(7), repeat=m):
    if not any(u) or u in seen:
        continue
    for k in range(1, 7):
        seen.add(tuple((k * np.array(u)) % 7))
    lines.append(np.array(u))
res = []
for u in lines:
    S = V[((V @ u) % 7) <= 3]
    pos = {c: i for i, c in enumerate(S @ w)}
    rows = [[pos[c] for c in ((a + E) % 7) @ w if c in pos] for a in V]
    rows = [r for r in rows if len(r) > 1]
    r = np.concatenate([np.full(len(q), i) for i, q in enumerate(rows)])
    A = sp.csr_matrix((np.ones(len(r)), (r, np.concatenate(rows))), shape=(len(rows), len(S)))
    out = milp(c=-np.ones(len(S)), constraints=[LinearConstraint(A, -np.inf, 1)], integrality=np.ones(len(S)),
               bounds=Bounds(0, 1), options={"time_limit": 120})
    res.append((int(round(-out.fun)), tuple(u.tolist()), out.status))
res.sort(reverse=True)
vals = [r[0] for r in res]
print(f"{len(lines)} directions; max inside a slab: {max(vals)} (alpha(C7^3)=33); min {min(vals)}")
print("distribution:", {v: vals.count(v) for v in sorted(set(vals), reverse=True)})
print("directions reaching the max:", [r[1] for r in res if r[0] == max(vals)][:12], " all exact:", all(r[2] == 0 for r in res))
