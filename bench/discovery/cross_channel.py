#!/usr/bin/env python3
"""Compression-gap microscope across channels (ESA-AD Mission 1, one week mid-mission).

For every ordered pair (x -> y) of the given channels and lags 0 and 1: the gap is the code length
of y_t knowing its own previous value, minus knowing also x_{t-lag} (bits/sample; transfer entropy,
with lag 0 meaning the same instant, which the ground has once x is decoded). It is compared with 5
circular time shifts of x. A pair is reported when its gap beats every shift; the excess over the
best shift is the information x carries about y that y's own past does not.

Usage: cross_channel.py ESA-Mission1.zip CHANNEL...
"""

import sys
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_esaadb import load  # noqa: E402
from microscope import code_lengths  # noqa: E402

Q = 32
WEEK = 7 * 3008


def quant(v):
    lo, hi = np.quantile(v, 0.005), np.quantile(v, 0.995)
    return np.clip(((v - lo) / (hi - lo + 1e-12) * Q).astype(int), 0, Q - 1)


def gain(yq, xq, lag):
    y, yp = yq[2:], yq[1:-1]
    xl = xq[2 - lag:len(xq) - lag]
    return (code_lengths(y, yp, Q, Q) - code_lengths(y, yp * Q + xl, Q, Q * Q)).mean()


def main():
    z = zipfile.ZipFile(sys.argv[1])
    chans = sys.argv[2:]
    data = {}
    for ch in chans:
        s = load(z, f"ESA-Mission1/channels/channel_{ch}.zip")
        s = s[~s.index.duplicated(keep="last")].sort_index()
        mid = len(s) // 2
        data[ch] = quant(s.to_numpy(float)[mid:mid + WEEK])
    rng = np.random.default_rng(0)
    print("| x -> y | lag | gain (mbit/sample) | best of 5 shifts | excess | verdict |\n|---|---:|---:|---:|---:|---|")
    for y in chans:
        for x in chans:
            if x == y:
                continue
            for lag in (0, 1):
                g = gain(data[y], data[x], lag)
                null = max(gain(data[y], np.roll(data[x], int(rng.integers(WEEK // 10, WEEK - WEEK // 10))), lag)
                           for _ in range(5))
                ok = g > null
                print(f"| {x} -> {y} | {lag} | {g*1000:.1f} | {null*1000:.1f} | {(g-null)*1000:.1f} | "
                      f"{'information' if ok else '-'} |", flush=True)


if __name__ == "__main__":
    main()
