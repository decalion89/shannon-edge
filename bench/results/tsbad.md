# TSB-AD-M: the pre-registered confirmation fails

Pre-registration: `tsbad_preregistration.md` (commit 6769a30). Script:
`bench/tsbad_eval.py` (commit bd107c1). Per-series scores:
`bench/results/data/tsbad_stage1.csv`.

Benchmark: TSB-AD-M (Liu and Paparrizos, NeurIPS 2024 D&B), with its 180
evaluation series, its window (`find_length_rank`) and its VUS-PR code.
The published methods' values come from the repository's
`benchmark_exp/benchmark_eval_results/multi_mergedTable_VUS-PR.csv`.
Their hyperparameters were tuned on the benchmark's tuning set; ours were
not tuned and nothing was trained.

## Stage 1 result (all 180 series)

| Score | Mean VUS-PR | Rank among the 23 published + ours |
|---|---:|---:|
| CNN (best published in the table) | 0.313 | 1 |
| OmniAnomaly / PCA / LSTMAD / USAD | 0.312 / 0.310 / 0.307 / 0.304 | |
| IForest | 0.203 | |
| **S1** (windowed e-process, max over channels) | **0.190** | 18 of 26 |
| HBOS | 0.190 | |
| **S2** (second-largest channel: corroboration) | 0.171 | 23 of 26 |
| **S0** (per-sample excess) | 0.134 | 25 of 26 |
| AnomalyTransformer | 0.118 | 26 |

* **H1 (S2 > S1): refuted.** S2's mean is lower: 0.171 vs 0.190
  (Wilcoxon p = 0.076, no significant difference in either direction).
  Cross-channel corroboration, found post hoc on ESA Mission 2, does
  **not** generalise.
* **H2 (S2 > 0.313): refuted.** Wilcoxon S2 vs CNN, p = 3e-17.
* The windowed e-process does improve on the per-sample score here too:
  0.190 vs 0.134.

## Per dataset

| Dataset | Series | S1 | S2 | CNN | PCA | Best published |
|---|---:|---:|---:|---:|---:|---:|
| CATSv2 | 5 | **0.168** | 0.058 | 0.082 | 0.118 | 0.132 |
| GECCO | 1 | 0.205 | **0.278** | 0.033 | 0.202 | 0.202 |
| TAO | 11 | 0.787 | 0.795 | 0.998 | 1.000 | 1.000 |
| Exathlon | 25 | 0.306 | 0.336 | 0.681 | 0.949 | 0.949 |
| SMD | 20 | 0.196 | 0.230 | 0.353 | 0.364 | 0.364 |
| MSL | 14 | 0.220 | 0.139 | 0.352 | 0.149 | 0.435 |
| SMAP | 25 | 0.161 | 0.051 | 0.191 | 0.093 | 0.380 |
| SVDB | 28 | 0.121 | 0.104 | 0.186 | 0.112 | 0.352 |
| MITDB | 11 | 0.043 | 0.035 | 0.140 | 0.065 | 0.140 |
| GHL | 23 | 0.009 | 0.009 | 0.024 | 0.012 | 0.065 |
| OPPORTUNITY | 7 | 0.041 | 0.043 | 0.158 | 0.299 | 0.299 |
| others (1–4 series each) | 10 | | | | | |

The compressor's surprise beats every published method on CATSv2 (S1)
and GECCO (S2). It is far behind on long-anomaly datasets (Exathlon, SWaT,
OPPORTUNITY) and on ECG (MITDB, SVDB).

## Diagnosis: habituation

The adaptive model learns the anomalous state while it is still going on.
Its cost rises at the onset and falls back afterwards, whereas VUS-PR
rewards a score that stays high over the whole labelled segment. This is
the same mechanism behind:
* the onset concentration measured on ESA
  (`bench/analysis/anomaly_information.py`);
* the invisibility of Mission 1's recurring class_7.

