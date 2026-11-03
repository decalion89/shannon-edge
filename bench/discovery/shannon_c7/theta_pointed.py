#!/usr/bin/env python3
"""Pointed bound: alpha(G) = 1 + alpha(G - N[0]) for vertex-transitive G = C7^k. On H = G - N[0] (no translation
symmetry left), compute theta(H) with linear block constraints sum_{i in B cap H} (X e)_i <= c_B and quadratic
ones sum_{B x B} X <= c_B sum_B diag(X), for blocks B = {x,x+1}^s x C7^(k-s) (all positions/coordinates) with
c_B = alpha(C7^(k-s)) minus 1 if B contains vertex 0's... (we use c_B for B cap H, i.e. alpha of B restricted
to H, upper-bounded by alpha(C7^(k-s)) - [0 in B]: if 0 in B the point 0 is already in I and B cap I \\ {0}
lies in B - N[0]).
Usage: theta_pointed.py k alpha1 ... alpha_{k-1}
"""
import itertools
import sys
import numpy as np
import cvxpy as cp

k = int(sys.argv[1])
alph = {0: 1}
for j, a in enumerate(sys.argv[2:], start=1):
    alph[j] = int(a)
V = [v for v in itertools.product(range(7), repeat=k)]
close = lambda a, b: all(min((x - y) % 7, (y - x) % 7) <= 1 for x, y in zip(a, b))  # noqa: E731
H = [v for v in V if not close(v, (0,) * k)]
pos = {v: i for i, v in enumerate(H)}
nH = len(H)
X = cp.Variable((nH, nH), symmetric=True)
cons = [X >> 0, cp.trace(X) == 1, X >= 0]
for i, v in enumerate(H):
    for j in range(i + 1, nH):
        if close(v, H[j]):
            cons.append(X[i, j] == 0)
rowsum = cp.sum(X, axis=1)
nb = 0
for s in range(1, k):
    for S in itertools.combinations(range(k), s):
        for base in itertools.product(range(7), repeat=s):
            members = [pos[v] for v in H if all((v[S[t]] - base[t]) % 7 in (0, 1) for t in range(s))]
            if not members:
                continue
            zero_in = all((0 - base[t]) % 7 in (0, 1) for t in range(s))
            c = alph[k - s] - (1 if zero_in else 0)
            cons.append(cp.sum(rowsum[members]) <= c)
            cons.append(cp.sum(X[np.ix_(members, members)]) <= c * cp.sum(cp.diag(X)[members]))
            nb += 1
p = cp.Problem(cp.Maximize(cp.sum(X)), cons)
p.solve(solver="SCS", eps=1e-7, max_iters=200000)
print(f"k={k}: |H|={nH}, {nb} blocks; pointed bound alpha <= 1 + {p.value:.4f} = {1 + p.value:.4f}  ({p.status})")
