#!/usr/bin/env python3
"""How many bits of communication is a law of nature worth? (pre-registered in
bench/discovery/law_bits_preregistration.md)

NOAA station 9414290 (San Francisco), 6-minute water levels, verified, metres (1 mm resolution).
2022 = training, 2023 = test. Every encoding guarantees |error| <= delta on every test sample,
delta = robust sigma of the training first differences (as in the noise-scale protocol).
  A  protocol alone: lattice of step 2 delta on the water level, flight profile
  B  protocol + the law: both ends share the astronomical tide (harmonic constituents with their
     known angular speeds, amplitudes and phases fitted on 2022); only the residual (level - tide) is
     sent on the same lattice, flight profile; plus the one-time cost of the coefficients (float32)
  L  lossless reference: the millimetre codes, flight profile

Usage: law_bits.py DATA_DIR
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bit_layers import robust_sigma  # noqa: E402
from esa_edge_link import flight, to_codes  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "results" / "data"
# standard tidal constituents: angular speed in degrees per hour
SPEEDS = {"M2": 28.9841042, "S2": 30.0, "N2": 28.4397295, "K2": 30.0821373, "K1": 15.0410686, "O1": 13.9430356,
          "P1": 14.9589314, "Q1": 13.3986609, "M4": 57.9682084, "M6": 86.9523127, "MK3": 44.0251729, "S4": 60.0,
          "MN4": 57.4238337, "MS4": 58.9841042, "2N2": 27.8953548, "MU2": 27.9682084, "NU2": 28.5125831,
          "L2": 29.5284789, "T2": 29.9589333, "J1": 15.5854433, "M1": 14.4966939, "OO1": 16.1391017,
          "2Q1": 12.8542862, "RHO1": 13.4715145, "SA": 0.0410686, "SSA": 0.0821373, "MM": 0.5443747,
          "MF": 1.0980331, "MSF": 1.0158958}


def load(d, year):
    fs = sorted(Path(d).glob(f"wl_{year}*.csv"))
    df = pd.concat([pd.read_csv(f) for f in fs])
    df.columns = [c.strip() for c in df.columns]
    df["t"] = pd.to_datetime(df["Date Time"])
    df = df.dropna(subset=["Water Level"]).drop_duplicates("t").sort_values("t")
    return df.t.to_numpy(), df["Water Level"].to_numpy(float)


def design(t, t0):
    h = (t - t0) / np.timedelta64(1, "h")
    cols = [np.ones_like(h)]
    for w in SPEEDS.values():
        a = np.deg2rad(w) * h
        cols += [np.cos(a), np.sin(a)]
    return np.stack(cols, 1)


def lattice_bytes(x, delta):
    k = np.round((x - x[0]) / (2 * delta)).astype(np.int64)
    li = k - k.min()
    assert np.max(np.abs(x[0] + 2 * delta * k - x)) <= delta * (1 + 1e-9) + 1e-12
    assert li.max() < 65536
    return flight(li.astype("<u2"))[0]


def main():
    d = sys.argv[1]
    t1, x1 = load(d, 2022)
    t2, x2 = load(d, 2023)
    t0 = t1[0]
    delta = robust_sigma(x1)
    beta, *_ = np.linalg.lstsq(design(t1, t0), x1, rcond=None)
    tide2 = design(t2, t0) @ beta
    # both ends compute the tide from float32 coefficients: use exactly those
    beta32 = beta.astype(np.float32).astype(np.float64)
    tide2 = design(t2, t0) @ beta32
    resid = x2 - tide2
    A = lattice_bytes(x2, delta)
    B_data = lattice_bytes(resid, delta)
    B = B_data + 4 * len(beta)
    L = flight(to_codes(np.round(x2 * 1000)))[0]
    n = len(x2)
    var_explained = 1 - np.var(x1 - design(t1, t0) @ beta) / np.var(x1)
    print(f"test samples {n:,}; delta = {delta * 1000:.1f} mm; tide model explains {100 * var_explained:.1f}% of 2022 variance")
    print(f"L lossless (mm codes):          {L:,} B = {8 * L / n:.3f} bit/sample")
    print(f"A protocol alone:               {A:,} B = {8 * A / n:.3f} bit/sample")
    print(f"B protocol + law (incl. {4 * len(beta)} B of coefficients): {B:,} B = {8 * B / n:.3f} bit/sample")
    saved = 1 - B / A
    print(f"bits per sample the law is worth: {8 * (A - B) / n:.3f}  ({100 * saved:.1f}% of the protocol's bytes)")
    print(f"T1 (law saves >= 20% of the protocol's bytes): {'HOLDS' if saved >= 0.20 else 'REFUTED'}")
    print(f"T2 (protocol + law <= 25% of lossless): {'HOLDS' if B <= 0.25 * L else 'REFUTED'}  (ratio {B / L:.3f})")
    pd.DataFrame([dict(n=n, delta=delta, lossless_B=L, protocol_B=A, law_B=B, law_data_B=B_data,
                       coef_B=4 * len(beta), var_explained=var_explained)]).to_csv(DATA / "law_bits.csv", index=False)


if __name__ == "__main__":
    main()
