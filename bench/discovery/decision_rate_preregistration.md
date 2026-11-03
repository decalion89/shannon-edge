# Can the decision's bandwidth need be predicted before transmitting? Pre-registration

Committed before any feature below is computed on any series.

## Question

For a series, how much of the downlink does the ground's decision need?
Can that be predicted from the **normal prefix alone**, with no labels
and no anomaly, before anything is transmitted?

A yes would be the first measurable piece of a "law of decision
information": the bits a decision needs depend on measurable structure
of the normal signal.

## Target (from data already computed in stage 4, never used for this question)

`bench/results/data/tsbad_cascade_{tuning,eval}.csv`: the share of
Sub-PCA's VUS-PR kept when the compressor chooses q of the windows,
for q ∈ {5, 10, 20, 30, 50}%.

**Target per series:**
AUR = mean over the five q of clip(cascade_q / subpca, 0, 1.5).
* Only series with subpca ≥ 0.05 are used, because the ratio is
  meaningless when the ground detector itself finds nothing.
* High AUR means a small share of the link already carries the
  decision.

## Features (fixed now; computed only on the normal prefix, `tr_N`)

* **f1 — entropy rate:** mean flight-profile cost in bits per sample,
  values quantised to 8 bits on the prefix range.
* **f2 — evidence spread:** the 99th minus the 50th percentile of the
  windowed (length L) mean cost on the prefix, in bits. It measures how
  much the normal signal's own surprise varies.
* **f3 — repeat rate:** the share of samples equal to the previous one.
* **f4 — log2(L):** the benchmark's period estimate.

**Model:** ordinary least squares of AUR on [1, f1, f2, f3, f4], fitted
on the tuning series only.

## Test (evaluation series, run once)

* **Success:** Spearman ρ between predicted and actual AUR is ≥ 0.30,
  one-sided p < 0.01.
* **Baseline:** the model must beat log2(series length) alone, i.e.
  have a higher ρ than that single trivial feature.

If either fails, the conjecture is refuted for these data, and that is
reported.

## Result (run once, `bench/discovery/decision_rate.py`)

The tuning fit uses 32 series with subpca ≥ 0.05:
AUR = 0.953 + 0.030·f1 − 0.139·f2 + 0.215·f3 − 0.027·f4.

On the evaluation set (236 series with subpca ≥ 0.05):

| | Spearman ρ with the actual AUR |
|---|---:|
| **Pre-registered model** | **0.129** (one-sided p = 0.024) |
| Baseline: log2(length) | 0.075 |

**Refuted.** ρ = 0.129 is below the pre-set 0.30, and p = 0.024 is above
0.01. It does beat the trivial baseline, but too weakly to count.

**Post hoc, not a result.** The entropy rate of the normal prefix (f1)
alone correlates **negatively** with AUR: ρ = −0.205 on the evaluation
set, while on tuning it was −0.075.
* Noisier normal signals leave less room for the compressor's triage:
  their own surprise dilutes the anomaly's.
* The fitted model gave f1 the wrong sign, because 32 tuning series are
  too few.
* This is a hypothesis for a new pre-registration on other data, not a
  finding.

Per-series values: `bench/results/data/decision_rate_{tuning,eval}.csv`.
