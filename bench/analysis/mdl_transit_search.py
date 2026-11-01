#!/usr/bin/env python3
"""Planet search as compression: bits saved by a code that knows a period.

    python3 bench/analysis/mdl_transit_search.py LC.fits [--pmin 0.5 --pmax 20]

Null code: detrended flux ~ Gaussian(0, sigma), sigma = robust noise.
Alternative code: the same, but points inside a box of duration D at phase
phi of period P are shifted by a fitted depth d.
For n in-box points with mean m, the bits saved are n*m^2/(2*sigma^2*ln 2)
(the Gaussian log-likelihood ratio at the fitted depth), minus half a bit
per... no: minus the description of (P, phi, D, d).
Two-part MDL: every hypothesis on the search grid is described with
log2(#hypotheses) bits, plus 0.5*log2(n) bits for the depth. By the Kraft
inequality over the grid, if the data are pure noise, P(net saving >= t) <=
2^-t: the false-alarm bound comes from the code length, not from
simulations.
Detrending: subtract a running median of 1 day. Reports the best few
(P, phi, D) with net bits saved, after masking the previous detection (to
find a second planet).
"""
import argparse

import numpy as np
from astropy.io import fits
from scipy.ndimage import median_filter

ap = argparse.ArgumentParser()
ap.add_argument("fits")
ap.add_argument("--pmin", type=float, default=0.5)
ap.add_argument("--pmax", type=float, default=20.0)
ap.add_argument("--planets", type=int, default=3)
ap.add_argument("--cotrend", nargs="*", default=[],
                help="other stars' light curves of the same quarter: subtract their common-mode (median of "
                     "their detrended, normalised flux, interpolated to this star's times), scaled by least "
                     "squares. A signal shared by all stars is the instrument, not a planet")
a = ap.parse_args()
d = fits.open(a.fits)[1].data
t, f = d["TIME"], d["PDCSAP_FLUX"]
ok = np.isfinite(t) & np.isfinite(f)
t, f = t[ok].astype(np.float64), f[ok].astype(np.float64) / np.median(f[ok])
cad = np.median(np.diff(t))
r = f - median_filter(f, size=max(3, int(round(1.0 / cad))), mode="nearest")
if a.cotrend:
    others = []
    for path in a.cotrend:
        dd = fits.open(path)[1].data
        tt, ff = dd["TIME"], dd["PDCSAP_FLUX"]
        k = np.isfinite(tt) & np.isfinite(ff)
        tt, ff = tt[k].astype(np.float64), ff[k].astype(np.float64) / np.median(ff[k])
        rr = ff - median_filter(ff, size=max(3, int(round(1.0 / cad))), mode="nearest")
        rr /= 1.4826 * np.median(np.abs(np.diff(rr))) / np.sqrt(2)  # each star in its own noise units
        others.append(np.interp(t, tt, rr))
    cm = np.median(np.array(others), axis=0)
    beta = float(np.dot(cm, r) / max(np.dot(cm, cm), 1e-30))
    r = r - beta * cm
sigma = 1.4826 * np.median(np.abs(np.diff(r))) / np.sqrt(2)
T = t[-1] - t[0]
durs = [d_ for d_ in (1.0 / 24, 2.0 / 24, 4.0 / 24, 8.0 / 24)]
mask = np.ones(len(t), bool)
for k in range(a.planets):
    best = None
    n_hyp = 0
    for D in durs:
        # period grid: relative step D/(4T) so a box of width D stays aligned over the baseline
        P = a.pmin
        periods = []
        while P <= a.pmax:
            periods.append(P)
            P *= 1 + D / (4 * T)
        nb_tot = 0
        for P in periods:
            nb = max(4, int(np.ceil(P / (D / 2))))  # phase bins of half a duration
            nb_tot += nb
            ph = ((t[mask] - t[0]) / P) % 1.0
            b = (ph * nb).astype(np.int64)
            s = np.bincount(b, weights=r[mask], minlength=nb)
            c = np.bincount(b, minlength=nb).astype(np.float64)
            # boxes of 2 adjacent half-duration bins (width D)
            s2, c2 = s + np.roll(s, -1), c + np.roll(c, -1)
            with np.errstate(divide="ignore", invalid="ignore"):
                gain = np.where((c2 > 2) & (s2 < 0), s2 * s2 / (2 * sigma ** 2 * np.log(2) * c2), 0.0)
            j = int(np.argmax(gain))
            if best is None or gain[j] - 0.5 * np.log2(max(c2[j], 1)) > best[0]:
                best = (gain[j] - 0.5 * np.log2(max(c2[j], 1)), P, j / nb, D, -s2[j] / c2[j], int(c2[j]))
        n_hyp += nb_tot
    desc = np.log2(n_hyp)
    net, P, ph, D, depth, n = best
    # Consistency (as in transit vetting): the same box must save bits in each half of the
    # time series separately. A one-off instrumental event can only be in one half.
    phall = ((t - t[0]) / P) % 1.0
    inbox = mask & (phall >= ph) & (phall < ph + D / P)
    half = t < t[0] + (t[-1] - t[0]) / 2
    halves = []
    for hmask in (half, ~half):
        sel = inbox & hmask
        c_ = sel.sum()
        s_ = r[sel].sum()
        halves.append(s_ * s_ / (2 * sigma ** 2 * np.log(2) * c_) - 0.5 * np.log2(max(c_, 1)) if c_ > 2 and s_ < 0 else 0.0)
    print(f"  consistency: bits saved in each half {halves[0]:.1f} / {halves[1]:.1f} (weaker half {min(halves):.1f})")
    print(f"planet search #{k + 1}: best P = {P:.5f} d, phase {ph:.3f}, duration {D * 24:.0f} h, depth {depth * 1e6:.0f} ppm, "
          f"{n} points in box; bits saved {net + desc:.1f} - description {desc:.1f} = net {net:.1f} bits "
          f"(false-alarm bound 2^-{max(net, 0):.0f})")
    # mask this signal's boxes before looking for the next one
    phall = ((t - t[0]) / P) % 1.0
    mask &= ~((phall >= ph - 0.02 * D / P * 12) & (phall <= ph + D / P + 0.02))
print(f"noise {sigma * 1e6:.0f} ppm per point; {n_hyp:,} hypotheses -> {np.log2(n_hyp):.1f} bits to name one")
