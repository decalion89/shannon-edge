#!/usr/bin/env python3
"""Search for a quantum independent set of size t in G = C7^2 (strong square): t projective measurements
{P_{i,v}}_v in C^d (rank-1 pieces |u_{i,a}><u_{i,a}| labelled L_i[a] in V) with
    <u_{i,a}, u_{j,b}> = 0   whenever i != j and L_i[a], L_j[b] are equal or adjacent in G.
Classical alpha(C7^2) = 10 (d = 1); theta = 11.0069, so t = 11 is the only possible quantum gain.
Cost = sum |<u_ia, u_jb>|^2 over forbidden pairs; unitaries U_i = expm(i H_i) optimised by BFGS; labels by
annealing. Usage: quantum_indep.py t d seconds seed
"""
import sys
import time
import numpy as np
from scipy.linalg import expm
from scipy.optimize import minimize

t, d, secs, seed = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
rng = np.random.default_rng(seed)
V = [(x, y) for x in range(7) for y in range(7)]
close1 = lambda a, b: min((a - b) % 7, (b - a) % 7) <= 1  # noqa: E731
CL = np.array([[close1(v[0], w[0]) and close1(v[1], w[1]) for w in V] for v in V])  # equal-or-adjacent


def herm(p):
    H = np.zeros((d, d), complex)
    iu = np.triu_indices(d, 1)
    H[np.diag_indices(d)] = p[:d]
    H[iu] = p[d:d + len(iu[0])] + 1j * p[d + len(iu[0]):]
    return H + np.triu(H, 1).conj().T


npar = d * d


def unitaries(P):
    return [expm(1j * herm(P[i * npar:(i + 1) * npar])) for i in range(t)]


def cost(P, L):
    U = unitaries(P)
    c = 0.0
    for i in range(t):
        for j in range(i + 1, t):
            M = np.abs(U[i].conj().T @ U[j]) ** 2  # M[a,b] = |<u_ia, u_jb>|^2
            c += (M * CL[np.ix_(L[i], L[j])]).sum()
    return c


def inner(L, P0, iters=200):
    r = minimize(cost, P0, args=(L,), method="L-BFGS-B", options={"maxiter": iters})
    return r.fun, r.x


L = [list(rng.integers(0, 49, size=d)) for _ in range(t)]
P = rng.normal(size=t * npar)
cur, P = inner(L, P)
best = cur
t0 = time.time()
while time.time() - t0 < secs and best > 1e-9:
    L2 = [row[:] for row in L]
    i, a = rng.integers(t), rng.integers(d)
    L2[i][a] = int(rng.integers(49))
    c2, P2 = inner(L2, P, iters=60)
    temp = 0.3 * (1 - (time.time() - t0) / secs) + 1e-3
    if c2 <= cur or rng.random() < np.exp((cur - c2) / temp):
        L, P, cur = L2, P2, c2
        if cur < best:
            best = cur
            print(f"  t={t} d={d}: cost {best:.3e} at {time.time() - t0:.0f}s", flush=True)
if best > 1e-9:
    cur, P = inner(L, P, iters=3000)
    best = min(best, cur)
print(f"t={t} d={d} seed={seed}: final min cost {best:.3e} (0 would mean a quantum independent set of size {t})",
      flush=True)
if best < 1e-9:
    print("labels:", L)
