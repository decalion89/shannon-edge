#!/usr/bin/env python3
"""Temporal version: maximise S^2/T over qubit/qutrit sequential strategies (Lueders A_x, then B_y).
Does the maximum depend only on the dimension d (a temporal dimension witness)?"""
import sys
import numpy as np
from scipy.optimize import minimize

rng = np.random.default_rng(int(sys.argv[1]) if len(sys.argv) > 1 else 0)


def run(N, d, reps=40, rank=1):
    def unit(v):
        c = v[:d] + 1j * v[d:]
        return c / np.linalg.norm(c)

    def unpack(q):
        k, A, B = 0, [], []
        for L in (A, B):
            for _ in range(N):
                c = unit(q[k:k + 2 * d]); k += 2 * d
                L.append(np.outer(c, c.conj()))
        c = unit(q[k:k + 2 * d])
        return A, B, np.outer(c, c.conj())

    def ratio(q):
        A, B, rho = unpack(q)
        P = np.array([[np.real(np.trace(B[y] @ A[x] @ rho @ A[x])) for y in range(N)] for x in range(N)])
        S, T = np.trace(P), P.sum()
        return S * S / T, S, T

    best = (0, 0, 0)
    for _ in range(reps):
        r = minimize(lambda q: -ratio(q)[0], rng.normal(size=(2 * N + 1) * 2 * d), method="L-BFGS-B",
                     options={"maxiter": 800})
        v = ratio(r.x)
        if v[0] > best[0]:
            best = v
    return best


for d in (2, 3):
    for N in (2, 3, 4, 5, 6):
        R, S, T = run(N, d)
        print(f"d={d} N={N}: max S^2/T = {R:.6f}  (S={S:.4f}, T={T:.4f})", flush=True)
