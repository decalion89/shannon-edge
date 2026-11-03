#!/usr/bin/env python3
"""One-bit zero-error equality task with a single two-sided certificate box (exploration).

Protocol: box settings x = s, y = t, binary outcomes. Alice sends M = a. Bob outputs "equal" if
(M, b) = (0, 0), "different" if (M, b) = (0, 1), abstains if M = 1. Zero error requires
p(0,0|x,y) = 0 for x != y and p(0,1|x,x) = 0 (i.e. p(0,0|x,x) = p_A(0)). Both answers are then
conclusive exactly when a = 0, so the worst-case success is p_A(0|x). Maximise it over the almost-quantum
set (NPA level 1+AB), symmetry-reduced as in aq_cert_sym.py.
"""
import sys

import cvxpy as cp

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import aq_cert_sym as S  # noqa: E402


def solve(R, N):
    K = len(R.classes)
    m = cp.Variable(K)
    idx = {k: i for i, k in enumerate(R.classes)}

    def expr(get):
        return sum(float(R.coef(N, get, k)) * m[idx[k]] for k in R.classes if R.coef(N, get, k) != 0)

    Tm = cp.bmat([[expr(lambda d, i=i, j=j: d[0][i][j]) for j in range(5)] for i in range(5)])
    Sm = cp.bmat([[expr(lambda d, i=i, j=j: d[1][i][j]) for j in range(5)] for i in range(5)])
    one, a = idx[S.canon(())], idx[S.canon(S.A(0))]
    diag, off = idx[S.canon(S.P(0, 0))], idx[S.canon(S.P(0, 1))]
    cons = [(Tm + Tm.T) / 2 >> 0, (Sm + Sm.T) / 2 >> 0, expr(lambda d: d[2]) >= 0, expr(lambda d: d[3]) >= 0,
            m[one] == 1, m[off] == 0, m[diag] == m[a]]
    p = cp.Problem(cp.Maximize(m[a]), cons)
    p.solve(solver="CLARABEL")
    return p.value, p.status


if __name__ == "__main__":
    R = S.Reduced()
    for N in [int(x) for x in sys.argv[1:]]:
        v, st = solve(R, N)
        lb = N * N / (19 * N * N - 80 * N + 64) if N >= 8 else None
        print(f"N={N}: two-sided box worst-case success = {v:.8f} (1/v = {1 / v:.4f})  "
              f"[quantum 1/N = {1 / N:.4f}; companion AQ lower bound {lb if lb is None else round(lb, 5)}]  {st}")