Stage 2 (`tsbad_preregistration.md`) replaces the adaptive model with a
reference snapshot learned on the normal prefix. It was chosen on the 20
tuning series and is evaluated once on these 180.

## Stage 2 result: the reference-model score (chosen on the tuning set, run once)

Per-series scores: `bench/results/data/tsbad_stage2.csv`.

| Score | Mean VUS-PR (180 series) | Rank among the 23 published + ours |
|---|---:|---:|
| CNN | 0.313 | 1 |
| OmniAnomaly / PCA / LSTMAD / USAD | 0.312 / 0.310 / 0.307 / 0.304 | 2–5 |
| AutoEncoder / KMeansAD | 0.295 / 0.295 | 6–7 |
| **D_ref_mean** (selected on the tuning set) | **0.275** | **8 of 25** |
| CBLOF / MCD / OCSVM / Donut | 0.273 / 0.271 / 0.265 / 0.260 | |
| S1 (stage 1, adaptive) | 0.190 | |

Reported, not selected:
* E_ref_summean 0.296;
* C_ref_win 0.267;
* A_adapt_win 0.190;
* B_ref 0.152.

* **H3 (D_ref_mean > 0.313): refuted.** D_ref_mean is below CNN on 110
  of 180 series (Wilcoxon p = 0.0007).
* **The habituation diagnosis is confirmed.** Removing habituation
  raises the mean from 0.190 to 0.275 (p = 0.0008), and from 18th to
  8th place.
  * Exathlon: 0.306 → 0.890.
  * SVDB (ECG): 0.121 → 0.211, above every published method's mean
    except the best (0.352).
  * Daphnet: 0.466, above every published method (best 0.340); a
    single series.
* **The adaptive and the reference models are complementary.** The
  adaptive model wins on CATSv2 (0.168, best of all) and GECCO (0.205).
  There the reference model falls to 0.036. Change detection and state
  detection are different questions.
* Nothing here is trained beyond the compressor's own online learning on
  the normal prefix. There is no hyperparameter search; one choice was
  made, on 20 tuning series.

**Next, not yet run.** Combine the adaptive and the reference scores,
with the combination chosen on the tuning set only. It must then be
tested on data not used so far, for example TSB-AD-U.

## Stage 3 result: TSB-AD-U, change + state combination (chosen on its tuning set, run once)

Per-series scores: `bench/results/data/tsbad_u_eval.csv`.
* 348 of the 350 evaluation series. Two Stock series (155, 165) did not
  finish within 20 min in the benchmark's VUS-PR code and are left out.
* Published values are compared on the same 348 series. On all 350,
  Sub-PCA's mean is 0.423.

| Score | Mean VUS-PR (348 series) | Rank among the 32 published + ours |
|---|---:|---:|
| Sub-PCA (best published) | 0.420 | 1 |
| KShapeAD / POLY / Series2Graph / MOMENT (FT) | 0.398 / 0.387 / 0.385 / 0.382 | |
| MatrixProfile / CNN / LSTMAD | 0.346 / 0.339 / 0.321 | |
| TimesFM / IForest / OmniAnomaly | 0.296 / 0.294 / 0.287 | |
| **F_max_z** (selected on the tuning set) | **0.269** | **18 of 33** |
| Lag-Llama / Chronos (zero-shot foundation models) | 0.269 / 0.268 | |
| TimesNet / AutoEncoder / TranAD | 0.258 / 0.257 / 0.253 | |
| A_adapt_win (adaptive alone) | 0.219 | |

Reported, not selected:
* C_ref_win 0.283;
* H_max_rank 0.241;
* D_ref_mean 0.237;
* G_mean_rank 0.223;
* B_ref 0.172.

* **H4 (F > A): holds.** 0.269 vs 0.219, Wilcoxon p = 0.027. Adding
  state detection to change detection helps on data never used before.
