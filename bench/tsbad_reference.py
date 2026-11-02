#!/usr/bin/env python3
"""TSB-AD-M: reference-model scores (post hoc, developed on the benchmark's
20 tuning series only, then evaluated once on the 180 evaluation series).

Diagnosis that motivated it (from the pre-registered run, bench/tsbad_eval.py):
the adaptive compressor habituates inside a long anomaly. Its cost rises at
the onset and falls back while the anomalous state persists, and VUS-PR
rewards scores that stay high over the whole labelled segment.

Reference model (examples/flight_reference_surprise): one flight session
learns the series' normal prefix (the benchmark's "tr_N", the training
part its semi-supervised methods use). Every later block of L samples is
coded by a fresh copy of that state. Each sample's cost is still a valid
sequential code length (Kraft), but a persistent anomalous state stays
costly.

Candidate scores, with excess = cost - b per channel:
* A_adapt_win:   the adaptive windowed e-process, max over channels (S1 of
                 the pre-registered run);
* B_ref:         reference excess, max over channels;
* C_ref_win:     the windowed e-process on reference costs, max over
                 channels;
* D_ref_mean:    moving mean of the reference excess over L samples
                 (causal), max over channels;
* E_ref_summean: sum over channels of the moving mean of the reference
                 excess.

Usage: tsbad_reference.py TSB-AD-M.zip TSB-AD-checkout {tuning|eval} out.csv [--jobs 4]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import zipfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_esaadb import surprise  # noqa: E402
from esa_chronological import window_evidence  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ZIP = None
CODE = None


def codes_of(x: np.ndarray) -> np.ndarray:
    uniq, codes = np.unique(x.astype(np.float32), return_inverse=True)
    if len(uniq) > 65536:
        codes = codes.astype(np.int64) * 65536 // len(uniq)
    return codes.astype("<u2")


def reference_cost(x: np.ndarray, train: int, block: int) -> np.ndarray:
    with tempfile.TemporaryDirectory() as t:
        cp, op = Path(t) / "c.u16", Path(t) / "o.u32"
        codes_of(x).tofile(cp)
        subprocess.run([str(ROOT / "target/release/examples/flight_reference_surprise"), str(cp), str(op),
                        str(train), str(block)], check=True, capture_output=True)
        return np.fromfile(op, dtype="<u4").astype(np.float64) / 256.0


def moving_mean(v: np.ndarray, L: int) -> np.ndarray:
    c = np.cumsum(np.r_[0.0, v])
    i = np.arange(1, len(v) + 1)
    lo = np.maximum(0, i - L)
    return (c[i] - c[lo]) / (i - lo)


def one(name: str):
    sys.path.insert(0, CODE)
    from TSB_AD.evaluation.basic_metrics import basic_metricor, generate_curve
    from TSB_AD.utils.slidingWindows import find_length_rank
    z = zipfile.ZipFile(ZIP)
    df = pd.read_csv(io.BytesIO(z.read(f"TSB-AD-M/{name}"))).dropna()
    data = df.iloc[:, 0:-1].values.astype(float)
    label = df["Label"].astype(int).to_numpy()
    L = int(find_length_rank(data[:, 0].reshape(-1, 1), rank=1))
    train = int(name.split(".")[0].split("_")[-3])
    n, d = data.shape
    fake_ts = np.arange(n, dtype=np.int64) * 3600 * 10**9
    A = np.full(n, -np.inf)
    B = np.full(n, -np.inf)
    C = np.full(n, -np.inf)
    D = np.full(n, -np.inf)
    E = np.zeros(n)
    for c in range(d):
        x = data[:, c]
        b = max(1, (min(len(np.unique(x.astype(np.float32))), 65536) - 1).bit_length())
        with contextlib.redirect_stderr(io.StringIO()):
            ad = surprise(pd.Series(x)) - b
        A = np.maximum(A, window_evidence(fake_ts, ad, float(L))[0])
        rf = reference_cost(x, train, L) - b
        B = np.maximum(B, rf)
        C = np.maximum(C, window_evidence(fake_ts, rf, float(L))[0])
        mm = moving_mean(rf, L)
        D = np.maximum(D, mm)
        E += mm
    out = {"file": name, "L": L, "n": n, "d": d, "train": train}
    for k, v in (("A_adapt_win", A), ("B_ref", B), ("C_ref_win", C), ("D_ref_mean", D), ("E_ref_summean", E)):
        v = np.nan_to_num(v, nan=0.0, posinf=1e6, neginf=-1e6)
        lo, hi = v.min(), v.max()
        v = (v - lo) / (hi - lo) if hi > lo else np.zeros_like(v)
        out[k] = float(generate_curve(label, v, L, "opt", 250)[7])
    print(name + " " + " ".join(f"{k}={out[k]:.3f}" for k in out if "_" in k and k[0].isupper()), file=sys.stderr,
          flush=True)
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
    lst = {"tuning": "TSB-AD-M-Tuning.csv", "eval": "TSB-AD-M-Eva.csv"}[args.split]
    files = pd.read_csv(Path(args.checkout) / "Datasets/File_List" / lst)["file_name"].tolist()
    done = set(pd.read_csv(args.out)["file"]) if Path(args.out).exists() else set()
    zsz = {i.filename.split("/")[-1]: i.file_size for i in zipfile.ZipFile(args.zip).infolist()}
    todo = sorted((f for f in files if f not in done), key=lambda f: -zsz.get(f, 0))
    with Pool(args.jobs, initializer=init, initargs=(args.zip, str(Path(args.checkout).resolve()))) as pool:
        for r in pool.imap_unordered(one, todo):
            pd.DataFrame([r]).to_csv(args.out, mode="a", header=not Path(args.out).exists(), index=False)


if __name__ == "__main__":
    main()
