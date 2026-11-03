#!/usr/bin/env python3
"""The outermost limit: the one-bit zero-error equality task over ALL nonsignalling boxes (only relativity
assumed). Box p(a, b | x, (t, c)): Alice x = s in [N], a = message bit; Bob setting (t, c = message),
outcome b in {E, D, abstain}. Linear program: normalisation, nonnegativity, no-signalling both ways,
zero error (s = t never D, s != t never E), maximise the worst-case conclusive probability.
"""
import itertools
import sys

import numpy as np
from scipy.optimize import linprog


def solve(N):
    Y = [(t, c) for t in range(N) for c in (0, 1)]
    idx = {}
    for x in range(N):
        for yi in range(len(Y)):
            for a in (0, 1):
                for b in range(3):
                    idx[(x, yi, a, b)] = len(idx)
    nv = len(idx) + 1  # last variable: w
    Aeq, beq, Aub, bub = [], [], [], []

    def row():
        return np.zeros(nv)

    for x in range(N):
        for yi in range(len(Y)):
            r = row()
            for a in (0, 1):
                for b in range(3):
                    r[idx[(x, yi, a, b)]] = 1
            Aeq.append(r); beq.append(1)
    # no-signalling: Alice's marginal independent of Bob's setting; Bob's independent of Alice's
    for x in range(N):
        for a in (0, 1):
            for yi in range(1, len(Y)):
                r = row()
                for b in range(3):
                    r[idx[(x, yi, a, b)]] += 1
                    r[idx[(x, 0, a, b)]] -= 1
                Aeq.append(r); beq.append(0)
    for yi in range(len(Y)):
        for b in range(3):
            for x in range(1, N):
                r = row()
                for a in (0, 1):
                    r[idx[(x, yi, a, b)]] += 1
                    r[idx[(0, yi, a, b)]] -= 1
                Aeq.append(r); beq.append(0)
    E, D = 0, 1
    for s in range(N):
        for t in range(N):
            # Bob uses setting (t, a): the relevant entries are p(a, b | s, (t, a))
            good, bad = (E, D) if s == t else (D, E)
            r = row()
            for a in (0, 1):
                r[idx[(s, Y.index((t, a)), a, bad)]] = 1
            Aeq.append(r); beq.append(0)
            r = row()
            r[-1] = 1
            for a in (0, 1):
                r[idx[(s, Y.index((t, a)), a, good)]] = -1
            Aub.append(r); bub.append(0)
    c = np.zeros(nv); c[-1] = -1
    res = linprog(c, A_ub=np.array(Aub), b_ub=bub, A_eq=np.array(Aeq), b_eq=beq,
                  bounds=[(0, None)] * (nv - 1) + [(None, None)], method="highs")
    return -res.fun, res.status


if __name__ == "__main__":
    for N in [int(x) for x in sys.argv[1:]]:
        v, st = solve(N)
        print(f"N={N}: nonsignalling (relativity-only) optimum = {v:.6f}   [quantum/classical 1/N = {1 / N:.4f}]")
