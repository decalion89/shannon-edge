#!/usr/bin/env python3
"""Rate selection for the Slepian-Wolf prototype without per-packet feedback.

Inputs: the Venus Express packets, the DUMP.csv written by
`examples/slepian_wolf.rs` (index, bits changed, checks needed, expected
cost per test packet) and CCSDS 124 per-packet sizes from
`bench/c/ccsds124_loss.c`. The encoder estimates each packet's information
from a per-bit flip-cost table the ground uplinks (one table lookup per
changed bit); a rate rule m = a*est + b is fitted on the first half of the
packets and tested on the second half. Also evaluated: hybrid ARQ, where
only packets that fail ask for more checks.

Usage: python3 bench/slepian_wolf_rate.py venus-express.ccsds DUMP.csv ccsds_sizes.txt
"""

import sys

import numpy as np

packets, dump, sizes = sys.argv[1:4]
P = np.fromfile(packets, dtype=np.uint8).reshape(-1, 90)
split = len(P) // 10
bits = np.unpackbits(P ^ (P >> 1), axis=1).astype(np.int8)
flip = bits[1:] ^ bits[:-1]  # flip[t-1]: change from packet t-1 to t
a = np.loadtxt(dump, delimiter=",")
t, mmin = a[:, 0].astype(int), a[:, 2]
c124 = np.loadtxt(sizes)[: len(t)]
h = len(t) // 2


def estimate(order1: bool) -> np.ndarray:
    """Encoder-side information estimate; tables refreshed every 1000 packets."""
    est, cached = np.empty(len(t)), None
    for i, tt in enumerate(t):
        upto = (tt // 1000) * 1000
        if cached != upto:
            cached = upto
            if order1:
                F, Fp = flip[1 : upto - 1], flip[: upto - 2]
                tabs = []
                for c in (0, 1):
                    sel = Fp == c
                    q = (np.where(sel, F, 0).sum(0) + 0.5) / (sel.sum(0) + 1)
                    tabs.append((-np.log2(q), -np.log2(1 - q)))
            else:
                q = (flip[: upto - 1].sum(0) + 0.5) / upto
                tabs = [(-np.log2(q), -np.log2(1 - q))] * 2
        f, fp = flip[tt - 1], flip[tt - 2]
        c1 = np.where(fp == 1, tabs[1][0], tabs[0][0])
        c0 = np.where(fp == 1, tabs[1][1], tabs[0][1])
        est[i] = (f * c1 + (1 - f) * c0).sum()
    return est


def fit(est, target, cost_fn):
    best = None
    for A in np.arange(0, 2.51, 0.05):
        B = np.quantile(mmin[:h] - A * est[:h], target)
        mm = np.minimum(np.ceil((A * est[:h] + B) / 4) * 4, 720)
        c = cost_fn(mm, mmin[:h]).sum()
        if best is None or c < best[0]:
            best = (c, A, B)
    return best[1], best[2]


print(f"Oracle (per-packet feedback), test half: {(mmin[h:] + 24).sum() / 8:,.0f} bytes; "
      f"CCSDS 124 R=0: {c124[h:].sum():,.0f}")
print("Bits changed (no table): corr", round(np.corrcoef(
    [flip[tt - 1].sum() for tt in t], mmin)[0, 1], 3))
for name, order1 in (("per-bit flip table", False), ("order-1 flip table", True)):
    est = estimate(order1)
    print(f"\n{name}, refreshed every 1000 packets: corr {np.corrcoef(est, mmin)[0, 1]:.3f}")
    resend = lambda mm, need: np.where(mm >= need, mm, mm + 91 * 8)  # noqa: E731
    for target in (0.95, 0.99, 0.999):
        A, B = fit(est, target, resend)
        mm = np.minimum(np.ceil((A * est[h:] + B) / 4) * 4, 720)
        ok = mm >= mmin[h:]
        total = (mm + 24 + 8).sum() / 8 + (~ok).sum() * 91
        print(f"  no feedback, target {target}: m = {A:.2f}*est {B:+.0f}; first-time {ok.mean() * 100:.2f}%; "
              f"{total:,.0f} bytes incl. raw resends; vs CCSDS {100 * (total / c124[h:].sum() - 1):+.1f}%")
    harq = lambda mm, need: mm + np.where(mm >= need, 0, np.ceil((need - mm) / 16) * 16 + 8)  # noqa: E731
    for target in (0.5, 0.8, 0.9, 0.95):
        A, B = fit(est, target, harq)
        mm = np.minimum(np.ceil((A * est[h:] + B) / 4) * 4, 720)
        fail = mm < mmin[h:]
        total = (harq(mm, mmin[h:]) + 24 + 8).sum() / 8
        print(f"  hybrid ARQ, target {target}: {fail.mean() * 100:.1f}% need a 2nd round; {total:,.0f} bytes; "
              f"vs CCSDS {100 * (total / c124[h:].sum() - 1):+.1f}%")
