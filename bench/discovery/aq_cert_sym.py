#!/usr/bin/env python3
"""Symmetry-reduced NPA "1+AB" SDP for the almost-quantum certification rate, valid for any N.

The moment matrix on {1, A_x, B_y, A_x B_y} is invariant under relabelling the settings (S_N). As an S_N
module the index space is 5 trivial + 5 standard + S^(N-2,2) + S^(N-2,1,1). The moment matrix is PSD iff
  * the 5x5 form on (1, sum_x A_x, sum_y B_y, sum_x P_xx, sum_{x!=y} P_xy) is PSD          (trivial)
  * the 5x5 form on the images of e_1 - e_2 under the equivariant maps
        e_x -> A_x, B_x, P_xx, sum_{y!=x} P_xy, sum_{y!=x} P_yx                               (standard)
    is PSD
  * q(4-cycle) >= 0 for (P12+P21) - (P23+P32) + (P34+P43) - (P41+P14)                        (N-2,2)
  * q(triangle) >= 0 for (P12-P21) + (P23-P32) + (P31-P13)                                   (N-2,1,1)
(P_xy = A_x B_y.) Each entry is a linear form in the 16 moment classes whose coefficients are polynomials
in N; they are obtained exactly by enumerating small N and interpolating (degree <= 4, checked on extra N).

Usage: aq_cert_sym.py N [N ...]
"""

import sys
from fractions import Fraction

import cvxpy as cp
import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from aq_cert_max import canon  # noqa: E402

A = lambda x: (("A", x),)  # noqa: E731
B = lambda y: (("B", y),)  # noqa: E731
P = lambda x, y: (("A", x), ("B", y))  # noqa: E731


def vectors(N):
    triv = [{(): 1}, {A(x): 1 for x in range(N)}, {B(y): 1 for y in range(N)}, {P(x, x): 1 for x in range(N)},
            {P(x, y): 1 for x in range(N) for y in range(N) if x != y}]

    def img(f):
        v = {}
        for x, c in ((0, 1), (1, -1)):
            for op, w in f(x).items():
                v[op] = v.get(op, 0) + c * w
        return {k: w for k, w in v.items() if w}

    std = [img(lambda x: {A(x): 1}), img(lambda x: {B(x): 1}), img(lambda x: {P(x, x): 1}),
           img(lambda x: {P(x, y): 1 for y in range(N) if y != x}),
           img(lambda x: {P(y, x): 1 for y in range(N) if y != x})]
    c4 = {}
    for (a, b), sg in (((0, 1), 1), ((1, 2), -1), ((2, 3), 1), ((3, 0), -1)):
        c4[P(a, b)] = c4.get(P(a, b), 0) + sg
        c4[P(b, a)] = c4.get(P(b, a), 0) + sg
    tri = {}
    for a, b in ((0, 1), (1, 2), (2, 0)):
        tri[P(a, b)] = tri.get(P(a, b), 0) + 1
        tri[P(b, a)] = tri.get(P(b, a), 0) - 1
    return triv, std, c4, tri


def form(u, v, classes):
    """Coefficients (dict class -> count) of u^T M v."""
    out = {}
    for a, wa in u.items():
        for b, wb in v.items():
            k = canon(tuple(reversed(a)) + b)
            out[k] = out.get(k, 0) + wa * wb
            if k not in classes:
                classes.append(k)
    return out


def blocks(N, classes):
    triv, std, c4, tri = vectors(N)
    T = [[form(u, v, classes) for v in triv] for u in triv]
    S = [[form(u, v, classes) for v in std] for u in std]
    return T, S, form(c4, c4, classes), form(tri, tri, classes)


def lagrange(xs, ys, x):
    tot = Fraction(0)
    for i, xi in enumerate(xs):
        t = Fraction(ys[i])
        for j, xj in enumerate(xs):
            if j != i:
                t *= Fraction(x - xj, xi - xj)
        tot += t
    return tot


class Reduced:
    """Polynomial-in-N coefficients of every block entry, from exact enumeration at N = 4..9, checked at 10, 11."""

    def __init__(self):
        self.classes = []
        self.Ns = [4, 5, 6, 7, 8, 9]
        self.data = {N: blocks(N, self.classes) for N in self.Ns + [10, 11]}

    def coef(self, N, getter, k):
        ys = [getter(self.data[n]).get(k, 0) for n in self.Ns]
        return lagrange(self.Ns, ys, N)

    def check(self):
        bad = 0
        for N in (10, 11):
            for which in range(4):
                g0 = self.data[N][which]
                ents = [(i, j) for i in range(5) for j in range(5)] if which < 2 else [None]
                for e in ents:
                    get = (lambda d, w=which, e=e: d[w][e[0]][e[1]]) if e else (lambda d, w=which: d[w])
                    for k in self.classes:
                        if self.coef(N, get, k) != get(self.data[N]).get(k, 0):
                            bad += 1
        return bad

    def solve(self, N):
        K = len(self.classes)
        m = cp.Variable(K)
        idx = {k: i for i, k in enumerate(self.classes)}

        def expr(get):
            return sum(float(self.coef(N, get, k)) * m[idx[k]] for k in self.classes
                       if self.coef(N, get, k) != 0)

        Tm = cp.bmat([[expr(lambda d, i=i, j=j: d[0][i][j]) for j in range(5)] for i in range(5)])
        Sm = cp.bmat([[expr(lambda d, i=i, j=j: d[1][i][j]) for j in range(5)] for i in range(5)])
        q4 = expr(lambda d: d[2])
        q3 = expr(lambda d: d[3])
        one = idx[canon(())]
        diag = idx[canon(P(0, 0))]
        off = idx[canon(P(0, 1))]
        cons = [(Tm + Tm.T) / 2 >> 0, (Sm + Sm.T) / 2 >> 0, q4 >= 0, q3 >= 0, m[one] == 1, m[off] == 0]
        prob = cp.Problem(cp.Maximize(m[diag]), cons)
        prob.solve(solver="CLARABEL")
        return prob.value, prob.status, m.value[idx[canon(A(0))]]


def main():
    R = Reduced()
    print(f"{len(R.classes)} moment classes; interpolation check failures: {R.check()}", flush=True)
    for N in [int(a) for a in sys.argv[1:]]:
        s, st, marg = R.solve(N)
        print(f"N={N}: max s = {s:.10f}  1/s = {1 / s:.8f}  N*s = {N * s:.6f}  marginal {marg:.8f}  {st}", flush=True)


if __name__ == "__main__":
    main()
