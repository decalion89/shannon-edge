#!/usr/bin/env python3
"""Where must a 109-set of C7^4 live? If all 7 adjacent-layer pairs had <= 31 points, |I| <= floor(7*31/2) = 108.
So a 109-set has two adjacent layers whose union J is an independent set of C7^3 with |J| >= 32.
Boundary-value search: take a 33-set J of C7^3, split it into layers I_0 (part S) and I_1 (rest), and solve EXACTLY
the maximum number of points in layers 2..6 (each layer independent, consecutive layers jointly independent,
layer 2 compatible with I_1 and layer 6 with I_0). Total = 33 + that. Local search over the split S.
Usage: boundary109.py J.npy seconds seed
"""
import itertools
import sys
import time
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
import scipy.sparse as sp

J = np.load(sys.argv[1]) % 7
secs, seed = float(sys.argv[2]), int(sys.argv[3])
rng = np.random.default_rng(seed)
V3 = np.array(list(itertools.product(range(7), repeat=3)))
w = np.array([49, 7, 1])
code = lambda X: (np.asarray(X) % 7) @ w  # noqa: E731
cliques = [code(a + np.array(list(itertools.product((0, 1), repeat=3)))) for a in V3]  # 343 cliques of size 8
offs = np.array(list(itertools.product((-1, 0, 1), repeat=3)))
L = 5  # layers 2..6 -> indices 0..4
nv = L * 343
rows = []
for x in range(L):
    for q in cliques:
        rows.append(x * 343 + q)                       # each layer independent
    if x + 1 < L:
        for q in cliques:
            rows.append(np.concatenate([x * 343 + q, (x + 1) * 343 + q]))  # consecutive layers jointly independent
r = np.concatenate([np.full(len(q), i) for i, q in enumerate(rows)])
A = sp.csr_matrix((np.ones(len(r)), (r, np.concatenate(rows))), shape=(len(rows), nv))
cons = LinearConstraint(A, -np.inf, 1)


def blocked(points):
    b = np.zeros(343, bool)
    if len(points):
        b[code((points[:, None, :] + offs[None, :, :]).reshape(-1, 3))] = True
    return b


def solve(S):
    I0, I1 = J[S], J[~S]
    ub = np.ones(nv)
    ub[0:343][blocked(I1)] = 0                 # layer 2 next to layer 1
    ub[(L - 1) * 343:][blocked(I0)] = 0        # layer 6 next to layer 0
    res = milp(c=-np.ones(nv), constraints=[cons], integrality=np.ones(nv), bounds=Bounds(0, ub),
               options={"time_limit": 120})
    return int(round(-res.fun)) if res.x is not None else -1


S = np.zeros(len(J), bool)
S[rng.choice(len(J), size=len(J) // 2, replace=False)] = True
cur = solve(S)
best = cur
print(f"|J|={len(J)}: start split {S.sum()}/{(~S).sum()} -> 5 layers hold {cur}, total {len(J) + cur} (need 109)",
      flush=True)
t0 = time.time()
while time.time() - t0 < secs:
    T = S.copy()
    i = rng.integers(len(J)); T[i] = ~T[i]
    if rng.random() < 0.5:
        j = rng.integers(len(J)); T[j] = ~T[j]
    v = solve(T)
    if v >= cur:
        S, cur = T, v
        if v > best:
            best = v
            print(f"  total {len(J) + v} at {time.time() - t0:.0f}s (split {S.sum()}/{(~S).sum()})", flush=True)
print(f"final best total {len(J) + best}", flush=True)
