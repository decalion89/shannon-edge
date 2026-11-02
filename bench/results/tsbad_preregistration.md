# TSB-AD-M confirmation: pre-registration

Written and committed **before** any of the rules below was run on
TSB-AD.

**Why.** The cross-channel corroboration of the windowed e-value rule was
found post hoc on ESA's missions (`esa_chronological.md`): 0.724 → 0.871
on Mission 2 and 0.432 → 0.569 on Mission 1. It needs data that played no
part in its design.

**Data.** TSB-AD-M (Liu and Paparrizos, "The Elephant in the Room:
Towards A Reliable Time-Series Anomaly Detection Benchmark", NeurIPS 2024
D&B). This is the 180-series evaluation list `TSB-AD-M-Eva.csv`, from
many domains.
* The benchmark's metric code: `TSB_AD.evaluation.metrics.get_metrics`.
* Its window: `find_length_rank(data[:, 0], rank=1)`, exactly as
  `benchmark_exp/Run_Detector_M.py` does.

No part of TSB-AD has been used in this project before.

## Scores (fixed; no training, no tuning, no labels)

**Coding.** Per channel, values are coded as in
`bench/anomaly_esaadb.py` (distinct values, merged into 65,536 ordered
bins if more). The flight profile then gives each sample's cost ℓ in
bits, online from the first sample. The series' "training" prefix is
not used for anything but warm-up.
* b = the channel's code width.
* The excess is ℓ − b.

**Windowed e-process.** Per channel, in consecutive blocks of L samples
(L = the benchmark's sliding window, blocks aligned at index 0):
log2 M_n = log2 mean_e Π((1 − e) + e·2^(ℓᵢ − b)), for
e ∈ {2^−1, 2^−4, 2^−8, 2^−12}. This is the rule pre-registered for ESA,
with the 6-hour window replaced by the benchmark's window.

**Scores per time step:**
* **S0** (per-sample): the largest excess over channels.
* **S1** (single): the largest log2 M over channels.
* **S2** (corroborated): the second-largest log2 M over channels (S1 if
  only one channel).

## Hypotheses

* **H1.** Mean VUS-PR of S2 > mean VUS-PR of S1 over the 180 series.
* **H2.** Mean VUS-PR of S2 > 0.313, the best mean VUS-PR in the
  benchmark paper's multivariate table (CNN).
  * Those methods' hyperparameters were tuned on TSB-AD's separate tuning
    set; ours were not tuned at all.
  * The repository's current leaderboard (xLSTMAD 0.392, MMPAD 0.354,
    Time_RCD 0.317) is reported for context.

**Reporting.**
* All three scores, per-dataset breakdowns, and Wilcoxon signed-rank
  tests (S2 vs S1, S2 vs CNN) are reported, whatever they show.
* Nothing above will be changed after the run.
* Any later variant will be labelled post hoc.

## Stage 2: reference-model score, chosen on the tuning set (committed before its evaluation run)

**Why a stage 2.** The stage-1 run was well underway (98 of 180 series)
and S1/S2 were far below the published methods. The diagnosis: the
adaptive compressor habituates inside long anomalies.

That motivated a **reference model** (`bench/tsbad_reference.py`,
`examples/flight_reference_surprise`):
* learn the series' normal prefix (the benchmark's `tr_N`);
* code every later block of L samples with a fresh copy of that state.

Five candidate scores were compared **only on the benchmark's 20 tuning
series** (`TSB-AD-M-Tuning.csv`, none of them in the evaluation list).
Mean VUS-PR (`bench/results/data/tsbad_reference_tuning.csv`):

| Candidate | Mean VUS-PR (20 tuning series) | Mean rank |
|---|---:|---:|
| A_adapt_win (stage-1 S1) | 0.237 | 4.40 |
| B_ref (per-sample reference excess, max over channels) | 0.194 | 4.50 |
| C_ref_win (windowed e-process on reference costs) | 0.290 | 3.60 |
| **D_ref_mean (moving mean of reference excess over L, max over channels)** | **0.313** | **3.55** |
| E_ref_summean (sum over channels of the moving mean) | 0.298 | 3.95 |

**Selected: D_ref_mean**, the best on both criteria. It will be evaluated
once on the 180 evaluation series and reported against:
* stage 1;
* the paper's table (CNN 0.313, OmniAnomaly 0.312, PCA 0.310);
* the leaderboard (xLSTMAD 0.392).

**H3.** D_ref_mean > 0.313 on the evaluation set. Like the published
methods, it uses the tuning set to choose its configuration and the
series' normal prefix. Unlike them, it trains nothing beyond the
compressor's own online learning, and it has no hyperparameter search.
