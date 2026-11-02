#!/usr/bin/env python3
"""Development: an amplitude-free shape channel for the on-board triage, built from the compressor
itself. Each sample is replaced by its ordinal pattern of order D (the rank order of the last D
values: D! symbols, Bandt and Pompe 2002). That symbol stream is coded by the same flight-profile
reference model as the values (examples/flight_reference_surprise: learn the normal prefix, code
each block from a snapshot). Its excess cost is a Kraft-valid "shape surprise". It needs no basis
learned on the ground and only integer comparisons on board.

Triage as in bench/tsbad_cascade.py. Rank windows of L samples by:
* ord_*: the ordinal shape surprise (moving mean over L, max per window);
* ordhyb_*: max(z(compressor change+state score), z(ordinal shape score)).
They are compared with cascade_* (compressor only) and hybrid_* (compressor + ground PCA basis),
judged on the ground by Sub-PCA.

Usage: tsbad_ordinal.py TSB-AD-U.zip TSB-AD-checkout {tuning|eval} out.csv [--jobs N] [--only FILE ...]
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
from tsbad_cascade import QS, onboard_score, shape_residual, zs_  # noqa: E402
from tsbad_reference import moving_mean, reference_cost  # noqa: E402

D = 4  # order of the ordinal patterns: 24 symbols
ZIP = None
CODE = None


def ordinal_codes(x: np.ndarray, d: int = D) -> np.ndarray:
    """Lehmer code of the rank order of (x[i-d+1], ..., x[i]); ties broken by position. The first
    d-1 samples get code 0."""
    n = len(x)
    out = np.zeros(n, dtype=np.int64)
    if n < d:
        return out
    w = np.lib.stride_tricks.sliding_window_view(x, d)
    order = np.argsort(w, axis=1, kind="stable")
    code = np.zeros(len(w), dtype=np.int64)
    for i in range(d):
        smaller = (order[:, i + 1:] < order[:, i:i + 1]).sum(axis=1) if i + 1 < d else 0
        code = code * (d - i) + smaller
    out[d - 1:] = code
    return out


def one(name: str):
    sys.path.insert(0, CODE)
    from TSB_AD.evaluation.basic_metrics import generate_curve
    from TSB_AD.models.PCA import PCA as SubPCA
    from TSB_AD.utils.slidingWindows import find_length_rank
    z = zipfile.ZipFile(ZIP)
    root = next(n.split("/")[0] for n in z.namelist() if n.endswith(name))
    df = pd.read_csv(io.BytesIO(z.read(f"{root}/{name}"))).dropna()
    data = df.iloc[:, 0:-1].values.astype(float)
    label = df["Label"].astype(int).to_numpy()
    L = int(find_length_rank(data[:, 0].reshape(-1, 1), rank=1))
    train = int(name.split(".")[0].split("_")[-3])
    n = len(label)
    x = data[:, 0]
    f = onboard_score(x, train, L)
    oc = ordinal_codes(x).astype(float)
    b = max(1, (len(np.unique(oc)) - 1).bit_length())
    o = moving_mean(reference_cost(oc, train, L) - b, L)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        clf = SubPCA(slidingWindow=find_length_rank(data, rank=1), n_components=None)
        clf.fit(data)
        g = np.nan_to_num(np.asarray(clf.decision_scores_, dtype=float).ravel())
    g = (g - g.min()) / (g.max() - g.min()) if g.max() > g.min() else np.zeros(n)

    def vus(v):
        return float(generate_curve(label, v, L, "opt", 250)[7])
    blocks = np.arange(n) // max(L, 1)
    nb = blocks.max() + 1
    fb = pd.Series(f).groupby(blocks).max().to_numpy()
    ob = pd.Series(o).groupby(blocks).max().to_numpy()
    rb = shape_residual(x, train, L, blocks, nb)
    ranks = {"cascade": fb, "ord": ob, "ordhyb": np.maximum(zs_(fb), zs_(ob)),
             "hybrid": np.maximum(zs_(fb), zs_(rb))}
    out = {"file": name, "L": L, "n": n, "subpca": vus(g)}
    for q in QS:
        k = max(1, int(round(q * nb)))
        for key, r in ranks.items():
            keep = np.zeros(nb, bool)
            keep[np.argsort(-r)[:k]] = True
            out[f"{key}_{int(q * 100)}"] = vus(np.where(keep[blocks], g, 0.0))
    print(name + " " + " ".join(f"{k}={v:.3f}" for k, v in out.items() if k.endswith("_10") or k == "subpca"),
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
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--skip", nargs="*", default=[])
    args = ap.parse_args()
    lst = "TSB-AD-U-" + {"tuning": "Tuning.csv", "eval": "Eva.csv"}[args.split]
    files = pd.read_csv(Path(args.checkout) / "Datasets/File_List" / lst)["file_name"].tolist()
    if args.only:
        files = [f for f in files if f in set(args.only)]
    done = set(pd.read_csv(args.out)["file"]) if Path(args.out).exists() else set()
    zsz = {i.filename.split("/")[-1]: i.file_size for i in zipfile.ZipFile(args.zip).infolist()}
    todo = sorted((f for f in files if f not in done and f not in args.skip), key=lambda f: zsz.get(f, 0))
    with Pool(args.jobs, initializer=init, initargs=(args.zip, str(Path(args.checkout).resolve()))) as pool:
        for r in pool.imap_unordered(one, todo):
            pd.DataFrame([r]).to_csv(args.out, mode="a", header=not Path(args.out).exists(), index=False)


if __name__ == "__main__":
    main()
