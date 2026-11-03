#!/usr/bin/env python3
"""Checks for the robust coincidence inequality (see welch_witness.md):

    S^2 <= T,   S = sum_x p(0,0|x,x),   T = sum_{x,y} p(0,0|x,y),

valid for every commuting-operator box with binary outcomes.
1. random quantum strategies (tensor products, random projectors / states): max S^2 - T;
2. the operator inequality X <= A^{1/2} B^{1/2} behind the proof (X = sum_y A_y B_y);
3. tightness on maximally entangled states with equiangular tight frames;
4. almost-quantum violation and noise tolerance of the witness for large N.
"""
import numpy as np
from scipy.linalg import sqrtm

rng = np.random.default_rng(7)


def proj(d, r):
    M = rng.normal(size=(d, r)) + 1j * rng.normal(size=(d, r))
    Q, _ = np.linalg.qr(M)
    return Q @ Q.conj().T


def effect(d):
    M = rng.normal(size=(d, d)) + 1j * rng.normal(size=(d, d))
    H = M @ M.conj().T
    w, V = np.linalg.eigh(H)
    w = rng.uniform(0, 1, size=d)
    return V @ np.diag(w) @ V.conj().T


worst, worst_op = -np.inf, np.inf
for trial in range(4000):
    N, dA, dB = rng.integers(2, 9), rng.integers(2, 5), rng.integers(2, 5)
    mk = (lambda d: proj(d, rng.integers(1, d + 1))) if trial % 3 else effect  # projectors or general effects
    A = [np.kron(mk(dA), np.eye(dB)) for _ in range(N)]
    B = [np.kron(np.eye(dA), mk(dB)) for _ in range(N)]
    psi = rng.normal(size=dA * dB) + 1j * rng.normal(size=dA * dB)
    psi /= np.linalg.norm(psi)
    P = np.array([[np.real(psi.conj() @ A[x] @ B[y] @ psi) for y in range(N)] for x in range(N)])
    worst = max(worst, np.trace(P) ** 2 - P.sum())
    if trial < 1500:
        X = sum(a @ b for a, b in zip(A, B))
        R = sqrtm(sum(A)) @ sqrtm(sum(B))
        D = R - X
        worst_op = min(worst_op, np.linalg.eigvalsh((D + D.conj().T) / 2).min())
print(f"1. max over 4000 random quantum strategies of S^2 - T = {worst:.2e}  (<= 0 expected)")
print(f"2. min eigenvalue of A^1/2 B^1/2 - X over 1500 cases = {worst_op:.2e}  (>= 0 up to sqrtm error)")

for N, d in [(4, 2), (7, 3), (9, 3), (16, 4)]:
    c = (N - d) / (d * (N - 1))  # Welch-bound overlap of an ETF of N vectors in C^d
    S, T = N / d, N / d + N * (N - 1) * c / d
    print(f"3. ETF N={N}, d={d}: S^2 = {S * S:.4f}, T = {T:.4f}  (equal: tight)")

print("4. almost-quantum optimal certificate boxes (T = S on the face, S = N^3/(17N^2-80N+64)):")
for N in [9, 18, 50, 100, 1000]:
    S = N ** 3 / (17 * N * N - 80 * N + 64)
    tol = S * (S - 1) / (N * (N - 1))  # mixing in off-diagonal coincidences eps keeps S^2 > T while eps < tol
    print(f"   N={N}: S = {S:.4f}, S^2 - T = {S * S - S:.4f}, tolerated off-diagonal coincidence eps < {tol:.5f}")
print("   limit N -> infinity: eps < 1/289 =", 1 / 289)