* **H5 (F > 0.423): refuted.** 0.269 vs Sub-PCA 0.420, p = 7e-11.
* The training-free compressor ties the zero-shot foundation models
  Lag-Llama and Chronos. It stays behind subsequence methods (Sub-PCA,
  KShapeAD, Series2Graph, MatrixProfile), which compare whole shapes.
  * Its largest losses are on shape anomalies: OPPORTUNITY 0.050 vs
    0.914, NEK 0.154 vs 0.905, SVDB, MITDB.
  * It beats every published mean on no dataset.
  * On SMD (0.478) it is above Sub-PCA (0.449), but MOMENT (FT) is
    better (0.750).

## What the three TSB-AD stages show

1. **Habituation is real and costs a lot.** Correcting it helped on all
   three collections where it was tested: ESA, TSB-AD-M and TSB-AD-U.
2. **Corroboration across channels does not generalise** beyond ESA
   Mission 2.
3. **The remaining gap is shape.** A per-sample predictive code does not
   see an abnormal subsequence made of normal-looking steps. Methods that
   compare subsequences do.

   The same blind spot explains:
   * ESA Mission 1's class_7;
   * MSL and OPPORTUNITY here.

   Closing it means adding subsequence memory, a match model, to the
   flight profile. Subsequence methods already exist, so that would not
   be new.
4. **Where the compressor stands.** It is a training-free, onboard,
   bit-exact by-product of compression. It is mid-table on TSB-AD,
   level with zero-shot foundation models. It ranks first on ESA
   Mission 2's whole-mission protocol, with a bounded false-alarm rate
   on its per-sample and windowed rules.

## Development only: does the general model's match model see shapes? No

**Hypothesis.** The general sedge model has a match model that follows
the longest earlier repeat. It should predict periodic data almost
perfectly and pay when a shape breaks, closing the shape gap.

**Test** (`bench/tsbad_cm.py`). On TSB-AD-U's **47 tuning series only**:
* values quantised to 8 bits on the normal prefix's range;
* `byte_costs` at MEM_BITS 22.
The evaluation set was not touched.

| Score (47 tuning series) | Mean VUS-PR |
|---|---:|
| CM_raw (general model, per-sample cost) | 0.153 |
| CM_mean (moving mean over L) | 0.143 |
| CM_max (moving max over L) | 0.143 |
| flight profile, adaptive windowed (A) | 0.249 |
| flight, change + state (F) | 0.252 |

**Result: refuted.** The general model is worse overall.
* It wins on a few datasets: NEK 0.665 (moving max) vs 0.094, SED, and
  Exathlon 0.971 (moving mean).
* It fails on the shape datasets it was meant to fix: OPPORTUNITY 0.03,
  MSL 0.05–0.09, UCR 0.01–0.04.
* Exact byte repeats are too brittle for noisy real shapes. A match
  model needs the same bytes; a shape anomaly needs "similar up to
  noise", which is what subsequence-distance methods measure.

Not pursued to the evaluation set. Per-series values:
`bench/results/data/tsbad_cm_tuning.csv`.

## Development: on-board triage + ground Sub-PCA, a cascade (`bench/tsbad_cascade.py`)

**Question.** If the downlink can carry only a fraction q of the data,
how much of a shape-aware ground detector's accuracy survives when the
on-board compressor chooses what to send?

**Setup.**
* On board, F_max_z ranks windows of L samples; the top q are sent.
* On the ground, Sub-PCA (best on TSB-AD-U) keeps its scores only on the
  sent windows.
* Control: the same q, chosen at random.

**Criterion, fixed before the run (commit 114b377 and earlier):** at
q = 20%, keep ≥ 90% of full Sub-PCA's mean VUS-PR and beat the random
control. Run on TSB-AD-U's 48 tuning series only.

