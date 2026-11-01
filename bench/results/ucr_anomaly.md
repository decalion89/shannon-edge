# UCR Time Series Anomaly Archive: where the compressor's surprise stands

`bench/ucr_anomaly.py` runs the archive of Wu & Keogh (2021): 250
univariate series from medicine, industry, space and biology, each with an
anomaly-free training prefix and exactly one anomaly. A prediction is the
location of the top score in the test part. It counts as correct within
[begin − 100, end + 100]. The archive's slides ask for some "play" but do
not fix a number; 100 is the tolerance commonly used.

| Method (no training unless stated) | Correct |
|---|---:|
| Flight-profile surprise, top sample | 67/250 (0.268) |
| Flight-profile surprise, summed over a window m | 52/250 (0.208) |
| Periodic code (change vs the same phase one period earlier), top sample | 70/250 (0.280) |
| Periodic code, summed over m | 87/250 (0.348) |
| General CM model (`byte_costs`), 16-bit rank codes, summed over m | 65/250 (0.260) |
| General CM model, 8-bit training quantiles, summed over m | 58/250 (0.232) |
| **Matrix-profile discord** (stumpy, window m) | **134/250 (0.536)** |
| Combination fixed in advance (committed before the matrix-profile results): per file, the method whose top score stands out more | 134/250 (0.536) |
| Either one correct (an oracle, not a method) | 160/250 (0.640) |
| Second combination rule, designed **after** the first failed: per file, the method whose test peak is the larger multiple of its own maximum on the anomaly-free training part | **141/250 (0.564)** |

m is the period estimated on the training prefix: the first
autocorrelation peak, clipped to 10..500.

**Verdict.**
* On single-signal shape anomalies, which are most of this archive, the
  compressor's surprise is clearly worse than the matrix profile: 0.27–0.35
  against 0.54.
* A compressor needs exact or near-exact repeats. A noisy shape never
  repeats exactly, while the z-normalised distance of the matrix profile
  tolerates noise and scale.
* The two methods are complementary: together they reach 160/250, and the
  surprise alone catches 26 files the matrix profile misses.
* The combination rule fixed in advance does not capture that gain. It
  picked the surprise in 79 files, but gains and losses cancelled exactly
  (134 = 134). Choosing per file between detectors without training is an
  open problem.
* A second rule, designed after seeing the first fail, does better: 141
  (+7 over the matrix profile). It compares how far each method's test
  peak rises above that method's own anomaly-free training range. It is
  post hoc, so it is a lead for a pre-registered test on other data, not
  a result.
* The training margin is informative on its own. When the surprise's
  test peak exceeds its training maximum, it is right in 60 of 180 files,
  against 7 of 70 otherwise.

This bounds the claim made from ESA-ADB. The compressor's surprise is a
strong, training-free detector of abrupt events in multichannel
telemetry: first on both ESA-ADB full sets, 9x and 3x the best published
methods. It is not a universal anomaly detector.
