#!/usr/bin/env python3
"""Is alpha(C7^4) >= 115? Feasibility ILP with the forced layer structure.

If |I| = 115, along any coordinate c the layer sizes a_x = |{v in I: v_c = x}| satisfy a_x + a_{x+1} <= 33
(alpha(C7^3) = 33) and sum = 115 = floor(7*33/2); solving the cyclic system forces a = (16,16,17,16,17,16,17)
up to rotation/reflection. Rotations and reflections act independently per coordinate (automorphisms of the
strong power), so WLOG every coordinate has exactly this pattern starting at x = 0: 28 equalities.
Plus: 16-cliques (<= 1), blocks {x,x+1}^s x C7^(4-s) (<= 33, 10, 3). Objective: none (feasibility), solved
as max sum with sum fixed to 115. Infeasible => alpha(C7^4) <= 114.
Usage: alpha115_feasibility.py seconds
"""
import itertools
import sys
import numpy as np
import highspy

secs = float(sys.argv[1])
m = 4
pattern = [16, 16, 17, 16, 17, 16, 17]
V = list(itertools.product(range(7), repeat=m))
idx = {v: i for i, v in enumerate(V)}
n = len(V)
rows = []  # (members, lo, hi)
for a in V:
    rows.append(([idx[tuple((a[i] + e[i]) % 7 for i in range(m))] for e in itertools.product((0, 1), repeat=m)],
                 -highspy.kHighsInf, 1))
cap = {1: 33, 2: 10, 3: 3}
for s in (1, 2, 3):
    for S in itertools.combinations(range(m), s):
        for base in itertools.product(range(7), repeat=s):
            mem = [i for i, v in enumerate(V) if all((v[S[j]] - base[j]) % 7 in (0, 1) for j in range(s))]
            rows.append((mem, -highspy.kHighsInf, cap[s]))
for c in range(m):
    for x in range(7):
        mem = [i for i, v in enumerate(V) if v[c] == x]
        rows.append((mem, pattern[x], pattern[x]))
rows.append((list(range(n)), 115, 115))
h = highspy.Highs()
h.setOptionValue("time_limit", secs)
h.setOptionValue("threads", 2)
lp = highspy.HighsLp()
lp.num_col_, lp.num_row_ = n, len(rows)
lp.col_cost_ = np.zeros(n)
lp.col_lower_, lp.col_upper_ = np.zeros(n), np.ones(n)
lp.row_lower_ = np.array([r[1] for r in rows], dtype=float)
lp.row_upper_ = np.array([r[2] for r in rows], dtype=float)
st, ix = [0], []
for r in rows:
    ix += r[0]; st.append(len(ix))
lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
lp.a_matrix_.start_, lp.a_matrix_.index_ = np.array(st), np.array(ix)
lp.a_matrix_.value_ = np.ones(len(ix))
lp.integrality_ = [highspy.HighsVarType.kInteger] * n
h.passModel(lp)
h.run()
print("RESULT status:", h.modelStatusToString(h.getModelStatus()), flush=True)
