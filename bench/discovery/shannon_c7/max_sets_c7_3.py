#!/usr/bin/env python3
"""Maximum independent sets of C7^3 (alpha = 33): verify alpha and enumerate maximum sets containing vertex 0
(vertex-transitive, so every orbit of maximum sets is represented) with no-good cuts, up to a cap.
Goal: understand which 33-sets exist, to analyse how they can be chained in the 7 layers of C7^4.
Usage: max_sets_c7_3.py cap seconds
"""
import itertools
import sys
import time
import numpy as np
import highspy

cap, secs = int(sys.argv[1]), float(sys.argv[2])
m = 3
V = list(itertools.product(range(7), repeat=m))
idx = {v: i for i, v in enumerate(V)}
n = len(V)
rows = [([idx[tuple((a[i] + e[i]) % 7 for i in range(m))] for e in itertools.product((0, 1), repeat=m)], 1.0)
        for a in V]
for S in itertools.combinations(range(m), 1):  # pairs of layers: alpha(C7^2) = 10
    for b in range(7):
        rows.append(([i for i, v in enumerate(V) if (v[S[0]] - b) % 7 in (0, 1)], 10.0))


def build(extra_rows, fix_count=None):
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    lp = highspy.HighsLp()
    allrows = rows + extra_rows
    lp.num_col_, lp.num_row_ = n, len(allrows)
    lp.col_cost_ = np.full(n, -1.0)
    lb = np.zeros(n); lb[idx[(0,) * m]] = 1.0
    lp.col_lower_, lp.col_upper_ = lb, np.ones(n)
    lo = np.full(len(allrows), -highspy.kHighsInf)
    up = np.array([r[1] for r in allrows])
    lp.row_lower_, lp.row_upper_ = lo, up
    st, ix = [0], []
    for r in allrows:
        ix += r[0]; st.append(len(ix))
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.a_matrix_.start_, lp.a_matrix_.index_ = np.array(st), np.array(ix)
    lp.a_matrix_.value_ = np.ones(len(ix))
    lp.integrality_ = [highspy.HighsVarType.kInteger] * n
    if fix_count is not None:  # require sum >= fix_count via a row with lower bound
        pass
    h.passModel(lp)
    return h


t0 = time.time()
h = build([])
h.run()
alpha = round(-h.getInfo().objective_function_value)
print(f"alpha(C7^3) = {alpha}  ({time.time() - t0:.1f}s)", flush=True)
# enumerate maximum sets containing 0 using no-good cuts: sum_{i in S} x_i <= alpha - 1
cuts, found = [], []
while len(found) < cap and time.time() - t0 < secs:
    h = build(cuts)
    h.run()
    val = -h.getInfo().objective_function_value
    if val < alpha - 0.5:
        print("no more maximum sets containing vertex 0", flush=True)
        break
    x = np.array(h.getSolution().col_value) > 0.5
    S = np.nonzero(x)[0].tolist()
    found.append(S)
    cuts.append((S, float(alpha - 1)))
print(f"found {len(found)} maximum independent sets of C7^3 containing vertex 0 "
      f"({'complete' if len(found) < cap and time.time() - t0 < secs else 'capped'}); {time.time() - t0:.0f}s",
      flush=True)
np.save("/tmp/claude-0/-home-user/f5214594-0f71-5d98-9550-f6c6aba4b49e/scratchpad/max33.npy",
        np.array(found, dtype=object), allow_pickle=True)
