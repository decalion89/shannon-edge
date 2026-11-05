#!/usr/bin/env python3
"""Development: the compressor's local information dimension as an anomaly score (TSB-AD-U).

Background (not new): a lossless code's mean cost per sample estimates the entropy rate of the
quantised signal. At resolution eps that rate grows as d*log2(1/eps) for the noise-like part,
where d is Renyi's information dimension; for deterministic chaos it tends to the
Kolmogorov-Sinai entropy (the sum of positive Lyapunov exponents, Pesin), and the slope goes to 0
(Gaspard and Wang's (eps, tau)-entropy, 1993). The slope of the compressor's bits against bits of
resolution is therefore a local, Kraft-calibrated estimate of the signal's dimension.

Per series:
* values are quantised uniformly on the normal prefix's range at B and B-2 bits (B = 8);
* each stream is coded by the adaptive flight profile;
* per sample, slope = (cost_B - cost_{B-2}) / 2, in bits per bit of resolution.

Scores (VUS-PR, benchmark code):
* DIM_mean:  moving mean of the slope over L;
* DIM_dev:   |moving mean - its median on the normal prefix|;
* COST_mean: moving mean of cost_B alone (the entropy rate), for reference.

Usage: tsbad_dimension.py TSB-AD-U.zip TSB-AD-checkout {tuning|eval} out.csv [--jobs N]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_esaadb import surprise  # noqa: E402
from tsbad_reference import moving_mean  # noqa: E402

B = 8
ZIP = None
CODE = None


def quantised_cost(x: np.ndarray, lo: float, hi: float, bits: int) -> np.ndarray:
    q = np.clip(np.floor((x - lo) / (hi - lo) * (1 << bits)) if hi > lo else np.zeros_like(x), 0, (1 << bits) - 1)
    with contextlib.redirect_stderr(io.StringIO()):
        return surprise(pd.Series(q.astype(np.float32)))


def one(name: str):
    sys.path.insert(0, CODE)
    from TSB_AD.evaluation.basic_metrics import generate_curve
    from TSB_AD.utils.slidingWindows import find_length_rank
    z = zipfile.ZipFile(ZIP)
    root = next(n.split("/")[0] for n in z.namelist() if n.endswith(name))
    df = pd.read_csv(io.BytesIO(z.read(f"{root}/{name}"))).dropna()
    data = df.iloc[:, 0:-1].values.astype(float)
    label = df["Label"].astype(int).to_numpy()
    L = int(find_length_rank(data[:, 0].reshape(-1, 1), rank=1))
    train = int(name.split(".")[0].split("_")[-3])
    x = data[:, 0]
    pre = x[: max(train, 2)]
    lo, hi = float(pre.min()), float(pre.max())
    c_hi = quantised_cost(x, lo, hi, B)
    c_lo = quantised_cost(x, lo, hi, B - 2)
    slope = moving_mean((c_hi - c_lo) / 2.0, L)
    base = float(np.median(slope[: max(train, 2)]))
    scores = {"DIM_mean": slope, "DIM_dev": np.abs(slope - base), "COST_mean": moving_mean(c_hi, L)}
    out = {"file": name, "L": L, "n": len(label)}
    for k, v in scores.items():
        v = np.nan_to_num(v)
        a, b = v.min(), v.max()
        v = (v - a) / (b - a) if b > a else np.zeros_like(v)
        out[k] = float(generate_curve(label, v, L, "opt", 250)[7])
    print(name + " " + " ".join(f"{k}={out[k]:.3f}" for k in scores), file=sys.stderr, flush=True)
    return out


def init(zp, code):
    global ZIP, CODE
    ZIP, CODE = zp, code


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zip")
    ap.add_argument("checkout")
    ap.add_argument("split", choices=["tuning", "eval"])
    ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    args = ap.parse_args()
    lst = "TSB-AD-U-" + {"tuning": "Tuning.csv", "eval": "Eva.csv"}[args.split]
    files = pd.read_csv(Path(args.checkout) / "Datasets/File_List" / lst)["file_name"].tolist()
    done = set(pd.read_csv(args.out)["file"]) if Path(args.out).exists() else set()
    zsz = {i.filename.split("/")[-1]: i.file_size for i in zipfile.ZipFile(args.zip).infolist()}
    todo = sorted((f for f in files if f not in done), key=lambda f: zsz.get(f, 0))
    with Pool(args.jobs, initializer=init, initargs=(args.zip, str(Path(args.checkout).resolve()))) as pool:
        for r in pool.imap_unordered(one, todo):
            pd.DataFrame([r]).to_csv(args.out, mode="a", header=not Path(args.out).exists(), index=False)


if __name__ == "__main__":
    main()
