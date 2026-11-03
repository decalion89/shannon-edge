#!/usr/bin/env python3
"""Lovasz theta and Schrijver theta' of C7^k (strong power) as Cayley graphs on Z_7^k, via the invariant
(circulant) reduction: X_ij = f(i - j). theta: f(0) = 1/n, f(d) = 0 on the connection set D (nonzero d with
all coordinates in {0, +-1}), Fourier transform of f >= 0; maximise n * sum f. theta' adds f >= 0.
Symmetry: f depends only on the multiset of |coordinates| (orbits under coordinate permutations and signs).
Usage: theta_cayley.py k
"""
import itertools
import sys
import numpy as np
from scipy.optimize import linprog

k = int(sys.argv[1])
n = 7 ** k
# orbit of d: sorted tuple of circular |d_i| in {0,1,2,3}
orbit_of = lambda d: tuple(sorted(min(x, 7 - x) for x in d))  # noqa: E731
orbits = sorted({orbit_of(d) for d in itertools.product(range(7), repeat=k)})
idx = {o: i for i, o in enumerate(orbits)}
size = np.zeros(len(orbits))
for d in itertools.product(range(7), repeat=k):
    size[idx[orbit_of(d)]] += 1
# Fourier: character chi_u(d) = prod cos(2 pi u_i d_i / 7); sum over orbit of d depends on orbit of u
c = [np.cos(2 * np.pi * a * np.arange(7) / 7) for a in range(4)]  # c[a][x]
F = np.zeros((len(orbits), len(orbits)))  # F[u_orbit, d_orbit] = sum_{d in orbit} chi_u(d)
for d in itertools.product(range(7), repeat=k):
    j = idx[orbit_of(d)]
    for i, uo in enumerate(orbits):
        F[i, j] += np.prod([c[uo[t]][d[t]] for t in range(k)])
zero = idx[tuple([0] * k)]
forbidden = [i for i, o in enumerate(orbits) if max(o) <= 1 and i != zero]
for nonneg in (False, True):
    # variables: f per orbit (value of f on each element of the orbit)
    cobj = -n * size
    A_eq, b_eq = [], []
    e = np.zeros(len(orbits)); e[zero] = 1; A_eq.append(e); b_eq.append(1 / n)
    for i in forbidden:
        e = np.zeros(len(orbits)); e[i] = 1; A_eq.append(e); b_eq.append(0)
    A_ub = -F  # Fourier >= 0
    b_ub = np.zeros(len(orbits))
    bounds = [(0, None) if nonneg else (None, None)] * len(orbits)
    r = linprog(cobj, A_ub=A_ub, b_ub=b_ub, A_eq=np.array(A_eq), b_eq=b_eq, bounds=bounds, method="highs")
    name = "theta'" if nonneg else "theta "
    val = -r.fun
    print(f"k={k} {name}(C7^k) = {val:.6f}  -> per-use {val ** (1 / k):.6f}  (theta(C7)^k = {3.3176672 ** k:.6f})")
