"""Check whether 4-variable inequalities follow from Shannon plus a list of known inequalities
under all 24 relabellings of the variables."""
from itertools import permutations

import numpy as np
from scipy.optimize import linprog

from entlp import Problem, elemental, zhang_yeung
from project import N4, dense


def permute(ci, perm):
    """ci over subsets 1..15 with variables relabelled i -> perm[i]."""
    out = np.zeros(N4, dtype=ci.dtype)
    for s in range(1, 16):
        t = sum(1 << perm[i] for i in range(4) if s >> i & 1)
        out[t - 1] = ci[s - 1]
    return out


def closure(base):
    """All relabellings of each inequality in base (arrays over 15 coordinates)."""
    seen, out = set(), []
    for b in base:
        for p in permutations(range(4)):
            q = permute(np.asarray(b), p)
            k = tuple(int(x) for x in q)
            if k not in seen:
                seen.add(k)
                out.append(q)
    return out


def implied(ci, base):
    """min ci.h over Shannon + closure(base), h(ABCD) <= 1; implied iff min >= 0."""
    G = dense(elemental(4), N4)
    rows = np.vstack([G] + [np.array(closure(base), float)]) if base else G
    A = np.vstack([-rows, np.eye(N4)[-1:]])
    b = np.concatenate([np.zeros(len(rows)), [1]])
    res = linprog(np.asarray(ci, float), A_ub=A, b_ub=b, bounds=(0, None), method="highs")
    return res.fun > -1e-9


def zy_vec():
    z = zhang_yeung()
    v = np.zeros(N4, int)
    for s, x in z.items():
        v[s - 1] = x
    return v
