# The compressor as an anomaly detector, on ESA's own benchmark

The flight profile computes, for every sample, its cost in bits — how
surprising it is given everything seen before — and sender and receiver
compute the same value. `esa_mission1_anomaly.md` showed with simple
controls that this surprise finds labelled anomalies. Here it is scored on
**ESA-ADB**, the European Space Agency Benchmark for Anomaly Detection in
Satellite Telemetry (Kotowski et al., arXiv:2406.17826), with its protocol
and its main metric, against the algorithms published there.

## Protocol (`bench/anomaly_esaadb.py`)

* ESA-AD Mission 1. Training: samples up to 2007-01-01 (84 months);
  test: samples after it, as in ESA-ADB. Validation: the last 3 months of
  training (from 2006-10-01), as in ESA-ADB.
* Events of category "Anomaly" and "Rare Event" count; communication gaps
  do not, but detections inside them are not false positives.
* **Corrected event-wise F0.5** (the benchmark's main metric: event-wise
  precision multiplied by the time-level true-negative rate, Sehili &
  Zhang), plus alarming precision; computed with the logic of ESA-ADB's
  own `ESAScores` code (MIT; adapted in the script, with attribution), on
  the logical OR of detections across the target channels.
* Detector: per channel, the flight profile's per-sample cost (online: a
  sample is scored by a model that has seen only the past); a per-channel
  threshold = a quantile of the cost of training samples outside labelled
  events; flags within 10 minutes merged into one detection. The quantile
  is chosen on the validation months (thresholds fitted before them);
  every rule tried is reported. No neural network, no training beyond the
  compressor's own online learning.

## Lightweight subset (channels 41–46), as in ESA-ADB Table 2

Validation (2006-10-01 to 2007-01-01, 3 events): F0.5 per rule 0.9999: 0.022, 0.99999: 0.172, 0.999999: 0.909, 1.0: 0.909; chosen: 1.0

| Threshold (quantile of training nominal cost) | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.9999 | 6470 | 54 | 6043 | 11 | 0.009 | 0.831 | **0.011** | 0.135 |
| 0.99999 | 835 | 44 | 683 | 21 | 0.061 | 0.677 | **0.074** | 0.314 |
| 0.999999 | 108 | 29 | 52 | 36 | 0.358 | 0.446 | **0.373** | 0.537 |
| 1.0 (chosen on validation) | 26 | 20 | 0 | 45 | 1.000 | 0.308 | **0.690** | 0.800 |

Published results on the same subset (ESA-ADB, Table 2, corrected
event-wise F0.5): Telemanom-ESA-Pruned **0.786** (precision 0.999,
recall 0.424); GlobalSTD5 0.253; Telemanom-ESA 0.178; DC-VAE-ESA STD5
0.075; DC-VAE-ESA STD3 0.003; GlobalSTD3 0.001; PCC, HBOS, iForest, KNN,
Windowed iForest < 0.001.

| Algorithm (lightweight subset, Mission 1) | Corrected event-wise F0.5 | Precision | Recall |
|---|---:|---:|---:|
| Telemanom-ESA-Pruned (LSTM per channel, pruned) | **0.786** | 0.999 | 0.424 |
| **sedge surprise, threshold = max of training nominal cost** | **0.690** | **1.000** | 0.308 |
| sedge surprise, 0.999999 quantile | 0.373 | 0.358 | 0.446 |
| GlobalSTD5 | 0.253 | 0.288 | 0.169 |
| Telemanom-ESA | 0.178 | 0.148 | 0.894 |
| DC-VAE-ESA STD5 | 0.075 | 0.063 | 0.338 |

With the most conservative rule — alarm only on a cost higher than
anything seen in nominal training data — the compressor's surprise raises
**no false alarm in seven years of test data** and detects 20 of 65
events, second only to the pruned LSTM ensemble and ahead of every other
published method, at no extra cost on board: the value is a by-product of
compression.

**Caveats, stated plainly.**

* The choice of rule is weakly determined: the validation months contain
  only 3 events, and the max rule ties with the 0.999999 quantile there
  (0.909 each); the tie was broken towards the higher, more conservative
  threshold, which the precision-weighted metric favours. With the other
  rule the test score would be 0.373. Both are reported.
* Preprocessing differs: ESA-ADB's algorithms run on data resampled to 30
  s (zero-order hold); the surprise is computed on the original samples.
  The metric logic is ESA-ADB's, applied to time intervals, so the scores
  are comparable in kind but not produced by the identical pipeline.
* Events are clipped to the test period at 2007-01-01.