| Downlinked share q | Cascade VUS-PR | Share of full Sub-PCA (0.326) | Random windows | Share | Anomalous samples sent |
|---:|---:|---:|---:|---:|---:|
| 5% | 0.234 | 72% | 0.086 | 26% | 31% |
| 10% | 0.266 | 82% | 0.091 | 28% | 41% |
| **20%** | **0.277** | **85%** | 0.119 | 36% | 53% |
| 30% | 0.256 | 78% | 0.135 | 41% | 61% |
| 50% | 0.268 | 82% | 0.195 | 60% | 73% |

* **The pre-set criterion fails:** 85% < 90% at q = 20%. The cascade is
  not "almost free".
* **On-board triage is still worth much more than chance.**
  * With 10% of the windows, the ground keeps 82% of Sub-PCA's VUS-PR,
    against 28% for random windows.
  * With 5%, it keeps 72%, against 26%.
  * The compressor sends 3–6x more anomalous samples than chance at
    small q.
* The non-monotone column (30% below 20%) comes from VUS-PR's
  sensitivity to the score floor in unsent windows. It is a property of
  the setup, not a gain to read into.

Per-series values: `bench/results/data/tsbad_cascade_tuning.csv`. The
evaluation set was not used.

## Stage 4 result: on-board triage cascade on TSB-AD-U-Eva (pre-registered, run once)

* 348 of the 350 evaluation series: the same two Stock series (155, 165)
  as in stage 3 do not finish in the benchmark's VUS-PR code and are
  left out (`--skip`).
* Our run of Sub-PCA reproduces the published table on these series:
  0.414 vs 0.420.

Per-series values: `bench/results/data/tsbad_cascade_eval.csv`.

| Downlinked share q | Cascade VUS-PR | Share of full Sub-PCA (0.414) | Random windows | Cascade / random | Anomalous samples sent |
|---:|---:|---:|---:|---:|---:|
| 5% | 0.213 | 51% | 0.093 | 2.3x | 29% |
| **10%** | **0.255** | **62%** | 0.103 | **2.5x** | 40% |
| 20% | 0.295 | 71% | 0.135 | 2.2x | 53% |
| 30% | 0.314 | 76% | 0.171 | 1.8x | 61% |
| 50% | 0.336 | 81% | 0.234 | 1.4x | 73% |

* **H6 (≥ 75% of Sub-PCA at q = 10%): refuted.** It keeps 62%. The 75%
  level is reached only at about 30% of the downlink.
* **H7 (≥ 2x random at q = 10%): holds.** 2.5x, Wilcoxon p = 7e-30.
* **What it means.** The compressor's surprise is a much better on-board
  filter than chance. With a tenth of the downlink it sends 40% of the
  anomalous samples, and the ground keeps 62% of its detection, against
  25% for random windows. It is not good enough for a tenth of the link
  to preserve most of a strong ground detector. The gap is the same
  shape blind spot: windows that hold abnormal shapes are not the ones
  the compressor finds most surprising.
* Prior art: prioritised downlink and cascaded detectors exist (e.g.
  US patent 12634313, "Using cascaded detectors for prioritizing and
  optimizing data exports"; on-board image prioritisation). This
  measures it for a telemetry compressor's surprise on a public
  benchmark against a random control. It is not a new idea.

## Development: triage by events (each chosen window with its neighbours) does not help

On TSB-AD-U's 48 tuning series, with the same budget (`event_*` columns of
`bench/tsbad_cascade.py`; `bench/results/data/tsbad_event_tuning.csv`).
Values are the share of full Sub-PCA's mean VUS-PR.

| Downlinked share q | Windows (as in stage 4) | Events (window + neighbours) | Random |
|---:|---:|---:|---:|
| 5% | 72% | 67% | 26% |
| 10% | 82% | 68% | 28% |
| 20% | 85% | 80% | 36% |
| 30% | 78% | 81% | 42% |
| 50% | 82% | 84% | 60% |

* Events are worse at small budgets and similar at large ones; neither
  difference is significant (Wilcoxon p = 0.23 at 10%, 0.79 at 20%).
