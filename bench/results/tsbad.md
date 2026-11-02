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
