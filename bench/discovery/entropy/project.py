#!/usr/bin/env python3
"""All 4-variable inequalities implied by a copy strategy: the projection of the extended
polymatroid cone onto the 15 coordinates of (A, B, C, D), computed by outer approximation.

Q starts as the Shannon cone Gamma_4 sliced at h(ABCD) = 1. Repeatedly: enumerate Q's vertices (cdd);
for each vertex outside the projection, an LP over Farkas multipliers finds a valid inequality
violated there; add it. Stops when every vertex of Q lies in the projection, so Q equals it.
"""

from fractions import Fraction
from itertools import combinations

import cdd
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, hstack, vstack

from entlp import Problem, elemental

N4 = 15  # coordinates of the 4-variable entropy vector: subsets 1..15


def dense(rows, dim):
    M = np.zeros((len(rows), dim))
    for i, r in enumerate(rows):
        for s, v in r.items():
            M[i, s - 1] = v
    return M


class Projection:
    def __init__(self, n, copies):
        """copies: list of (src, over, dst) applied in order on an n-variable problem."""
        p = Problem(n)
        for src, over, dst in copies:
            p.copy(src, over, dst)
        self.p = p
        self.G = dense(p.ineq, p.dim)  # G h >= 0
        self.E = dense(p.eq, p.dim) if p.eq else np.zeros((0, p.dim))

    def contains(self, v):
        """Is the 4-variable vector v (length 15) the restriction of a feasible extended vector?"""
        dim = self.p.dim
        Aeq = [np.eye(dim)[:N4]] + ([self.E] if len(self.E) else [])
        beq = [v] + ([np.zeros(len(self.E))] if len(self.E) else [])
        res = linprog(np.zeros(dim), A_ub=-self.G, b_ub=np.zeros(len(self.G)), A_eq=np.vstack(Aeq),
                      b_eq=np.concatenate(beq), bounds=(0, None), method="highs")
        return res.status == 0

    def cut(self, v):
        """A valid inequality c.x >= 0 (on the 15 coordinates) minimising c.v, with |c| <= 1; None if c.v >= 0."""
        dim = self.p.dim
        ng, ne = len(self.G), len(self.E)
        # variables: c (15, free in [-1,1]), lam (ng, >= 0), mu (ne, free)
        # constraint: [c; 0] = G^T lam + E^T mu  (dim equations)
        Ic = np.zeros((dim, N4))
        Ic[:N4, :N4] = np.eye(N4)
        A = np.hstack([Ic, -self.G.T, -self.E.T if ne else np.zeros((dim, 0))])
        obj = np.concatenate([v, np.zeros(ng + ne)])
        bounds = [(-1, 1)] * N4 + [(0, None)] * ng + [(None, None)] * ne
        res = linprog(obj, A_eq=A, b_eq=np.zeros(dim), bounds=bounds, method="highs")
        if res.status != 0 or res.fun > -1e-9:
            return None
        return res.x[:N4]


def to_rational(c, verify, v):
    """Round c to small integers, keeping it valid (verify(c) -> bool) and violated at v."""
    c = c / np.max(np.abs(c))
    for den in (1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 30, 60, 120, 840, 5040, 100000):
        r = np.array([Fraction(x).limit_denominator(den) for x in c])
        lcm = np.lcm.reduce([f.denominator for f in r])
        ci = np.array([int(f * lcm) for f in r])
        g = np.gcd.reduce(np.abs(ci[ci != 0]))
        ci = ci // g
        if np.dot(ci, v) < -1e-9 and verify(ci):
            return ci
    return None


def vertices(ineqs):
    """Vertices of {x: a.x >= 0 for a in ineqs, x(ABCD) = 1}."""
    rows = [[0] + [int(a) for a in r] for r in ineqs]
    rows.append([-1] + [0] * 14 + [1])  # h(ABCD) >= 1 ... and <= 1 below
    rows.append([1] + [0] * 14 + [-1])
    mat = cdd.matrix_from_array(rows, rep_type=cdd.RepType.INEQUALITY, lin_set=[len(rows) - 1])
    poly = cdd.polyhedron_from_matrix(mat)
    gen = cdd.copy_generators(poly)
    out = []
    for g in gen.array:
        if g[0] == 1:
            out.append(np.array([float(x) for x in g[1:]]))
    return out


def run(proj, max_rounds=200, log=print):
    ineqs = [list(dense([r], N4)[0].astype(int)) for r in elemental(4)]
    found = []

    def valid(ci):
        f = {s + 1: int(ci[s]) for s in range(N4) if ci[s]}
        return proj.p.minimise(f)[0] > -1e-9

    for rnd in range(max_rounds):
        V = vertices(ineqs)
        outside = [v for v in V if not proj.contains(v)]
        log(f"round {rnd}: {len(V)} vertices, {len(outside)} outside the projection, {len(found)} new inequalities")
        if not outside:
            return found, True
        added = 0
        for v in outside:
            if any(np.dot(f, v) < -1e-9 for f in found[-added:] if added):
                continue
            c = proj.cut(v)
            if c is None:
                continue
            ci = to_rational(c, valid, v)
            if ci is None:
                continue
            if any(np.array_equal(ci, f) for f in found):
                continue
            found.append(ci)
            ineqs.append(list(ci))
            added += 1
        if not added:
            return found, False
    return found, False


NAMES = ["A", "B", "AB", "C", "AC", "BC", "ABC", "D", "AD", "BD", "ABD", "CD", "ACD", "BCD", "ABCD"]


def show(ci):
    return " ".join(f"{'+' if x > 0 else '-'}{abs(x) if abs(x) != 1 else ''}h({NAMES[i]})" for i, x in enumerate(ci) if x) + " >= 0"