* Budget spent on neighbours is taken from other, independent surprise
  peaks.
* The window results reproduce the earlier development run exactly
  (82% and 85%).

Not taken to the evaluation set.

## Development: ordinal patterns as a compressor-native shape channel (partial, negative)

**Idea** (`bench/tsbad_ordinal.py`). Replace each sample by its ordinal
pattern of order 4 (Bandt and Pompe 2002), one of 24 symbols. Code that
stream with the same flight reference model, and use its excess cost as
an amplitude-free, Kraft-valid "shape surprise".
* It needs no ground-learned basis and only integer comparisons on board.
* Ordinal-pattern change detection is prior art (e.g. arXiv:1210.4903,
  arXiv:2502.03099). Coding the patterns with the compressor is the only
  twist.

**Result**, on the 18 smallest of the 48 tuning series (stopped at 10
min, with the CPU shared with the stage-5 evaluation). Values are the
share of Sub-PCA kept.

| q | compressor | ordinal | compressor + ordinal | compressor + PCA basis |
|---:|---:|---:|---:|---:|
| 5% | 73% | 39% | 65% | **88%** |
| 10% | 74% | 42% | 71% | **103%** |
| 20% | 81% | 60% | 69% | **106%** |

The ordinal channel is weak alone and makes the hybrid worse than the
compressor alone. Ignoring amplitude throws away what these anomalies are
made of. Dropped. The ground-learned PCA basis stays the shape channel to
beat. Per-series values:
`bench/results/data/tsbad_ordinal_tuning_partial.csv`.

## Development: the compressor's local information dimension (partial)

**Theory, which is not new.**
* A lossless code's mean cost estimates the entropy rate of the
  quantised signal (Shannon–McMillan–Breiman; Kraft makes the bits
  honest).
* At resolution ε that rate grows as d·log2(1/ε), with d Rényi's
  information dimension. For deterministic chaos it tends to the
  Kolmogorov–Sinai entropy, the sum of the positive Lyapunov exponents
  (Pesin), and the slope goes to 0 (Gaspard and Wang's ε-entropy, 1993).
* So the compressor's extra bits per extra bit of resolution are a
  local, Kraft-calibrated estimate of the signal's dimension.
* Measuring it needs a second, coarser model. It is not "zero extra
  RAM".

**Test** (`bench/tsbad_dimension.py`). Values are quantised at 8 and 6
bits on the normal prefix's range, and each stream is coded by the
adaptive flight profile. The per-sample slope is
(cost_8 − cost_6)/2, averaged over L.
* DIM_dev: |slope − its median on the normal prefix|.
* DIM_mean: the slope itself.
* COST_mean: the 8-bit cost alone.

Run on the 29 smallest of the 48 tuning series (stopped at 10 min, with
the CPU shared). Mean VUS-PR:

| Score | Mean VUS-PR |
|---|---:|
| DIM_mean | 0.088 |
| **DIM_dev** | 0.169 |
| COST_mean (entropy rate alone) | 0.129 |
| F_max_z (stage-3 change + state score) | 0.248 |

* **Overall it is weaker** than the compressor's change+state score.
  It beats it on 11 of 29 series.
* **But on OPPORTUNITY it sees what nothing else in this project
  did:**
  * id 11: 0.977, vs 0.046 for F_max_z;
  * id 23: 0.764, vs 0.020.
  OPPORTUNITY is the shape dataset where the compressor's score was
  0.05 on the evaluation set and Sub-PCA 0.91. A change of the signal's
  *dimension* (how many bits each extra bit of resolution costs) is
  invisible to the cost itself, but not to its slope.
* Two series are an anecdote, not a result. If pursued, it must be as a
  third channel of the hybrid (max of z-scores), chosen on the full
  tuning set and pre-registered on data not yet used for triage, such as
  TSB-AD-M.

Per-series values: `bench/results/data/tsbad_dimension_tuning_partial.csv`.
