#!/usr/bin/env python3
"""Symbolic proof of the achievability half: for every N >= 8 the explicit moments
   <1> = 1,  <A_x> = <B_y> = (3N^2-18N+16)/d,  <A_x B_x> = N^2/d,  <A_x B_y> = 0 (x != y),
   <A_x A_y> = <B_x B_y> = (3N^2-28N+32)/(2d),  <A_x A_y B_x B_y> = N^2 (N-8) / ((5N-8) d),
   all other moment classes 0,   d = 17N^2 - 80N + 64,
form a PSD level-1+AB moment matrix, so s_AQ(N) >= N^2/d. Positivity is shown block by block: a real
symmetric matrix is PSD iff every coefficient of its characteristic polynomial det(xI - M) alternates
in sign (all elementary symmetric functions of the eigenvalues >= 0). Each such function is a rational
function of N; its numerator and denominator are checked to have no real root above 8 and the right
sign there.
"""
import sys
from fractions import Fraction

import sympy as sp

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import aq_cert_sym as S  # noqa: E402

Nn = sp.symbols("N", positive=True)
R = S.Reduced()
C = R.classes
d = 17 * Nn**2 - 80 * Nn + 64
val = {k: sp.Integer(0) for k in C}
val[C[0]] = sp.Integer(1)
val[C[1]] = val[C[2]] = (3 * Nn**2 - 18 * Nn + 16) / d
val[C[3]] = Nn**2 / d
val[C[5]] = val[C[8]] = (3 * Nn**2 - 28 * Nn + 32) / (2 * d)
val[C[11]] = Nn**2 * (Nn - 8) / ((5 * Nn - 8) * d)


def poly_coef(getter, k):
    xs = R.Ns
    ys = [getter(R.data[n]).get(k, 0) for n in xs]
    return sp.interpolate(list(zip(xs, ys)), Nn)


def entry(getter):
    return sp.together(sum(poly_coef(getter, k) * val[k] for k in C))


def nonneg_for_N_ge_8(expr):
    num, den = sp.fraction(sp.factor(sp.together(expr)))
    ok = True
    for poly in (num, den):
        p = sp.Poly(sp.expand(poly), Nn)
        if p.is_zero:
            continue
        roots = [r for r in sp.real_roots(p) if r > 8]
        if roots:
            ok = False
    val_big = sp.limit(expr, Nn, sp.oo) if not sp.simplify(expr) == 0 else 0
    sample = expr.subs(Nn, 9)
    return ok and sample >= 0, sp.factor(expr)


def check_block(M, name):
    x = sp.symbols("x")
    cp = sp.Poly(sp.expand(sp.together((x * sp.eye(M.shape[0]) - M).det())), x)
    coeffs = cp.all_coeffs()  # x^n, x^(n-1), ...
    allok = True
    for i, c in enumerate(coeffs[1:], start=1):
        e = sp.together(((-1) ** i) * c)  # elementary symmetric function e_i
        ok, f = nonneg_for_N_ge_8(e)
        allok &= ok
        print(f"  {name} e_{i} = {f}   -> {'>= 0 for N >= 8' if ok else 'NOT shown'}")
    return allok


def main():
    T = sp.Matrix(5, 5, lambda i, j: entry(lambda dd, i=i, j=j: dd[0][i][j]))
    Sm = sp.Matrix(5, 5, lambda i, j: entry(lambda dd, i=i, j=j: dd[1][i][j]))
    T = (T + T.T) / 2
    Sm = (Sm + Sm.T) / 2
    q4 = sp.factor(entry(lambda dd: dd[2]))
    q3 = sp.factor(entry(lambda dd: dd[3]))
    print("trivial block:")
    a = check_block(T, "T")
    print("standard block:")
    b = check_block(Sm, "S")
    c4, _ = nonneg_for_N_ge_8(q4)
    c3, _ = nonneg_for_N_ge_8(q3)
    print(f"(N-2,2) scalar = {q4}: {'>= 0' if c4 else 'NOT shown'};  (N-2,1,1) scalar = {q3}: {'>= 0' if c3 else 'NOT shown'}")
    print("ACHIEVABILITY PROVED for all N >= 8" if (a and b and c4 and c3) else "not proved")


if __name__ == "__main__":
    main()
