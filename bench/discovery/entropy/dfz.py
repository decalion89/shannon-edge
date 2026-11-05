"""Dougherty-Freiling-Zeger inequalities in their (a,...,g) form:
2I(A;B) <= aI(A;B|C)+bI(A;C|B)+cI(B;C|A)+dI(A;B|D)+eI(A;D|B)+fI(B;D|A)+gI(C;D)."""
import numpy as np

from entlp import add, mi

A, B, C, D = 1, 2, 4, 8
SIX = [(5, 3, 1, 2, 0, 0, 2), (4, 2, 1, 3, 1, 0, 2), (4, 4, 1, 2, 1, 1, 2),
       (3, 3, 3, 2, 0, 0, 2), (3, 4, 2, 3, 1, 0, 2), (3, 2, 2, 2, 1, 1, 2)]


def vec(coefs, lhs=2):
    a, b, c, d, e, f, g = coefs
    expr = add((a, mi(A, B, C)), (b, mi(A, C, B)), (c, mi(B, C, A)), (d, mi(A, B, D)), (e, mi(A, D, B)),
               (f, mi(B, D, A)), (g, mi(C, D)), (-lhs, mi(A, B)))
    v = np.zeros(15, int)
    for s, x in expr.items():
        v[s - 1] = x
    return v


def vec9(c):
    """aI(A;B) <= bI(A;B|C)+cI(A;C|B)+dI(B;C|A)+eI(A;B|D)+fI(A;D|B)+gI(B;D|A)+hI(C;D)+iI(C;D|A)."""
    a, b, cc, d, e, f, g, h, i = c
    expr = add((b, mi(A, B, C)), (cc, mi(A, C, B)), (d, mi(B, C, A)), (e, mi(A, B, D)), (f, mi(A, D, B)),
               (g, mi(B, D, A)), (h, mi(C, D)), (i, mi(C, D, A)), (-a, mi(A, B)))
    v = np.zeros(15, int)
    for s, x in expr.items():
        v[s - 1] = x
    return v


def final_list():
    import json
    from pathlib import Path
    return [vec9(it["coefs"]) for it in json.load(open(Path(__file__).with_name("dfz_list.json")))]
