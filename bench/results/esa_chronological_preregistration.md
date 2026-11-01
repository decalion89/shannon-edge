# Whole-mission ESA test: pre-registration of a windowed e-value rule

Written and committed **before** this rule was run on any mission, and
before the per-sample results on Missions 2 and 3 were seen. Only the
per-sample rule's Mission 1 result was known at that time (event-wise
F0.5 0.427: precision 0.900, recall 0.138, t = 30 bits).

## Protocol (fixed)

The protocol is that of Alcarria et al., "Structure-Aware Unsupervised
Anomaly Detection for Spacecraft Telemetry with Adaptive EVT
Thresholding" (SPAICE 2026, arXiv:2609.10017). They report F0.5 = 0.700
(Mission 1) and 0.698 (Mission 2).
* All target channels.
* Scored from the first sample + 1 month (floored to the day) to the end
  of the mission.
* Events of category Anomaly and Rare Event, entirely inside the scored
  period.
* Detections closer than 6 hours grouped into one.
* ESA-ADB's own `ESAScores`; the primary metric is the corrected
  event-wise F0.5.
* Missions 1, 2 and 3. Mission 3 is not part of ESA-ADB and has no
  published results.

Script: `bench/esa_chronological.py`.

## Rule (fixed, no training, no parameter chosen on labels)

**Statistic.** Per channel, per 6-hour UTC window, a running e-process
over the samples in the window:
* M_n = (1/4) Σ_e Π_{i≤n} ((1 − e) + e·2^(ℓᵢ − b)), for e ∈ {2^−1,
  2^−4, 2^−8, 2^−12};
* ℓᵢ is the flight profile's cost of sample i in bits, and b the
  channel's code width.

**Validity.** Under a calibrated code, each factor has expectation at
most 1 given the past (Kraft). So each product, and their average, is a
nonnegative supermartingale starting at 1. By Ville's inequality,
P(sup_n M_n ≥ 2^t) ≤ 2^−t within one window.

**Alarm.** A sample alarms when log2 M_n ≥ t_w, where t_w = ceil(log2 W)
and W is the number of channel-windows holding at least one scored
sample. Under calibration, the expected number of channel-windows with a
false alarm is at most 1.

This is an e-detector in the sense of Shin, Ramdas and Rinaldo
(arXiv:2203.03532), restarted at fixed windows. The theory is theirs.
What is tested here is whether it helps a flight compressor on real
telemetry.

## Hypotheses and what counts as an answer

* **H1.** The windowed rule scores a higher event-wise F0.5 than the
  per-sample rule (t = ceil(log2 N)) on at least 2 of the 3 missions.
* **H2.** The windowed rule reaches Alcarria et al.'s score (0.700 on
  Mission 1, 0.698 on Mission 2) on at least one of them.

All results are reported, whatever they are. The rule, t_w, the windows
and the e grid will not be changed after seeing results. If a variant is
tried later, it will be labelled post hoc.
