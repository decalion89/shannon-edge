#!/usr/bin/env python3
"""Linear programs over entropy vectors: Shannon (elemental) inequalities, the copy lemma, and the
test "is this information inequality implied?".

An entropy vector on n variables is indexed by non-empty subsets (bitmasks 1..2^n-1).
"""

from itertools import combinations

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix


def elemental(n):
    """Rows a with a.h >= 0 for the elemental Shannon inequalities (h[0] is the empty set, fixed 0)."""
    N = (1 << n) - 1
    rows = []
    for i in range(n):
        r = {N: 1, N & ~(1 << i): -1}
        rows.append(r)
    for i, j in combinations(range(n), 2):
        rest = [k for k in range(n) if k not in (i, j)]
        for m in range(len(rest) + 1):
            for K in combinations(rest, m):
                k = sum(1 << x for x in K)
                r = {}
                for s, c in ((k | 1 << i, 1), (k | 1 << j, 1), (k | 1 << i | 1 << j, -1), (k, -1)):
                    if s:
                        r[s] = r.get(s, 0) + c
                rows.append(r)
    return rows


def mi(a, b, c=0):
    """I(a;b|c) as a dict over subsets (a, b, c are bitmasks)."""
    r = {}
    for s, k in ((a | c, 1), (b | c, 1), (a | b | c, -1), (c, -1)):
        if s:
            r[s] = r.get(s, 0) + k
    return {s: v for s, v in r.items() if v}


def add(*terms):
    """Sum of (coef, dict) terms."""
    r = {}
    for k, d in terms:
        for s, v in d.items():
            r[s] = r.get(s, 0) + k * v
    return {s: v for s, v in r.items() if v}


class Problem:
    """Polymatroid on n variables plus linear equalities; minimise f.h with h(all) <= 1."""

    def __init__(self, n):
        self.n = n
        self.dim = (1 << n) - 1
        self.ineq = elemental(n)
        self.eq = []

    def copy(self, src, over, dst):
        """Variables dst (list) are a copy of src (list) over the set `over` (list of variable indices):
        (dst, over) has the joint law of (src, over), and dst is independent of all other variables given over."""
        m = dict(zip(src, dst))
        base = list(over)
        pool = list(src) + base
        for r in range(1, len(pool) + 1):
            for S in combinations(pool, r):
                if not any(v in src for v in S):
                    continue
                a = sum(1 << v for v in S)
                b = sum(1 << (m[v] if v in m else v) for v in S)
                if a != b:
                    self.eq.append(add((1, {a: 1}), (-1, {b: 1})))
        D = sum(1 << v for v in dst)
        O = sum(1 << v for v in over)
        rest = ((1 << self.n) - 1) & ~D & ~O
        if rest:
            self.eq.append(mi(D, rest, O))

    def minimise(self, f):
        """min f.h over the feasible cone with h(all) <= 1; returns (value, h)."""
        dim = self.dim
        A = lil_matrix((len(self.ineq) + 1, dim))
        for i, r in enumerate(self.ineq):
            for s, v in r.items():
                A[i, s - 1] = -v
        A[len(self.ineq), dim - 1] = 1
        b = np.zeros(len(self.ineq) + 1)
        b[-1] = 1
        Aeq = lil_matrix((max(len(self.eq), 1), dim))
        beq = np.zeros(max(len(self.eq), 1))
        for i, r in enumerate(self.eq):
            for s, v in r.items():
                Aeq[i, s - 1] = v
        c = np.zeros(dim)
        for s, v in f.items():
            c[s - 1] = v
        res = linprog(c, A_ub=A.tocsr(), b_ub=b, A_eq=Aeq.tocsr() if self.eq else None,
                      b_eq=beq if self.eq else None, bounds=(0, None), method="highs")
        assert res.status == 0, res.message
        return res.fun, res.x


def zhang_yeung(A=1, B=2, C=4, D=8):
    """ZY (1998): I(A;B) + I(A;CD) + 3 I(C;D|A) + I(C;D|B) - 2 I(C;D) >= 0."""
    return add((1, mi(A, B)), (1, mi(A, C | D)), (3, mi(C, D, A)), (1, mi(C, D, B)), (-2, mi(C, D)))


def ingleton(A=1, B=2, C=4, D=8):
    """Ingleton expression: I(A;B|C) + I(A;B|D) + I(C;D) - I(A;B) >= 0 holds for linear ranks, not all entropies."""
    return add((1, mi(A, B, C)), (1, mi(A, B, D)), (1, mi(C, D)), (-1, mi(A, B)))
