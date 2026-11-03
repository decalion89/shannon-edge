#!/usr/bin/env python3
"""Exact ILP attack on alpha(C7^4) (known: 108 <= alpha <= 115; 115 = floor(33 * 3.5), the cheap layer bound).
Valid constraints (all from known exact values alpha(C7)=3, alpha(C7^2)=10, alpha(C7^3)=33):
  - 16-cliques {a + {0,1}^4}: sum <= 1
  - for any set S of coordinates fixed to a 2-block {x,x+1} each, the remaining C7^(4-|S|) gives
    sum <= alpha(C7^(4-|S|)):  |S|=1 -> 33, |S|=2 -> 10, |S|=3 -> 3
  - symmetry breaking: vertex 0 in the set (vertex-transitive graph)
Reports the solver's primal and dual bounds. Usage: alpha_c7_4_ilp.py seconds
"""
import itertools
import sys
import numpy as np
import highspy

secs = float(sys.argv[1])
m = 4
V = list(itertools.product(range(7), repeat=m))
idx = {v: i for i, v in enumerate(V)}
rows = []  # (indices, ub)
for a in V:
    rows.append(([idx[tuple((a[i] + e[i]) % 7 for i in range(m))] for e in itertools.product((0, 1), repeat=m)], 1))
alpha_rest = {1: 33, 2: 10, 3: 3}
for s in (1, 2, 3):
    for S in itertools.combinations(range(m), s):
        for base in itertools.product(range(7), repeat=s):
            members = [i for i, v in enumerate(V)
                       if all((v[S[j]] - base[j]) % 7 in (0, 1) for j in range(s))]
            rows.append((members, alpha_rest[s]))
h = highspy.Highs()
h.setOptionValue("output_flag", True)
h.setOptionValue("time_limit", secs)
h.setOptionValue("log_to_console", True)
inf = highspy.kHighsInf
n = len(V)
lp = highspy.HighsLp()
lp.num_col_ = n
lp.num_row_ = len(rows)
lp.col_cost_ = np.full(n, -1.0)
lb = np.zeros(n); ub = np.ones(n); lb[idx[(0,) * m]] = 1.0
lp.col_lower_ = lb
lp.col_upper_ = ub
lp.row_lower_ = np.full(len(rows), -inf)
lp.row_upper_ = np.array([r[1] for r in rows], dtype=float)
starts, index, value = [0], [], []
for r in rows:
    index += r[0]; value += [1.0] * len(r[0]); starts.append(len(index))
lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
lp.a_matrix_.start_ = np.array(starts)
lp.a_matrix_.index_ = np.array(index)
lp.a_matrix_.value_ = np.array(value)
lp.integrality_ = [highspy.HighsVarType.kInteger] * n
h.passModel(lp)
h.run()
info = h.getInfo()
print(f"RESULT alpha(C7^4): best found {-info.objective_function_value:.0f}, "
      f"proven upper bound {-info.mip_dual_bound:.3f}, status {h.modelStatusToString(h.getModelStatus())}",
      flush=True)
