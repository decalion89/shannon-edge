#!/usr/bin/env python3
"""On-board triage + ground analysis, a cascade (TSB-AD-U, development).

The question: how much of the downlink does the ground need for a
shape-aware detector to keep its accuracy, if the on-board compressor
chooses what to send?

Per series:
* on board: F_max_z, the change+state score selected in stage 3
  (bench/tsbad_reference.py), computed per sample. Windows of L samples
  are ranked by their largest F, and the top fraction q is "downlinked";
* on the ground: Sub-PCA, the best published method on TSB-AD-U (benchmark
  code: the body of run_Sub_PCA with its default periodicity, i.e.
  models.PCA with slidingWindow = find_length_rank(data, rank=1)). It scores the whole
  series as in the benchmark, but only downlinked windows keep their
  scores; the rest are set to the minimum (the ground saw nothing there);
* control: the same fraction q of windows, chosen at random (seed 0).

Pass/fail criterion, fixed before the run: at q = 20%, the cascade keeps
at least 90% of full Sub-PCA's mean VUS-PR, and beats the random control.

Usage: tsbad_cascade.py TSB-AD-U.zip TSB-AD-checkout {tuning|eval} out.csv [--jobs 4]
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
from tsbad_reference import moving_mean, reference_cost  # noqa: E402

ZIP = None
CODE = None
QS = (0.05, 0.10, 0.20, 0.30, 0.50)


def onboard_score(x: np.ndarray, train: int, L: int) -> np.ndarray:
    n = len(x)
    b = max(1, (min(len(np.unique(x.astype(np.float32))), 65536) - 1).bit_length())
    with contextlib.redirect_stderr(io.StringIO()):
        ad = surprise(pd.Series(x)) - b
    A = window_evidence(np.arange(n, dtype=np.int64) * 3600 * 10**9, ad, float(L))[0]
    D = moving_mean(reference_cost(x, train, L) - b, L)

    def zs(v):
        v = np.nan_to_num(v, nan=0.0, posinf=1e6, neginf=-1e6)
        sd = v.std()
        return (v - v.mean()) / sd if sd > 0 else np.zeros_like(v)
    return np.maximum(zs(A), zs(D))


def one(name: str):
    sys.path.insert(0, CODE)
    from TSB_AD.evaluation.basic_metrics import generate_curve
    from TSB_AD.models.PCA import PCA as SubPCA  # run_Sub_PCA, without the wrapper's torch import
    from TSB_AD.utils.slidingWindows import find_length_rank
    z = zipfile.ZipFile(ZIP)
    root = next(n.split("/")[0] for n in z.namelist() if n.endswith(name))
    df = pd.read_csv(io.BytesIO(z.read(f"{root}/{name}"))).dropna()
    data = df.iloc[:, 0:-1].values.astype(float)
    label = df["Label"].astype(int).to_numpy()
    L = int(find_length_rank(data[:, 0].reshape(-1, 1), rank=1))
    train = int(name.split(".")[0].split("_")[-3])
    n = len(label)
    f = onboard_score(data[:, 0], train, L)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        clf = SubPCA(slidingWindow=find_length_rank(data, rank=1), n_components=None)
        clf.fit(data)
        g = np.asarray(clf.decision_scores_, dtype=float).ravel()
    g = np.nan_to_num(g)
    g = (g - g.min()) / (g.max() - g.min()) if g.max() > g.min() else np.zeros(n)

    def vus(v):
        return float(generate_curve(label, v, L, "opt", 250)[7])
    blocks = np.arange(n) // max(L, 1)
    nb = blocks.max() + 1
    bmax = pd.Series(f).groupby(blocks).max().to_numpy()
    rng = np.random.default_rng(0)
    rand_order = rng.permutation(nb)
    out = {"file": name, "L": L, "n": n, "subpca": vus(g)}
    for q in QS:
        k = max(1, int(round(q * nb)))
        keep = np.zeros(nb, bool)
        keep[np.argsort(-bmax)[:k]] = True
        out[f"cascade_{int(q * 100)}"] = vus(np.where(keep[blocks], g, 0.0))
        keep_r = np.zeros(nb, bool)
        keep_r[rand_order[:k]] = True
        out[f"random_{int(q * 100)}"] = vus(np.where(keep_r[blocks], g, 0.0))
        # Fraction of anomalous samples inside downlinked windows.
        out[f"anom_cov_{int(q * 100)}"] = float(label[keep[blocks]].sum() / max(label.sum(), 1))
    print(name + " " + " ".join(f"{k}={v:.3f}" for k, v in out.items() if k.startswith(("subpca", "cascade_20", "random_20"))),
          file=sys.stderr, flush=True)
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
    todo = sorted((f for f in files if f not in done), key=lambda f: -zsz.get(f, 0))
    with Pool(args.jobs, initializer=init, initargs=(args.zip, str(Path(args.checkout).resolve()))) as pool:
        for r in pool.imap_unordered(one, todo):
            pd.DataFrame([r]).to_csv(args.out, mode="a", header=not Path(args.out).exists(), index=False)


if __name__ == "__main__":
    main()
