#!/usr/bin/env python3
"""Stage 5 verdict, exactly as pre-registered (bench/results/tsbad_preregistration.md, stage 5 and
its analysis plan, commits 2fed742 and 59b774b). Reads the per-series CSV written by
bench/tsbad_cascade.py and prints every test, pass or fail. Nothing here may be changed after the
evaluation results are seen.

Primary hypotheses (q = 10%, mean VUS-PR over series):
* H8:  hybrid_10 >= 0.75 * subpca
* H9:  hybrid_10 > cascade_10, Wilcoxon signed-rank p < 0.05 (one-sided, greater)
* H10: j2_hybrid_10 >= 0.75 * iforest and j2_hybrid_10 >= 2 * j2_random_10

Analysis plan, applied only if H8 and H9 hold (A fails if any check fails):
* A1: H10 holds (judge independence).
* A2: among datasets with >= 3 series, mean(hybrid_10 - cascade_10) > 0 in >= 60% of them.
* A3: across those datasets, Spearman rho between the gain (hybrid_10 - cascade_10) and the gap
      (subpca - cascade_10) is > 0 with one-sided p < 0.05.
* A4: mean shape_10 does not exceed mean hybrid_10.

Usage: stage5_verdict.py results.csv [--expect 348]
"""

import argparse
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, wilcoxon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--expect", type=int, default=348)
    args = ap.parse_args()
    d = pd.read_csv(args.csv).drop_duplicates("file")
    n = len(d)
    print(f"{n} series (expected {args.expect}){'' if n >= args.expect else '  -- INCOMPLETE, verdict not final'}")
    m = d.mean(numeric_only=True)
    out = {}

    h8 = m.hybrid_10 >= 0.75 * m.subpca
    print(f"H8  hybrid_10 / subpca = {m.hybrid_10:.3f} / {m.subpca:.3f} = {m.hybrid_10 / m.subpca:.3f} (>= 0.75): "
          f"{'HOLDS' if h8 else 'REFUTED'}")
    p9 = wilcoxon(d.hybrid_10, d.cascade_10, alternative="greater").pvalue
    h9 = (m.hybrid_10 > m.cascade_10) and p9 < 0.05
    print(f"H9  hybrid_10 {m.hybrid_10:.3f} vs cascade_10 {m.cascade_10:.3f}, one-sided Wilcoxon p = {p9:.4g}: "
          f"{'HOLDS' if h9 else 'REFUTED'}")
    if "iforest" in d:
        r1 = m.j2_hybrid_10 / m.iforest
        r2 = m.j2_hybrid_10 / m.j2_random_10
        h10 = (r1 >= 0.75) and (r2 >= 2.0)
        print(f"H10 IForest judge: j2_hybrid_10 / iforest = {r1:.3f} (>= 0.75), / j2_random_10 = {r2:.2f} (>= 2): "
              f"{'HOLDS' if h10 else 'REFUTED'}")
    else:
        h10 = False
        print("H10 IForest columns missing: cannot be assessed")
    out.update(H8=h8, H9=h9, H10=h10)

    print("\nAll budgets (share of the ground judge's full score):")
    for q in (5, 10, 20, 30, 50):
        row = f"  q={q:>2}%  Sub-PCA judge: cascade {m[f'cascade_{q}'] / m.subpca:.2f}  hybrid {m[f'hybrid_{q}'] / m.subpca:.2f}" \
              f"  shape {m[f'shape_{q}'] / m.subpca:.2f}  random {m[f'random_{q}'] / m.subpca:.2f}"
        if "iforest" in d:
            row += (f"   IForest judge: cascade {m[f'j2_cascade_{q}'] / m.iforest:.2f}  hybrid {m[f'j2_hybrid_{q}'] / m.iforest:.2f}"
                    f"  random {m[f'j2_random_{q}'] / m.iforest:.2f}")
        print(row)

    d["ds"] = d.file.str.split("_").str[1]
    g = d.groupby("ds").agg(n=("file", "size"), subpca=("subpca", "mean"), cascade=("cascade_10", "mean"),
                            hybrid=("hybrid_10", "mean"), shape=("shape_10", "mean"))
    g["gain"] = g.hybrid - g.cascade
    g["gap"] = g.subpca - g.cascade
    print("\nPer dataset (q = 10%):")
    print(g.round(3).to_string())

    if not (h8 and h9):
        print("\nH8 or H9 refuted: the analysis plan A is not applied. Next mutation (pre-registered): e-value merge.")
        return 0
    big = g[g.n >= 3]
    a1 = h10
    share = float((big.gain > 0).mean()) if len(big) else 0.0
    a2 = share >= 0.60
    rho, prho = spearmanr(big.gain, big.gap) if len(big) >= 3 else (float("nan"), 1.0)
    prho1 = prho / 2 if rho > 0 else 1 - prho / 2
    a3 = (rho > 0) and prho1 < 0.05
    a4 = m.shape_10 <= m.hybrid_10
    print(f"\nA1 judge independence (H10): {'PASS' if a1 else 'FAIL'}")
    print(f"A2 datasets (>= 3 series) with positive gain: {share:.0%} of {len(big)} (>= 60%): {'PASS' if a2 else 'FAIL'}")
    print(f"A3 Spearman(gain, gap) over {len(big)} datasets: rho = {rho:.3f}, one-sided p = {prho1:.4g}: "
          f"{'PASS' if a3 else 'FAIL'}")
    print(f"A4 ablation: shape_10 {m.shape_10:.3f} <= hybrid_10 {m.hybrid_10:.3f}: {'PASS' if a4 else 'FAIL'}")
    print(f"\nVerdict: {'ESTABLISHED' if all((a1, a2, a3, a4)) else 'NOT ESTABLISHED'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
