#!/usr/bin/env python3
"""Does the operator inequality behind S^2 <= T extend to k commuting families?

    X_k = sum_y A^(1)_y A^(2)_y ... A^(k)_y  <=  (A^(1) A^(2) ... A^(k))^{1/k},   A^(j) = sum_y A^(j)_y,

with A^(j)_y effects acting on tensor factor j. If true, Jensen gives S^k <= T_k (S = sum_y p(0..0|y..y),
T_k = sum over all setting tuples). Random tests: projectors and general effects, k = 2, 3, 4.
"""
import numpy as np
from functools import reduce

rng = np.random.default_rng(13)


def proj(d):
    r = rng.integers(1, d + 1)
    M = rng.normal(size=(d, r)) + 1j * rng.normal(size=(d, r))
    Q, _ = np.linalg.qr(M)
    return Q @ Q.conj().T


def effect(d):
    U, _ = np.linalg.qr(rng.normal(size=(d, d)) + 1j * rng.normal(size=(d, d)))
    return U @ np.diag(rng.uniform(0, 1, d)) @ U.conj().T


def embed(op, j, dims):
    return reduce(np.kron, [op if i == j else np.eye(dims[i]) for i in range(len(dims))])


def mpow(H, p):
    w, V = np.linalg.eigh((H + H.conj().T) / 2)
    return V @ np.diag(np.clip(w, 0, None) ** p) @ V.conj().T


for k in (2, 3, 4):
    worst_op, worst_S = np.inf, -np.inf
    for trial in range(600 if k < 4 else 200):
        dims = [int(rng.integers(2, 4)) for _ in range(k)]
        N = int(rng.integers(2, 6))
        mk = proj if trial % 2 else effect
        fam = [[embed(mk(dims[j]), j, dims) for _ in range(N)] for j in range(k)]
        X = sum(reduce(np.matmul, [fam[j][y] for j in range(k)]) for y in range(N))
        P = reduce(np.matmul, [sum(fam[j]) for j in range(k)])
        G = mpow(P, 1.0 / k)
        D = G - X
        worst_op = min(worst_op, np.linalg.eigvalsh((D + D.conj().T) / 2).min())
        psi = rng.normal(size=P.shape[0]) + 1j * rng.normal(size=P.shape[0])
        psi /= np.linalg.norm(psi)
        S = np.real(psi.conj() @ X @ psi)
        T = np.real(psi.conj() @ P @ psi)
        worst_S = max(worst_S, S ** k - T)
    print(f"k={k}: min eig[(prod A^(j))^(1/k) - X_k] = {worst_op:.2e} | max S^k - T_k = {worst_S:.2e}", flush=True)
