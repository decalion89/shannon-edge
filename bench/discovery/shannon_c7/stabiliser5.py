#!/usr/bin/env python3
"""Symmetry group of an independent set A in C7^5 inside Aut(C7^5) = (Z7 x| Z2) wr S5 (order 7^5 2^5 5! = 64,538,880).
For each (permutation P, signs s) find all translations t with P(s*A) + t = A. Prints |Stab| and generators.
Usage: stabiliser5.py set.npy"""
import itertools
import sys
import numpy as np

A = np.load(sys.argv[1]) % 7
m = A.shape[1]
w = 7 ** np.arange(m)[::-1]
key = lambda X: np.sort((X % 7) @ w)  # noqa: E731
kA = key(A)
found = []
for P in itertools.permutations(range(m)):
    for s in itertools.product((1, -1), repeat=m):
        B = (A[:, list(P)] * np.array(s)) % 7
        for b in B:
            t = (A[0] - b) % 7
            if np.array_equal(key(B + t), kA):
                found.append((P, s, tuple(t)))
print(f"|Stab| = {len(found)}")
for f in found[:12]:
    print("  perm", f[0], "signs", f[1], "translation", f[2])
