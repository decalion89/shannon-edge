#!/usr/bin/env python3
"""TSB-AD-M confirmation of the windowed e-value rule and its cross-channel
corroboration (pre-registered in bench/results/tsbad_preregistration.md).

Per series of the benchmark's evaluation list:
* every channel is coded with the flight profile, online from the first
  sample, with no training; the excess is cost - b bits;
* the windowed mixture e-process is restarted every L samples, where L is
  the benchmark's own sliding window
  (find_length_rank(data[:, 0], rank=1), as benchmark_exp/Run_Detector_M.py);
* S0 = max over channels of the excess;
* S1 = max over channels of log2 M;
* S2 = second-largest over channels of log2 M.
VUS-PR and AUC-PR come from the benchmark's own code (generate_curve and
basic_metricor, as get_metrics computes them), on scores min-max scaled to
[0, 1].

Usage:
    cargo build --release --example flight_surprise
    pip install statsmodels portion
    python3 bench/tsbad_eval.py TSB-AD-M.zip TSB-AD-checkout out.csv [--jobs 4]
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
from esa_chronological import window_evidence  # noqa: E402

ZIP = None
CODE = None


def scores(data: np.ndarray, L: int) -> dict[str, np.ndarray]:
    n, d = data.shape
    ex = np.empty((d, n))
    lm = np.empty((d, n))
    fake_ts = np.arange(n, dtype=np.int64) * 3600 * 10**9  # one "hour" per sample: blocks of L samples
    for c in range(d):
        s = pd.Series(data[:, c], name=f"c{c}")
        with contextlib.redirect_stderr(io.StringIO()):
            cost = surprise(s)
        b = max(1, (min(len(np.unique(data[:, c].astype(np.float32))), 65536) - 1).bit_length())
        ex[c] = cost - b
        lm[c], _ = window_evidence(fake_ts, ex[c], float(L))
    s0 = ex.max(axis=0)
    s1 = lm.max(axis=0)
    s2 = np.sort(lm, axis=0)[-2] if d >= 2 else s1
    return {"S0": s0, "S1": s1, "S2": s2}


def one(name: str):
    sys.path.insert(0, CODE)
    from TSB_AD.evaluation.basic_metrics import basic_metricor, generate_curve
    from TSB_AD.utils.slidingWindows import find_length_rank
    z = zipfile.ZipFile(ZIP)
    df = pd.read_csv(io.BytesIO(z.read(f"TSB-AD-M/{name}"))).dropna()
    data = df.iloc[:, 0:-1].values.astype(float)
    label = df["Label"].astype(int).to_numpy()
    L = int(find_length_rank(data[:, 0].reshape(-1, 1), rank=1))
    out = {"file": name, "L": L, "n": len(label), "d": data.shape[1]}
    for k, v in scores(data, L).items():
        v = np.nan_to_num(v, nan=0.0, posinf=1e6, neginf=-1e6)
        lo, hi = v.min(), v.max()
        v = (v - lo) / (hi - lo) if hi > lo else np.zeros_like(v)
        _, _, _, _, _, _, _, vus_pr = generate_curve(label, v, L, "opt", 250)
        out[f"{k}_VUS-PR"] = float(vus_pr)
        out[f"{k}_AUC-PR"] = float(basic_metricor().metric_PR(label, v))
    print(f"{name}: " + " ".join(f"{k}={out[f'{k}_VUS-PR']:.3f}" for k in ("S0", "S1", "S2")), file=sys.stderr, flush=True)
    return out


def init(zp, code):
    global ZIP, CODE
    ZIP, CODE = zp, code


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zip")
    ap.add_argument("checkout")
    ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    args = ap.parse_args()
    files = pd.read_csv(Path(args.checkout) / "Datasets/File_List/TSB-AD-M-Eva.csv")["file_name"].tolist()
    done = set(pd.read_csv(args.out)["file"]) if Path(args.out).exists() else set()
    todo = [f for f in files if f not in done]
    # Longest first, for load balance.
    zsz = {i.filename.split("/")[-1]: i.file_size for i in zipfile.ZipFile(args.zip).infolist()}
    todo.sort(key=lambda f: -zsz.get(f, 0))
    with Pool(args.jobs, initializer=init, initargs=(args.zip, str(Path(args.checkout).resolve()))) as pool:
        for r in pool.imap_unordered(one, todo):
            pd.DataFrame([r]).to_csv(args.out, mode="a", header=not Path(args.out).exists(), index=False)


if __name__ == "__main__":
    main()
