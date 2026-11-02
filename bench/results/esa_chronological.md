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

## Next: can one label recover the recurring anomaly? Feasibility (development years only)

Mission 1's class_7 is invisible to surprise because it recurs. Could a
single operator label recover it? First, an upper bound that uses no
compressor at all (`bench/analysis/oneshot_feasibility.py`):
* the first class_7 event (id_30, 2000-02-27) is the template;
* its z-normalised distance (MASS) to every subsequence of 5-min medians
  is computed;
* the minimum is taken per 6-h window.

Only 2000–2006 is used: 2007–2013 stays untouched for a later
pre-registered test.

| Channel | Other class_7 events found (of 21) | Nominal windows below the threshold (of 9,002) |
|---|---:|---:|
| 14 | 8 / 9 | 5 / 10 |
| 21 | 8 / 9 | 5 / 10 |
| 29 | 9 / 10 | 5 / 10 |

One example finds about 40% of the other occurrences at about one false
window a year. The rest have visibly different shapes: some drop first,
others overshoot. A compressor with a match model could at best
approach this.

Estimated effect on Mission 1: about 18 more events of 196, which is
not enough by itself to close the gap to 0.700. Several examples per
class, and classes other than class_7, would be needed. Not pursued
further yet.

## Post hoc: corroboration across channels (`bench/analysis/corroboration.py`)

**Not confirmatory.** This was designed after seeing where the
pre-registered rule's false alarms come from.

**What we saw.** The windowed rule's false alarms are almost all raised
by a single channel: 55 of 57 on Mission 1, 162 of 192 on Mission 2, 1
of 1 on Mission 3. True events are mostly found by detections spanning
several channels; on Mission 2, 607 of 629. One channel, 75, alone
raises 19 of Mission 1's 57 false alarms.

**Rule.** Alarm when at least 2 channels reach
t2 = ceil((log2 W_time + log2 C(n, 2)) / 2) in the same 6-h window,
where W_time is the number of 6-h windows and n the number of channels.
If channels were independent given the past, that gives at most one
expected false pair-window. The formula fixes t2; nothing was tuned.
"Union" means either rule, each at one extra bit.

| Mission | t_w / t2 | Single (pre-registered) | **Pair** | Union | Pair: shifted median / max |
|---|---:|---:|---:|---:|---:|
| 1 | 21 / 13 | 0.432 | **0.569** (precision 0.884, recall 0.235) | 0.492 | 0.080 / 0.125 |
| 2 | 18 / 12 | 0.724 | **0.871** (precision 0.852, recall 0.955) | 0.737 | 0.128 / 0.160 |
| 3 | 18 / 11 | 0.492 | 0.333 | 0.492 | — |

* **Mission 2.** The pair rule reaches 0.871, against 0.698 for
  Alcarria et al. on the same protocol. It is close to the 0.882 cited
  for PitIA, but that was under a static split, so the two are not
  comparable.
* **Mission 1.** It improves to 0.569, still below 0.700.
* **Mission 3.** It loses: few events, mostly in one channel.
* **The independence assumption is false.** The pair rule still raises
  6 false detections on Mission 1 and 58 on Mission 2, where at most
  one is expected under independence. Correlated channels, or
  unlabelled events, break it. The pair rule therefore has **no**
  guarantee, only a formula for its threshold. Cross-channel
  corroboration is also standard practice in monitoring (e.g. a
  multivariate SPRT patent for telemetry, US 9,152,530).

**To make this a result, it must be tested on data not used here**: a
new ESA release or another mission, with the pair rule fixed as above.
