#!/usr/bin/env python3
"""Lovasz theta of C7^k fused with block (layer) constraints, as an exact LP over translation- and
symmetry-invariant matrices X_ij = f(i - j).

For an independent set I and X = 1_I 1_I^T / |I|: tr X = 1, X_ij = 0 on edges, X psd, X >= 0, and for any
block B with alpha(G[B]) <= c:   sum_{i,j in B} X_ij = |B cap I|^2/|I| <= c |B cap I|/|I| = c sum_{i in B} X_ii.
Blocks used: products of {x, x+1} (s coordinates) and Z7 (k - s coordinates): alpha = alpha(C7^(k-s)).
Averaged over translations/permutations the constraint reads  sum_d f(d) c_B(d) <= c |B| f(0),
c_B(d) = prod_i c_i(d_i), with c_{x,x+1}(0)=2, (+-1)=1, else 0 and c_{Z7}(.) = 7.
Usage: theta_blocks.py k  alpha(C7^1) alpha(C7^2) ... alpha(C7^(k-1))   (exact values or valid upper bounds)
"""
import itertools
import sys
import numpy as np
from scipy.optimize import linprog

k = int(sys.argv[1])
alph = {0: 1}
for j, a in enumerate(sys.argv[2:], start=1):
    alph[j] = float(a)
n = 7 ** k
orbit_of = lambda d: tuple(sorted(min(x, 7 - x) for x in d))  # noqa: E731
orbits = sorted({orbit_of(d) for d in itertools.product(range(7), repeat=k)})
idx = {o: i for i, o in enumerate(orbits)}
size = np.zeros(len(orbits))
for d in itertools.product(range(7), repeat=k):
    size[idx[orbit_of(d)]] += 1
c7 = [np.cos(2 * np.pi * a * np.arange(7) / 7) for a in range(4)]
F = np.zeros((len(orbits), len(orbits)))
for d in itertools.product(range(7), repeat=k):
    j = idx[orbit_of(d)]
    for i, uo in enumerate(orbits):
        F[i, j] += np.prod([c7[uo[t]][d[t]] for t in range(k)])
zero = idx[tuple([0] * k)]
forbidden = [i for i, o in enumerate(orbits) if max(o) <= 1 and i != zero]


def cblock(s):  # vector over orbits: average over the orbit of c_B(d), B = {x,x+1}^s x Z7^(k-s)
    v = np.zeros(len(orbits))
    for d in itertools.product(range(7), repeat=k):
        val = 0.0
        for perm in itertools.permutations(range(k)):  # average over which coordinates carry the 2-blocks
            p = 1.0
            for pos, coord in enumerate(perm):
                x = min(d[coord], 7 - d[coord])
                p *= (2 if x == 0 else 1 if x == 1 else 0) if pos < s else 7
            val += p
        v[idx[orbit_of(d)]] += val / np.math.factorial(k) if hasattr(np, "math") else val / __import__("math").factorial(k)
    return v  # sum over d in orbit of averaged c_B(d)


rows, rhs = [-F], [np.zeros(len(orbits))]
desc = []
for s in range(1, k):
    c = alph[k - s]
    Bsize = 2 ** s * 7 ** (k - s)
    v = cblock(s)
    row = v.copy()
    row[zero] -= c * Bsize  # sum_d f(d) c_B(d) - c |B| f(0) <= 0 ; v[zero] already includes c_B(0) * 1
    rows.append(row[None, :]); rhs.append(np.zeros(1))
    desc.append(f"B={{x,x+1}}^{s} x C7^{k - s}: alpha<= {c:g}")
A_ub = np.vstack(rows); b_ub = np.concatenate(rhs)
for nonneg in (False, True):
    A_eq = [np.eye(len(orbits))[zero]] + [np.eye(len(orbits))[i] for i in forbidden]
    b_eq = [1 / n] + [0] * len(forbidden)
    res = linprog(-n * size, A_ub=A_ub, b_ub=b_ub, A_eq=np.array(A_eq), b_eq=b_eq,
                  bounds=[(0, None) if nonneg else (None, None)] * len(orbits), method="highs")
    print(f"k={k} {'theta_+blocks (f>=0)' if nonneg else 'theta+blocks        '}: {-res.fun:.6f}   "
          f"[theta = {3.3176672 ** k:.4f}; layer bound = {7 * alph[k - 1] / 2:.2f}]", flush=True)
print("blocks:", "; ".join(desc))
