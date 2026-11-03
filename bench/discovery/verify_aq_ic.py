#!/usr/bin/env python3
"""Independent numerical verification of Das Bhowmik & Banik, "Almost-Quantum Correlations Violate
Information Causality", arXiv:2610.41444 (v1, 30 Oct 2026).

(A) Their explicit almost-quantum (AQ) realisation of the box p* (Appendix A), for N = 1..60 settings.
(B) The exact information-causality sum of their block-certification protocol (not only their lower bound).
(C) AQ membership checked independently: feasibility of the NPA level-"1+AB" moment matrix for N = 2..6.
(D) Their contrast with quantum theory: NPA level-2 upper bound on sum_x p(0,0|x,x) for certificate boxes,
    and the largest s at level 1+AB, for small N.
"""

import itertools

import cvxpy as cp
import numpy as np

S = 1 / 17


# ---------------------------------------------------------------------------------------------- (A)
def realisation(N):
    d = 2 * N + 3
    E = np.eye(d)
    psi, e1, e2 = E[0], E[1], E[2]
    f = [E[3 + x] for x in range(N)]
    g = [E[3 + N + x] for x in range(N)]
    c = [3 / 17 * psi + np.sqrt(15) / 34 * e2 + np.sqrt(5) / (2 * np.sqrt(17)) * g[x] for x in range(N)]
    dd = [np.sqrt(51) / 34 * e1 + 1 / (2 * np.sqrt(17)) * f[x] for x in range(N)]
    u = [c[x] + dd[x] for x in range(N)]
    v = [c[x] - dd[x] for x in range(N)]
    w = [1 / 17 * psi - 2 * np.sqrt(15) / 85 * e2 + 2 / np.sqrt(85) * g[x] for x in range(N)]

    def proj(a, b):
        Q, _ = np.linalg.qr(np.stack([a, b], 1))
        return Q @ Q.T

    A0 = [proj(u[x], w[x]) for x in range(N)]
    B0 = [proj(v[y], w[y]) for y in range(N)]
    I = np.eye(d)
    err_comm, err_p = 0.0, 0.0
    for x in range(N):
        for y in range(N):
            for Ax in (A0[x], I - A0[x]):
                for By in (B0[y], I - B0[y]):
                    err_comm = max(err_comm, np.abs(Ax @ By @ psi - By @ Ax @ psi).max())
            p00 = psi @ A0[x] @ B0[y] @ psi
            target = S if x == y else 0.0
            err_p = max(err_p, abs(p00 - target))
        err_p = max(err_p, abs(psi @ A0[x] @ psi - 3 / 17), abs(psi @ B0[x] @ psi - 3 / 17))
    err_proj = max(np.abs(P @ P - P).max() for P in A0 + B0)
    return err_comm, err_p, err_proj


# ---------------------------------------------------------------------------------------------- (B)
def h(p):
    p = np.asarray(p, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = -p * np.log2(p) - (1 - p) * np.log2(1 - p)
    return np.nan_to_num(r)


def ic_sum(k, N, s=S):
    u = 2.0 ** -k
    i = np.arange(N)
    t = s * u * (1 - u) ** i
    exact = k * np.sum(h(t) - 0.5 * h(2 * t))
    bound = k * s * (1 - (1 - u) ** N)
    return exact, bound


# ---------------------------------------------------------------------------------------- (C), (D)
def reduce_word(word):
    """Commute Alice's letters to the left, then merge equal neighbours (projectors)."""
    a = [l for l in word if l[0] == "A"]
    b = [l for l in word if l[0] == "B"]

    def merge(seq):
        out = []
        for l in seq:
            if not out or out[-1] != l:
                out.append(l)
        return tuple(out)

    return merge(a), merge(b)


def canon(word):
    a, b = reduce_word(word)
    return min((a, b), (a[::-1], b[::-1]))


def moment_matrix(ops):
    n = len(ops)
    keys = {}
    idx = np.empty((n, n), dtype=object)
    for r in range(n):
        for c in range(n):
            kk = canon(tuple(reversed(ops[r])) + ops[c])
            idx[r, c] = kk
            keys.setdefault(kk, len(keys))
    return idx, keys


def npa(N, level, s=None, objective=False):
    A = [(("A", x),) for x in range(N)]
    B = [(("B", y),) for y in range(N)]
    ops = [()] + A + B
    if level == "1+AB":
        ops += [(("A", x), ("B", y)) for x in range(N) for y in range(N)]
    elif level == 2:
        ops += [(("A", x), ("B", y)) for x in range(N) for y in range(N)]
        ops += [(("A", x), ("A", z)) for x in range(N) for z in range(N) if x != z]
        ops += [(("B", x), ("B", z)) for x in range(N) for z in range(N) if x != z]
    idx, keys = moment_matrix(ops)
    m = cp.Variable(len(keys))
    G = cp.Variable((len(ops), len(ops)), symmetric=True)
    cons = [G >> 0]
    for r in range(len(ops)):
        for c in range(r, len(ops)):
            cons.append(G[r, c] == m[keys[idx[r, c]]])
    cons.append(m[keys[((), ())]] == 1)
    for x in range(N):
        for y in range(N):
            kk = keys.get(canon((("A", x), ("B", y))))
            if x != y:
                cons.append(m[kk] == 0)
            elif s is not None:
                cons.append(m[kk] == s)
        if s is not None:
            cons += [m[keys[canon((("A", x),))]] == 3 / 17, m[keys[canon((("B", x),))]] == 3 / 17]
    if objective:
        obj = cp.Maximize(sum(m[keys[canon((("A", x), ("B", x)))]] for x in range(N)))
        prob = cp.Problem(obj, cons)
    else:
        prob = cp.Problem(cp.Minimize(0), cons)
    prob.solve(solver="CLARABEL")
    return prob.status, (prob.value if objective else None), G.value


def main():
    print("(A) explicit AQ realisation of p* (max errors: commutation on psi, probabilities, projector):")
    for N in (1, 2, 3, 5, 10, 30, 60):
        ec, ep, er = realisation(N)
        print(f"    N={N:3d}: {ec:.1e}  {ep:.1e}  {er:.1e}")
    print("(B) information-causality sum, exact vs the paper's bound:")
    for k, N in ((18, 757_693), (18, 757_692), (18, 2 ** 22), (24, 24 * 2 ** 24), (30, 30 * 2 ** 30 // 64)):
        if N > 50_000_000:
            u = 2.0 ** -k
            bound = k * S * (1 - (1 - u) ** N)
            exact = float("nan")
        else:
            exact, bound = ic_sum(k, N)
        print(f"    k={k}, N={N:,}: exact I = {exact:.9f}, bound = {bound:.9f}  (IC requires I <= 1)")
    print("(C) NPA level 1+AB feasibility of p* (status, min eigenvalue of the moment matrix):")
    for N in (2, 3, 4, 5, 6):
        st, _, G = npa(N, "1+AB", s=S)
        print(f"    N={N}: {st}, min eig {np.linalg.eigvalsh(G).min():.2e}")
    print("(D) max sum_x p(0,0|x,x) over certificate boxes (p(0,0|x,y)=0 for x!=y):")
    for N in (3, 4, 5):
        st1, v1, _ = npa(N, "1+AB", objective=True)
        st2, v2, _ = npa(N, 2, objective=True)
        print(f"    N={N}: level 1+AB {v1:.4f} ({st1}); level 2 {v2:.4f} ({st2})  [paper: quantum <= 1]")


if __name__ == "__main__":
    main()
