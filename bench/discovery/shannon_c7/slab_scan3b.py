#!/usr/bin/env python3
"""Complete the C7^3 slab scan: one representative of each |u| class not covered by slab_scan3.py (which used one
vector per LINE, but rescaling changes the slab). Exact MILP per class."""
import itertools
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
import scipy.sparse as sp

m = 3
V = np.array(list(itertools.product(range(7), repeat=m)))
w = 7 ** np.arange(m)[::-1]
E = np.array(list(itertools.product((0, 1), repeat=m)))
for u in [(2, 2, 2), (0, 3, 3), (2, 3, 3), (0, 0, 3), (0, 2, 3), (2, 2, 3), (3, 3, 3), (0, 0, 2), (0, 2, 2)]:
    u = np.array(u)
    S = V[((V @ u) % 7) <= 3]
    pos = {c: i for i, c in enumerate(S @ w)}
    rows = [[pos[c] for c in ((a + E) % 7) @ w if c in pos] for a in V]
    rows = [r for r in rows if len(r) > 1]
    r = np.concatenate([np.full(len(q), i) for i, q in enumerate(rows)])
    A = sp.csr_matrix((np.ones(len(r)), (r, np.concatenate(rows))), shape=(len(rows), len(S)))
    out = milp(c=-np.ones(len(S)), constraints=[LinearConstraint(A, -np.inf, 1)], integrality=np.ones(len(S)),
               bounds=Bounds(0, 1), options={"time_limit": 300})
    print(f"|u| class {tuple(u.tolist())}: max in slab {int(round(-out.fun))} ({'exact' if out.status == 0 else 'time limit'})",
          flush=True)
