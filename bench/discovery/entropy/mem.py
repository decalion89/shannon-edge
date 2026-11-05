#!/usr/bin/env python3
"""Maximum Entropy Method (Csirmaz, arXiv:2509.12439, Lemma MEM) as a projection problem.

Start from an entropic f on A,B,C,D, extended by exact duplicates (A' parallel to A, ...): still
entropic. For a down-closed family F of subsets, MEM gives a polymatroid g on the same base with
g = f on F and g(X;Y|D) = 0 for EVERY 3-partition XYD that separates F (no F-set meets both X and Y).
The 4-variable inequalities implied are the projection of
  { g polymatroid : g(S) = g(pi(S)) for S in F, all separating CI statements hold }
onto the 15 subsets of ABCD (pi maps each duplicate to its original; ABCD is in F).
A single separating partition is the Copy Lemma (Csirmaz, Claim equiv2); several at once is the
part whose strength relative to the iterated Copy Lemma is an open problem (his Problem list).
"""

import itertools

import numpy as np

import project as P
from entlp import Problem, mi


def downclose(maxsets):
    F = set()
    for m in maxsets:
        bits = [b for b in range(16) if m >> b & 1]
        for r in range(1, len(bits) + 1):
            for c in itertools.combinations(bits, r):
                F.add(sum(1 << b for b in c))
    return F


def separating_partitions(n, F):
    """All 3-partitions (X, Y, D) of range(n), X and Y non-empty, X<Y, with no F-set meeting both."""
    out = []
    for lab in itertools.product(range(3), repeat=n):
        X = sum(1 << i for i in range(n) if lab[i] == 0)
        Y = sum(1 << i for i in range(n) if lab[i] == 1)
        D = sum(1 << i for i in range(n) if lab[i] == 2)
        if not X or not Y or X > Y:
            continue
        if all(not (S & X and S & Y) for S in F):
            out.append((X, Y, D))
    return out


class MEMProjection(P.Projection):
    def __init__(self, dup_of, maxsets):
        """dup_of: list of base indices duplicated (duplicate i gets index 4+i); maxsets: bitmasks over 4+k elements."""
        n = 4 + len(dup_of)
        p = Problem(n)
        F = downclose(maxsets) | downclose([15])
        pi = {4 + i: d for i, d in enumerate(dup_of)}
        for S in F:
            T = 0
            for b in range(n):
                if S >> b & 1:
                    T |= 1 << (pi.get(b, b))
            if T != S:
                p.eq.append({S: 1, T: -1})
        parts = separating_partitions(n, F)
        for X, Y, D in parts:
            p.eq.append(mi(X, Y, D))
        self.parts = parts
        self.p = p
        self.G = P.dense(p.ineq, p.dim)
        self.E = P.dense(p.eq, p.dim) if p.eq else np.zeros((0, p.dim))
