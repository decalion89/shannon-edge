#!/usr/bin/env python3
"""The edge link (pre-registered in bench/results/esa_edge_link_preregistration.md): exact on-board
detection, error-bounded values on the link, real frame bytes.

Usage: esa_edge_link.py ESA-MissionN.zip --channels ... [--split 2001-10-01 --validation 2001-07-01] [--k 1]
"""

import argparse
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_esaadb import load  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FS = ROOT / "target/release/examples/flight_surprise"


def to_codes(v):
    _, c = np.unique(v.astype(np.float32), return_inverse=True)
    if c.max() >= 65536:
        c = c.astype(np.int64) * 65536 // (c.max() + 1)
    return c.astype("<u2")


def flight(codes):
    """Real frame bytes and per-sample cost (bits) of the flight profile on a code stream."""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        codes.tofile(d / "c")
        r = subprocess.run([str(FS), str(d / "c"), str(d / "s"), "14"], check=True, capture_output=True, text=True)
        nbytes = int(re.search(r"-> (\d+) bytes", r.stderr).group(1))
        cost = np.fromfile(d / "s", "<u4") / 256.0
    return nbytes, cost


def varint_len(x):
    n = 1
    while x >= 128:
        x >>= 7
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip")
    ap.add_argument("--channels", nargs="+", type=int, required=True)
    ap.add_argument("--split", default="2001-10-01")
    ap.add_argument("--validation", default="2001-07-01")
    ap.add_argument("--k", type=float, default=1.0)
    a = ap.parse_args()
    z = zipfile.ZipFile(a.zip)
    root = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
    split, val = pd.Timestamp(a.split), pd.Timestamp(a.validation)
    rows = []
    series = {}
    for ch in a.channels:
        s = load(z, f"{root}/channels/channel_{ch}.zip")
        s = s[~s.index.duplicated(keep="last")].sort_index()
        series[ch] = s
    n_test = sum(int((s.index >= split).sum()) for s in series.values())
    t = float(np.ceil(np.log2(n_test)))
    for ch, s in series.items():
        v = s.to_numpy(np.float64)
        codes = to_codes(v)
        b = max(1, (int(codes.max())).bit_length())
        lossless, cost = flight(codes)
        test = s.index >= split
        alarms = np.nonzero(test & (cost >= b + t))[0]
        alarm_bytes = sum(varint_len(int(x)) for x in np.diff(np.r_[0, alarms])) + varint_len(len(alarms))
        tr = s.index < val
        dv = np.diff(v[tr])
        sigma = 1.4826 * np.median(np.abs(dv - np.median(dv))) / np.sqrt(2)
        delta = a.k * sigma
        if delta > 0:
            step = 2 * delta
            k = np.round((v - v[0]) / step).astype(np.int64)
            recon = v[0] + step * k
            err = float(np.max(np.abs(recon - v)))
            idx = (k - k.min())
            idx = np.minimum(idx, 65535).astype("<u2") if idx.max() < 65536 else to_codes(k.astype(float))
            edge, _ = flight(idx)
        else:
            err, edge = 0.0, lossless
        rows.append((ch, len(v), lossless, edge, len(alarms), alarm_bytes, sigma, delta, err))
        print(f"channel {ch}: {len(v):,} samples; lossless {lossless:,} B; edge {edge:,} B + alarms {alarm_bytes} B "
              f"({len(alarms)} alarms); delta {delta:.4g}, max error {err:.4g}", flush=True)
    df = pd.DataFrame(rows, columns=["channel", "samples", "lossless_B", "edge_B", "alarms", "alarm_B", "sigma", "delta",
                                     "max_err"])
    L, E = df.lossless_B.sum(), df.edge_B.sum() + df.alarm_B.sum()
    ok_err = bool((df.max_err <= df.delta * (1 + 1e-9) + 1e-12).all())
    print(f"\nTotal: lossless {L:,} B; edge link {E:,} B (alarms {df.alarm_B.sum()} B) -> {100 * (1 - E / L):.1f}% saved; "
          f"error bound held on every channel: {ok_err}; Kraft margin t = {t:g} bits")
    print(f"Claim 1 (>= 40% saved): {'HOLDS' if 1 - E / L >= 0.40 else 'REFUTED'}; Claim 2 (error <= delta): "
          f"{'HOLDS' if ok_err else 'REFUTED'}; Claim 3: on-board alarms computed on exact data, identical by construction")
    df.to_csv(ROOT / f"bench/results/data/edge_link_{root}.csv", index=False)


if __name__ == "__main__":
    main()
