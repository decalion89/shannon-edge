#!/usr/bin/env python3
"""Slab-capacity curve P_m(s): the largest independent set of C7^m whose layers 0 and 1 (along the last coordinate)
together contain exactly s points. alpha(C7^m) = max_s P_m(s); the classical layer bound ignores the trade-off.
Exact MILP (HiGHS via scipy), clique constraints of C7^m. Usage: slab_curve.py m s_min s_max [time_limit]
"""
import itertools
import sys
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
import scipy.sparse as sp

m, s_min, s_max = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
tl = float(sys.argv[4]) if len(sys.argv) > 4 else 600
V = np.array(list(itertools.product(range(7), repeat=m)))
w = 7 ** np.arange(m)[::-1]
code = lambda X: (np.asarray(X) % 7) @ w  # noqa: E731
E = np.array(list(itertools.product((0, 1), repeat=m)))
cl = [code(a + E) for a in V]
r = np.concatenate([np.full(len(q), i) for i, q in enumerate(cl)])
A = sp.csr_matrix((np.ones(len(r)), (r, np.concatenate(cl))), shape=(len(cl), len(V)))
slab = ((V[:, -1] == 0) | (V[:, -1] == 1)).astype(float)
for s in range(s_min, s_max + 1):
    cons = [LinearConstraint(A, -np.inf, 1), LinearConstraint(slab[None, :], s, s)]
    res = milp(c=-np.ones(len(V)), constraints=cons, integrality=np.ones(len(V)), bounds=Bounds(0, 1),
               options={"time_limit": tl})
    if res.status == 2:
        print(f"m={m} s={s}: infeasible (slab cannot hold {s})", flush=True)
        continue
    val = int(round(-res.fun)) if res.x is not None else None
    db = getattr(res, "mip_dual_bound", None)
    ok = "exact" if res.status == 0 else f"status {res.status}, bound {(-db if db is not None else float('nan')):.1f}"
    print(f"m={m} s={s}: P(s) = {val}  [{ok}]   rest = {val - s if val is not None else None}", flush=True)
