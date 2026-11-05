#!/usr/bin/env python3
"""Spectral fingerprint of maximum independent sets of C7^m: |hat 1_A(u)| = |sum_{x in A} exp(2 pi i <u,x>/7)| for
all u in Z_7^m, grouped by the frequency class (sorted multiset of |u_i| in {0,1,2,3}, the orbits of the
coordinate permutations and sign flips). Reports, per class, min and max over all u in the class and over all sets.
Exact zeros shared by every optimal set would be a 'spectral law' usable as extra constraints in theta-type bounds.
Usage: spectral.py set1.npy [set2.npy ...]"""
import itertools
import sys
import numpy as np

sets = [np.load(f) % 7 for f in sys.argv[1:]]
m = sets[0].shape[1]
U = np.array(list(itertools.product(range(7), repeat=m)))
cls = [tuple(sorted(min(x, 7 - x) for x in u)) for u in U]
stats = {}
for A in sets:
    ph = np.exp(2j * np.pi * (A @ U.T) / 7).sum(axis=0)
    mag = np.abs(ph)
    for c, v in zip(cls, mag):
        lo, hi = stats.get(c, (np.inf, -np.inf))
        stats[c] = (min(lo, v), max(hi, v))
print(f"{len(sets)} sets of size {[len(A) for A in sets]} in C7^{m}")
for c in sorted(stats):
    lo, hi = stats[c]
    flag = "  <-- ALWAYS ZERO" if hi < 1e-9 else ("  <-- never zero" if lo > 1e-9 else "")
    print(f"class {c}: |F| in [{lo:.3f}, {hi:.3f}]{flag}")
