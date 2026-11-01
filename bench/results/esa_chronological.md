# Whole-mission ESA test, no training: the pre-registered windowed e-value rule

**Question.** Alcarria et al. (SPAICE 2026, arXiv:2609.10017) evaluate
unsupervised detectors on whole ESA missions, chronologically. Their
method retrains a model every month (46.6 CPU-hours on Mission 1) and
reports corrected event-wise F0.5 = 0.700 (Mission 1) and 0.698
(Mission 2). Can a detector with no training reach that, with a
false-alarm threshold fixed by a formula?

**Answer.**
* **On Mission 2, yes: 0.724 against 0.698.**
* On Mission 1, no: 0.432 against 0.700.
* On Mission 3, which is not part of ESA-ADB and has no published
  result, the score is 0.492.

The rule was pre-registered (`esa_chronological_preregistration.md`,
commit d47d93d) and implemented (commit 26f2cab) before it was run.

## Protocol

As Alcarria et al.:
* all target channels;
* scored from 2000-02-01 (first sample + 1 month) to the end of the
  mission;
* events of category Anomaly and Rare Event, entirely inside the scored
  period;
* detections closer than 6 h grouped;
* ESA-ADB's own metric code (`ESAScores`, `ChannelAwareFScore`,
  `ADTQC`), unmodified.

Event counts match theirs on Mission 1: 196 events, 118 of them
anomalies. On Mission 2 we count 627 events, 31 of them anomalies,
against their 644. Our count keeps only events entirely inside the
scored period.

Script: `bench/esa_chronological.py`.

## Rules

* **Per-sample.** Flag a sample when its flight-profile cost reaches
  b + t bits, t = ceil(log2 N), N = samples scored over all target
  channels. Under calibration there is at most one expected false
  sample-flag (Kraft).
* **Windowed (pre-registered).** Per channel and per 6-hour UTC window,
  the mixture e-process M_n = mean_e Π((1 − e) + e·2^(ℓᵢ − b)), for
  e ∈ {2^−1, 2^−4, 2^−8, 2^−12}. Flag when log2 M_n reaches
  t_w = ceil(log2 W), W = channel-windows scored. Under calibration there
  is at most one expected false channel-window (Kraft + Ville). This is
  an e-detector in the sense of Shin, Ramdas and Rinaldo
  (arXiv:2203.03532), restarted at fixed windows.

Nothing is trained, and no value was chosen on labels.

## Results (ESA-ADB's metric code)

| Mission | Rule | t | Detections | **Event-wise F0.5** | Precision (corr.) | Recall | Alarming precision | Channel-aware F0.5 | ADTQC | Anomalies only F0.5 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 (58 ch., 608 M samples) | per-sample | 30 | 32 | 0.427 | 0.900 | 0.138 | 0.900 | 0.044 | 0.912 | 0.543 |
| 1 | **windowed** | 21 | 136 | **0.432** | 0.495 | 0.286 | 0.683 | 0.107 | 0.870 | 0.388 |
| 2 (47 ch., 339 M samples) | per-sample | 29 | 33 | 0.217 | 0.872 | 0.054 | 1.000 | 0.012 | 0.822 | 0.298 |
| 2 | **windowed** | 18 | 721 | **0.724** | 0.682 | 0.963 | 0.962 | 0.641 | 0.748 | 0.093 |
| 3 (24 ch., 368 M samples) | per-sample | 29 | 2 | 0.135 | 1.000 | 0.030 | 1.000 | 0.030 | 0.962 | 0.000 |
| 3 | **windowed** | 18 | 6 | **0.492** | 0.857 | 0.182 | 1.000 | 0.111 | 0.667 | 0.714 |
| Alcarria et al. 2026, M1 / M2 | monthly retraining | | | 0.700 / 0.698 | 0.852 / 0.721 | 0.408 / 0.621 | | | | |

**Pre-registered hypotheses**
* **H1** (windowed > per-sample on at least 2 of 3 missions): **holds**,
  3 of 3. On Mission 1 the margin is marginal: 0.432 vs 0.427.
* **H2** (reach Alcarria et al. on at least one mission): **holds** on
  Mission 2, 0.724 vs 0.698. It does not hold on Mission 1.

**Reference margins (not a result, chosen by no one).** The per-sample
rule at fixed t = 20–28 scores 0.32–0.49 on Mission 1 and 0.13–0.31 on
Mission 3 (`--margins`). No fixed per-sample margin reaches the windowed
rule on Mission 3.

## Control: circular time shifts (`bench/analysis/shift_control.py`)

The same detections, shifted in time by k/21 of the scored span
(k = 1..20, wrapping around). This keeps their number, lengths and
spacing and destroys only their alignment with events. Scored with the
event-wise logic of `ESAScores`, which reproduces the official 0.724,
0.432 and 0.492 exactly.

| Mission | Unshifted | Shifted: median | Shifted: max | Share of time flagged |
|---|---:|---:|---:|---:|
| 1 | 0.432 | 0.079 | 0.132 | 0.48% |
| 2 | 0.724 | 0.138 | 0.163 | 12.87% |
| 3 | 0.492 | 0.000 | 0.000 | 0.01% |

The scores come from detecting the right moments, not from detecting a
lot.

## What this does and does not show

* **Mission 2: a training-free detector, threshold fixed by a formula,
  scores above a monthly-retrained method on its own protocol.** Recall
  is 0.963: 604 of 627 events are found.
* **Mission 2's events are mostly rare nominal events** (596 of 627).
  Scored on its 31 anomalies alone, the windowed rule gets 0.093. The
  per-sample rule does better there (0.298). Alcarria et al. do not
  report anomalies alone; JSempereH/ESA-ADB-anomaly-detection reports at
  most about 0.16 for unsupervised methods on Mission 2 anomalies, under
  a walk-forward protocol.
* **Mission 1 stays far below** (0.432 vs 0.700). Its largest anomaly
  class (class_7, 45 events) is a recurring smooth dip within the normal
  range. No per-sample surprise sees it: the event's largest excess is
  about 4–5 bits at every scale tried. Only 78 of 196 events have any
  sample 16 or more bits above b (`bench/results/esa_adb.md`, ceiling
  analysis).
* **The guarantee.** It holds only if the model is calibrated. Mission 2
  channels 18–20 are about 4x overconfident in the far tail
  (`kraft_calibration.py`). The flagged 12.9% of Mission 2 time is
  partly that.
* **Cost.** The whole of Mission 1 (58 channels, 608 M samples), scored
  with the flight profile, took 28 min wall-clock on a shared 4-core
  machine. That includes unpacking and unpickling the data. Alcarria et
  al. report 46.6 h of retraining for Mission 1.
* **Comparability.** Same protocol as far as their paper describes it;
  not their code. The event sets differ slightly on Mission 2 (627 vs
  644).
