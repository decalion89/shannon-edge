#!/usr/bin/env python3
"""Is the noise really noise? (pre-registered in bench/discovery/hidden_noise_preregistration.md)

For each channel, the part every error-bounded scheme discards is e_t = v_t - y_t, where y_t is the
1-sigma lattice reconstruction (|e_t| <= delta). If e is white noise it carries no information. Here e is
quantised to 64 equal levels over [-delta, delta] and its online KT code length is compared:
  order 0   (no context: the white-noise assumption)
  order 1   (context: previous discarded symbol)
  cross     (context: the concurrent discarded symbol of another channel of the same mission)
Samples: 2,000,000 consecutive samples starting at the test split of each mission.

Usage: hidden_noise.py ESA-Mission1.zip ESA-Mission2.zip
"""

import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_esaadb import load  # noqa: E402
from bit_layers import robust_sigma  # noqa: E402
from microscope import code_lengths  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "results" / "data"
Q = 64
N = 2_000_000
SPECS = [("ESA-Mission1", [41, 42, 43, 44, 45, 46], "2006-10-01", "2007-01-01"),
         ("ESA-Mission2", [18, 19, 20], "2001-07-01", "2001-10-01")]  # 21-28: sigma = 0 or float jitter


def discarded(s, val, split):
    v = s.to_numpy(np.float64)
    idx = s.index.tz_localize(None) if s.index.tz is not None else s.index
    d = robust_sigma(v[idx < pd.Timestamp(val)])
    k = np.round((v - v[0]) / (2 * d))
    e = v - (v[0] + 2 * d * k)
    q = np.clip(np.floor((e + d) / (2 * d) * Q), 0, Q - 1).astype(np.int64)
    i0 = int(np.searchsorted(idx, np.datetime64(split)))
    return q[i0:i0 + N], idx[i0:i0 + N]


def main():
    rows = []
    for zp, (name, chans, val, split) in zip(sys.argv[1:3], SPECS):
        z = zipfile.ZipFile(zp)
        E, T = {}, {}
        for ch in chans:
            s = load(z, f"{name}/channels/channel_{ch}.zip")
            s = s[~s.index.duplicated(keep="last")].sort_index()
            E[ch], T[ch] = discarded(s, val, split)
        for ch in chans:
            q = E[ch]
            zero = np.zeros(len(q), np.int64)
            c0 = code_lengths(q[1:], zero[1:], Q, 1).mean()
            c1 = code_lengths(q[1:], q[:-1], Q, Q).mean()
            best_cross, best_with = c0, None
            for other in chans:
                if other == ch or len(E[other]) != len(q) or not np.array_equal(T[other], T[ch]):
                    continue
                cx = code_lengths(q[1:], E[other][1:], Q, Q).mean()
                if cx < best_cross:
                    best_cross, best_with = cx, other
            rows.append(dict(mission=name, channel=ch, order0=c0, order1=c1, cross=best_cross, cross_with=best_with,
                             gain1=1 - c1 / c0, gain_cross=1 - best_cross / c0))
            print(f"{name} ch{ch}: order-0 {c0:.3f} | order-1 {c1:.3f} ({100 * (1 - c1 / c0):+.1f}%) | "
                  f"cross {best_cross:.3f} with ch{best_with} ({100 * (1 - best_cross / c0):+.1f}%)  "
                  f"[uniform would be {np.log2(Q):.3f}] bit/sample", flush=True)
    d = pd.DataFrame(rows)
    d.to_csv(DATA / "hidden_noise.csv", index=False)
    n1 = float((d.gain1 >= 0.05).mean())
    n2 = bool((d.gain_cross >= 0.05).any())
    print(f"\nN1 channels whose discarded part is >= 5% compressible from its own past: {n1:.0%} (needs >= 50%): "
          f"{'HOLDS' if n1 >= 0.5 else 'REFUTED'}")
    print(f"N2 some channel's discarded part >= 5% predictable from another channel's: "
          f"{'HOLDS' if n2 else 'REFUTED'}")


if __name__ == "__main__":
    main()
