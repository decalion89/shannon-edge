#!/usr/bin/env python3
"""Surprise-adaptive error-bounded coding of Venus Express packets: every
value within +-delta (delta = k x the field's robust noise sigma, as in
near_lossless.py --safe), except *surprising* values, which are kept
exact. A value is surprising when it is at least Z sigma away from the
previous reconstructed value (Z = 6, fixed before any measurement). The
receiver must know which values are exact; the cost of that flag stream is
reported as its ideal adaptive entropy, and it is added to the codec's
output size.

    python3 bench/analysis/surprise_adaptive.py venus.bin OUT_PREFIX k ...
"""
import math
import sys

import numpy as np

P = np.fromfile(sys.argv[1], dtype=np.uint8).reshape(-1, 90).astype(np.int64)
out_prefix = sys.argv[2]
n = len(P)
split = n // 10
Z = 6.0
fields = [(10, 2), (18, 3), (22, 3), (26, 3), (30, 3), (58, 3), (62, 3), (66, 3), (70, 3), (74, 3),
          (77, 4), (81, 4), (85, 4)]  # the "safe" set of near_lossless.py


def vals(s, w):
    v = np.zeros(n, dtype=np.int64)
    for i in range(w):
        v = v * 256 + P[:, s + i]
    return v


def put(Q, s, w, v):
    for i in range(w):
        Q[:, s + w - 1 - i] = (v >> (8 * i)) & 255


sig = {}
for s, w in fields:
    mod = 1 << (8 * w)
    v = vals(s, w)[:split]
    d = (v[1:] - v[:-1]) % mod
    d = np.where(d >= mod // 2, d - mod, d)
    sig[(s, w)] = 1.4826 * np.median(np.abs(d - np.median(d))) / np.sqrt(2)
for k in [float(x) for x in sys.argv[3:]]:
    Q = P.copy()
    exact_total, flag_bits, worst = 0, 0.0, 0.0
    for s, w in fields:
        delta = int(k * sig[(s, w)])
        step = 2 * delta + 1
        mod = 1 << (8 * w)
        v = vals(s, w)
        r = np.empty(n, dtype=np.int64)
        r[0] = v[0]
        exact = np.zeros(n, bool)
        thr = Z * max(sig[(s, w)], 1.0)
        for t in range(1, n):
            d = (v[t] - r[t - 1]) % mod
            if d >= mod // 2:
                d -= mod
            if abs(d) >= thr:
                r[t] = v[t]
                exact[t] = True
            else:
                r[t] = (r[t - 1] + int(round(d / step)) * step) % mod
        err = np.abs(((v - r + mod // 2) % mod) - mod // 2)
        assert err.max() <= delta and (err[exact] == 0).all()
        worst = max(worst, err.max() / max(sig[(s, w)], 1e-9))
        put(Q, s, w, r)
        m = int(exact.sum())
        exact_total += m
        # ideal adaptive (KT) cost of the flag stream for this field
        flag_bits += math.lgamma(n + 1) - math.lgamma(m + 0.5) - math.lgamma(n - m + 0.5) + math.lgamma(0.5) * 2 - math.lgamma(1) \
            if m else math.log2(n + 1)
    Q.astype(np.uint8).tofile(f"{out_prefix}_k{k}.bin")
    print(f"k={k}: surprising values kept exact {exact_total:,} of {n * len(fields):,} "
          f"({100 * exact_total / (n * len(fields)):.3f}%), flag cost ~{flag_bits / math.log(2) / 8:,.0f} bytes, "
          f"max error {worst:.2f} sigma -> {out_prefix}_k{k}.bin")
