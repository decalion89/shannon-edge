#!/usr/bin/env python3
"""Structure of the independent 108-sets of C7^4 found by different routes: symmetry group (stabiliser inside
Aut(C7^4) = (Z7 x| Z2) wr S4, order 7^4 * 2^4 * 4! = 921984), layer-size profiles per coordinate, and whether two
sets are equivalent (same orbit under Aut). Usage: structure108.py set1.npy set2.npy ...
"""
import itertools
import sys
import numpy as np

w = 7 ** np.arange(4)[::-1]
code = lambda X: set(((np.asarray(X) % 7) @ w).tolist())  # noqa: E731
sets = [np.load(f) % 7 for f in sys.argv[1:]]
G = [(P, s) for P in itertools.permutations(range(4)) for s in itertools.product((1, -1), repeat=4)]


def images(A):
    """all images of A under Aut, as frozensets of codes (canonical form = min over images)."""
    out = []
    for P, s in G:
        B = (A[:, list(P)] * np.array(s)) % 7
        for t in A:  # translate so that some point maps to the first point of A (enough for equality tests)
            pass
        out.append(B)
    return out


def stabiliser(A):
    cA = code(A)
    count = 0
    for P, s in G:
        B = (A[:, list(P)] * np.array(s)) % 7
        for b in B:  # candidate translation sends b to A[0]
            t = A[0] - b
            if code(B + t) == cA:
                count += 1
    return count


def canon(A):
    best = None
    for P, s in G:
        B = (A[:, list(P)] * np.array(s)) % 7
        for b in B:
            key = tuple(sorted(code(B - b)))
            if best is None or key < best:
                best = key
    return best


canons = []
for f, A in zip(sys.argv[1:], sets):
    prof = [sorted(np.bincount(A[:, c], minlength=7).tolist()) for c in range(4)]
    st = stabiliser(A)
    cn = canon(A)
    canons.append(cn)
    print(f"{f.split('/')[-1]}: |A|={len(A)}, |Stab|={st}, layer profiles (sorted) {prof}", flush=True)
classes = {}
for f, cn in zip(sys.argv[1:], canons):
    classes.setdefault(cn, []).append(f.split('/')[-1])
print(f"{len(classes)} equivalence class(es) under Aut(C7^4):")
for i, v in enumerate(classes.values()):
    print(f"  class {i}: {v}")
