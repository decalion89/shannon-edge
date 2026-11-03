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

## Stage 3: TSB-AD-U, combination of change and state detection (committed before its evaluation run)

**Why.** On TSB-AD-M, the adaptive score (A, change detection) and the
reference score (D, state detection) won on different datasets. Three
combinations were added (`bench/tsbad_reference.py`):
* F_max_z: max of their per-series z-scores;
* G_mean_rank: mean of their percentile ranks;
* H_max_rank: max of their percentile ranks.

**Data never used before:** TSB-AD-U, the univariate collection.
Candidates were compared **only on its 47 tuning series**
(`TSB-AD-U-Tuning.csv`; `bench/results/data/tsbad_u_tuning.csv`):

| Candidate | Mean VUS-PR (47 tuning series) | Mean rank |
|---|---:|---:|
| A_adapt_win | 0.249 | 5.24 |
| B_ref | 0.149 | 6.34 |
| C_ref_win | 0.241 | **4.57** |
| D_ref_mean | 0.170 | 6.07 |
| **F_max_z** | **0.252** | 5.01 |
| G_mean_rank | 0.196 | 5.47 |
| H_max_rank | 0.218 | 5.21 |

**Selected: F_max_z**, by the criterion used in stage 2: best mean
VUS-PR, the benchmark's own ranking measure.
* Its margin over A is tiny (0.252 vs 0.249).
* The mean-rank criterion would have picked C_ref_win.
* All candidates are reported on the evaluation set.

**Hypotheses for the single evaluation run** (TSB-AD-U-Eva, against
`uni_mergedTable_VUS-PR.csv`):
* **H4.** F_max_z > A_adapt_win in mean VUS-PR.
* **H5.** F_max_z > 0.423, the best published mean (Sub-PCA).

## Stage 4: on-board triage cascade on TSB-AD-U (committed before its evaluation run)

**Setup.** As developed on the 48 tuning series (`tsbad.md`,
"on-board triage + ground Sub-PCA"; `bench/tsbad_cascade.py`, unchanged):
* on board, the compressor's change+state score F_max_z ranks windows
  of L samples, and the top q are downlinked;
* on the ground, Sub-PCA keeps its scores only on downlinked windows;
* control: the same q of windows, chosen at random (seed 0).

The 90% criterion set before the development run failed there (85% at
q = 20%). The criterion below is new and is stated as such.

**Primary budget: q = 10%** (the others are reported).

* **H6.** At q = 10%, the cascade keeps ≥ 75% of full Sub-PCA's mean
  VUS-PR on TSB-AD-U-Eva.
* **H7.** At q = 10%, the cascade keeps ≥ 2x the random control's mean
  VUS-PR.

It is refuted if either fails. The full Sub-PCA is computed by our run of
the benchmark's model code and is also checked against the published
`uni_mergedTable_VUS-PR.csv`.

## Stage 5: hybrid on-board triage (compressor + ground-learned shape score), committed before its evaluation run

**Development** (48 tuning series, `bench/results/data/tsbad_hybrid_tuning.csv`).
Share of full Sub-PCA's mean VUS-PR kept:

| q | compressor (stage 4) | shape (PCA basis from the normal prefix) | **hybrid max(z, z)** | random |
|---:|---:|---:|---:|---:|
| 5% | 72% | 82% | **85%** | 26% |
| 10% | 82% | 88% | **99%** | 28% |
| 20% | 85% | 84% | **100%** | 36% |

* Hybrid vs compressor: Wilcoxon p = 0.002 (q = 10%), 0.034 (20%).
* The shape score alone does not beat the compressor (p = 0.41); the
  combination does.

**Known risk.** The ground judge, Sub-PCA, is itself a PCA of
subsequences, so a PCA shape score may agree with it for that reason
alone. A second judge from a different family is therefore added:
IForest as the benchmark runs it (n_estimators = 200, window 100;
unseeded, so it carries a little run-to-run noise).

**Hypotheses** (TSB-AD-U-Eva, the same 348 series as stage 4, q = 10%,
mean VUS-PR):
* **H8.** hybrid keeps ≥ 75% of full Sub-PCA.
* **H9.** hybrid > compressor-only triage, Wilcoxon p < 0.05.
* **H10** (judge independence). Judged by IForest, hybrid keeps ≥ 75% of
  full IForest and ≥ 2x the random windows.

All are reported whatever they show. `bench/tsbad_cascade.py` is not
changed after this commit.

## Stage 5, analysis plan for after the run (committed while the run is in progress, before H8–H10 are computed)

At commit time 40 of 348 series were done. H8–H10 have not been
computed on them. The following is fixed now.

**A. If H8 and H9 hold** (the hybrid works), four checks decide between
"a real geometric effect" and "agreement with the judge, or luck":
1. **Judge independence.** H10, already pre-registered: the gain must
   survive with IForest as the ground judge.
2. **Consistency across datasets, not just series.** Among datasets
   with ≥ 3 series, the mean of (hybrid_10 − cascade_10) must be
   positive in ≥ 60% of them (sign test over datasets). A gain carried
   by one large dataset is not a law.
3. **The predicted mechanism.** If the shape channel recovers what
   the compressor misses, then across datasets the gain
   (hybrid_10 − cascade_10) must correlate positively with the gap
   (subpca − cascade_10): Spearman ρ > 0, one-sided p < 0.05. No
   correlation would mean the gain does not come from shape.
4. **Ablation.** shape_10 alone must not exceed hybrid_10 (the
   combination, not the PCA alone, is the claim). If shape alone is as
   good, the compressor adds nothing to triage.

A fails if any of 1–4 fails, and the claim is then reported as not
established.

**B. If H8 or H9 fails, the next mutation (stated now).** Replace the
max of z-scores, which needs a per-series standardisation, with an
**e-value merge**.
* Each channel's window score is turned into a conformal e-value
  against the normal prefix's windows.
* The channels are merged by their **arithmetic mean**, the essentially
  unique symmetric e-merging function that stays valid under arbitrary
  dependence (Vovk and Wang, "E-values: calibration, combination and
  applications", Ann. Statist. 2021).

It keeps the Kraft/Ville guarantee of the rest of the project and has no
per-series tuning. It would be developed on the 48 tuning series and
pre-registered on data not used for triage (TSB-AD-M evaluation series).
