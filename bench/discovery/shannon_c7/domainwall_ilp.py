#!/usr/bin/env python3
"""ILP version of the domain-wall test (domainwall_sat.py ran out of memory): independent set of C7^5 (box/clique
constraints, sum <= 1 per 2^5 box) with layer sizes along every coordinate equal to the one-wall pattern
(53,52,53,52,53,52,53) (size 368). Feasibility -> new record. HiGHS with time limit. Usage: domainwall_ilp.py seconds"""
import itertools
import sys
import numpy as np
import highspy

secs = float(sys.argv[1])
m = 5
pattern = [53, 52, 53, 52, 53, 52, 53]
V = np.array(list(itertools.product(range(7), repeat=m)))
w = 7 ** np.arange(m)[::-1]
n = len(V)
E = np.array(list(itertools.product((0, 1), repeat=m)))
rows, lo, hi = [], [], []
for a in V:
    rows.append(((a + E) % 7) @ w); lo.append(-highspy.kHighsInf); hi.append(1)
for c in range(m):
    for x in range(7):
        rows.append(np.nonzero(V[:, c] == x)[0]); lo.append(pattern[x]); hi.append(pattern[x])
h = highspy.Highs()
h.setOptionValue("time_limit", secs)
h.setOptionValue("output_flag", True)
lp = highspy.HighsLp()
lp.num_col_, lp.num_row_ = n, len(rows)
lp.col_cost_ = np.zeros(n)
lp.col_lower_, lp.col_upper_ = np.zeros(n), np.ones(n)
lp.row_lower_, lp.row_upper_ = np.array(lo, float), np.array(hi, float)
st, ix = [0], []
for r in rows:
    ix += list(r); st.append(len(ix))
lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
lp.a_matrix_.start_, lp.a_matrix_.index_ = np.array(st), np.array(ix)
lp.a_matrix_.value_ = np.ones(len(ix))
lp.integrality_ = [highspy.HighsVarType.kInteger] * n
h.passModel(lp)
h.run()
status = h.modelStatusToString(h.getModelStatus())
print("RESULT:", status, flush=True)
if status == "Optimal":
    x = np.array(h.getSolution().col_value) > 0.5
    A = V[x]
    d = (A[:, None, :] - A[None, :, :]) % 7
    ok = (np.minimum(d, 7 - d) >= 2).any(axis=2); np.fill_diagonal(ok, True)
    print("size", len(A), "independent", ok.all(), flush=True)
    np.save("/tmp/claude-0/-home-user/f5214594-0f71-5d98-9550-f6c6aba4b49e/scratchpad/domainwall368.npy", A)
