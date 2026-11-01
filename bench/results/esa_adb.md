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

## Full set of target channels (58 channels), as in ESA-ADB Table 2

The harder setting: all 58 target channels of Mission 1, events combined
across them (`--channels` = every channel with Target = YES in
channels.csv: 12–52, 57–66, 70–76).

Validation (2006-10-01 to 2007-01-01, 5 events): F0.5 per rule 0.999999: 0.600, 0.9999999: 0.714, 1.0: 0.882; chosen: 1.0

| Threshold (quantile of training nominal cost) | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.999999 | 585 | 55 | 348 | 36 | 0.136 | 0.604 | **0.161** | 0.226 |
| 0.9999999 | 255 | 44 | 127 | 47 | 0.257 | 0.484 | **0.284** | 0.336 |
| 1.0 (chosen on validation) | 227 | 39 | 113 | 52 | 0.257 | 0.429 | **0.279** | 0.333 |

Published results on the full set (ESA-ADB, Table 2, corrected event-wise
F0.5): Telemanom-ESA-Pruned **0.061** (precision 0.050, recall 0.870);
Telemanom-ESA 0.008; DC-VAE-ESA STD5 0.007; GlobalSTD5 0.003; PCC, HBOS,
iForest, GlobalSTD3, DC-VAE-ESA STD3 < 0.001 (KNN and Windowed iForest ran
out of memory).

| Algorithm (full set, Mission 1) | Corrected event-wise F0.5 | Precision | Recall |
|---|---:|---:|---:|
| **sedge surprise, max of training nominal cost (chosen on validation)** | **0.279** | 0.257 | 0.429 |
| Telemanom-ESA-Pruned | 0.061 | 0.050 | 0.870 |
| Telemanom-ESA | 0.008 | 0.007 | 0.946 |
| DC-VAE-ESA STD5 | 0.007 | 0.005 | 0.804 |
| GlobalSTD5 | 0.003 | 0.002 | 0.761 |

On the full set the compressor's surprise scores **4.6x the best published
algorithm**. Here the rule is chosen on validation without a tie (5
validation events: 0.882 for the max rule against 0.714 and 0.600). It
still raises 113 false detections in the test years (precision 0.257):
better than the published methods, far from the lightweight subset's zero.
The same caveats apply (original samples rather than 30 s resampling;
events clipped at the split).

## Mission 2 (replication)

Same detector and procedure, Mission 2 protocol of ESA-ADB: training up to
2001-10-01, validation from 2001-07-01. Channels with more than 65,536
distinct values (e.g. channel 18: 90,474) are scored on their values
merged into 65,536 ordered bins (detection only). The validation dates
printed by the run were a hard-coded label, corrected here (the
computation used the Mission 2 dates).

### Lightweight subset (channels 18–28)

Validation (2001-07-01 to 2001-10-01, 27 events): F0.5 per rule 0.9999: 0.072, 0.99999: 0.498, 0.999999: 0.859, 1.0: 0.746; chosen: 0.999999

| Threshold (quantile of training nominal cost) | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.9999 | 3819 | 345 | 3001 | 5 | 0.103 | 0.986 | **0.126** | 0.426 |
| 0.99999 | 649 | 299 | 159 | 51 | 0.653 | 0.854 | **0.685** | 0.615 |
| 0.999999 (chosen on validation) | 187 | 139 | 13 | 211 | 0.914 | 0.397 | **0.725** | 0.808 |
| 1.0 | 107 | 91 | 1 | 259 | 0.989 | 0.260 | **0.634** | 0.867 |

Published (ESA-ADB Table 2): Windowed iForest **0.949**, Telemanom-ESA-Pruned
0.842, iForest 0.609, Telemanom-ESA 0.224, DC-VAE-ESA STD5 0.079,
GlobalSTD5 0.075, HBOS 0.068, PCC 0.036, GlobalSTD3 0.007, DC-VAE-ESA STD3
0.003, KNN 0.001. **The surprise (0.725) is third** here.

### Full set (47 target channels)

Validation (2001-07-01 to 2001-10-01, 27 events): F0.5 per rule 0.999999: 0.551, 0.9999999: 0.739, 1.0: 0.714; chosen: 0.9999999

| Threshold (quantile of training nominal cost) | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.999999 | 648 | 313 | 110 | 49 | 0.740 | 0.865 | **0.762** | 0.570 |
| 0.9999999 (chosen on validation) | 330 | 203 | 29 | 159 | 0.875 | 0.561 | **0.787** | 0.651 |
| 1.0 | 288 | 176 | 24 | 186 | 0.880 | 0.486 | **0.757** | 0.640 |

Published (ESA-ADB Table 2): PCC **0.079**, Telemanom-ESA-Pruned 0.071,
GlobalSTD5 0.064, Telemanom-ESA 0.064, Windowed iForest 0.042, iForest
0.027, HBOS 0.020, DC-VAE-ESA STD5 0.011, GlobalSTD3 0.008, DC-VAE-ESA STD3
0.002. **The surprise scores 0.787, about 10x the best published.**

## Summary across both missions

| Corrected event-wise F0.5 | sedge surprise | Best published | Rank |
|---|---:|---:|---:|
| Mission 1, lightweight (6 channels) | 0.690 | 0.786 (Telemanom-ESA-Pruned) | 2nd |
| Mission 1, full set (58 channels) | **0.279** | 0.061 (Telemanom-ESA-Pruned) | **1st, 4.6x** |
| Mission 2, lightweight (11 channels) | 0.725 | 0.949 (Windowed iForest) | 3rd |
| Mission 2, full set (47 channels) | **0.798** (0.787 before muting) | 0.079 (PCC) | **1st, ~10x** |

On the realistic setting — every target channel of an operating
spacecraft — the compressor's free by-product beats every published
algorithm by a wide margin on both missions; on the small hand-picked
subsets, trained neural networks or windowed isolation forests remain
better. Its strength is precision: thresholds at the extremes of what the
model has seen keep false alarms rare where the published methods raise
thousands.

## Are the test sets the same as the paper's?

Event counts of our test and validation sets against ESA-ADB's
Supplementary Tables 11–12:

| Set | ESA-ADB | Ours |
|---|---:|---:|
| Mission 1 lightweight, test | 65 (29 anomalies, 36 rare events) | 65 (29, 36) |
| Mission 1 full, test | 91 | 91 |
| Mission 1 validation, lightweight / full | 3 / 5 | 3 / 5 |
| Mission 2 lightweight, test | 349 | 350 |
| Mission 2 full, test | 361 | 362 |
| Mission 2 validation, full | 27 | 27 |

Exact for Mission 1; one event more in each Mission 2 test set, most
likely an event straddling the split that we clip to the test period
rather than drop. The remaining difference is preprocessing (ESA-ADB's
algorithms see 30-s resampled data; the surprise uses original samples).

## What it finds, and what it misses (lightweight subset)

Breaking the 65 test events down by category (rule: cost above the
maximum seen in nominal training data):

| Category | Detected |
|---|---:|
| Anomaly | **19 of 29** |
| Rare Event | 1 of 36 |

The surprise is a detector of **anomalies** — data the model has never
seen — and nearly blind to "rare events" (infrequent but known
operations, which the model has already seen and learned). Scored on
anomalies alone, as in ESA-ADB's Supplementary Table 9:

| Algorithm (lightweight subset, anomalies only) | Corrected event-wise F0.5 | Precision | Recall |
|---|---:|---:|---:|
| Telemanom-ESA-Pruned | **0.968** | 0.999 | 0.862 |
| **sedge surprise, max of training nominal cost** | **0.905** | 1.000 | 0.655 |
| GlobalSTD5 | 0.211 | 0.205 | 0.241 |
| Telemanom-ESA | 0.090 | 0.074 | 0.931 |
| DC-VAE-ESA STD5 | 0.026 | 0.021 | 0.241 |
| others | ≤ 0.001 | | |

**Tried and rejected: joint surprise.** Maybe the missed anomalies are
mildly surprising in several channels at once. Summing the per-channel
costs normalised by their thresholds (threshold = max on training) finds
3 of 65 events (F0.5 0.195); summing the two largest finds 17 of 65
(0.639, anomalies only 0.876). Both are worse than the per-channel rule:
the missed anomalies are simply not surprising to the model.


## Fewer false alarms, chosen on validation only

Two rules were added to the search, both decided on the validation months
(`--factors`, `--mute`): a margin on the threshold (×1, ×1.25, ×1.5), and
muting a channel that raised a false detection in the 3 months before the
evaluated period (for the validation itself, the 3 months before it; for
the test, the validation months — a rule never sees its own period).

### Mission 1, full set

Validation (2006-10-01 to 2007-01-01, 5 events): F0.5 per rule q=0.9999999: 0.714, q=0.9999999, mute: 0.714, q=0.9999999, x1.25: 0.769, q=0.9999999, x1.25, mute: 0.769, q=0.9999999, x1.5: 0.000, q=0.9999999, x1.5, mute: 0.000, q=1.0: 0.882, q=1.0, mute: 0.882, q=1.0, x1.25: 0.769, q=1.0, x1.25, mute: 0.769, q=1.0, x1.5: 0.000, q=1.0, x1.5, mute: 0.000; chosen: q=1.0, mute

| Rule | Muted channels | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q=0.9999999 | 0 | 255 | 44 | 127 | 47 | 0.257 | 0.484 | **0.284** | 0.336 |
| q=0.9999999, mute | 1 | 256 | 44 | 127 | 47 | 0.257 | 0.484 | **0.284** | 0.333 |
| q=0.9999999, x1.25 | 0 | 74 | 29 | 16 | 62 | 0.644 | 0.319 | **0.535** | 0.483 |
| q=0.9999999, x1.25, mute | 0 | 74 | 29 | 16 | 62 | 0.644 | 0.319 | **0.535** | 0.483 |
| q=0.9999999, x1.5 | 0 | 27 | 16 | 4 | 75 | 0.800 | 0.176 | **0.468** | 0.640 |
| q=0.9999999, x1.5, mute | 0 | 27 | 16 | 4 | 75 | 0.800 | 0.176 | **0.468** | 0.640 |
| q=1.0 | 0 | 227 | 39 | 113 | 52 | 0.257 | 0.429 | **0.279** | 0.333 |
| q=1.0, mute (chosen on validation) | 0 | 227 | 39 | 113 | 52 | 0.257 | 0.429 | **0.279** | 0.333 |
| q=1.0, x1.25 | 0 | 67 | 22 | 16 | 69 | 0.579 | 0.242 | **0.453** | 0.415 |
| q=1.0, x1.25, mute | 0 | 67 | 22 | 16 | 69 | 0.579 | 0.242 | **0.453** | 0.415 |
| q=1.0, x1.5 | 0 | 18 | 9 | 4 | 82 | 0.692 | 0.099 | **0.315** | 0.600 |
| q=1.0, x1.5, mute | 0 | 18 | 9 | 4 | 82 | 0.692 | 0.099 | **0.315** | 0.600 |

Validation (5 events) again chose the maximum rule; muting changed nothing
(at most one channel muted). The official score stays **0.279**. The
table also shows that a ×1.25 margin would have scored 0.535 on the test
years: it was not chosen, and choosing it now, after seeing the test
results, would be exactly the selection bias this protocol exists to
prevent. With five validation events the choice of rule is noisy; a
longer validation window would be the principled remedy for future runs.

### Mission 2, full set

Validation (2001-07-01 to 2001-10-01, 27 events): F0.5 per rule q=0.9999999: 0.739, q=0.9999999, mute: 0.766, q=0.9999999, x1.25: 0.465, q=0.9999999, x1.25, mute: 0.465, q=0.9999999, x1.5: 0.161, q=0.9999999, x1.5, mute: 0.161, q=1.0: 0.714, q=1.0, mute: 0.714, q=1.0, x1.25: 0.465, q=1.0, x1.25, mute: 0.465, q=1.0, x1.5: 0.161, q=1.0, x1.5, mute: 0.161; chosen: q=0.9999999, mute

| Rule | Muted channels | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q=0.9999999 | 0 | 330 | 203 | 29 | 159 | 0.875 | 0.561 | **0.787** | 0.651 |
| q=0.9999999, mute (chosen on validation) | 5 | 317 | 202 | 24 | 160 | 0.894 | 0.558 | **0.798** | 0.664 |
| q=0.9999999, x1.25 | 0 | 34 | 25 | 4 | 337 | 0.862 | 0.069 | **0.262** | 0.735 |
| q=0.9999999, x1.25, mute | 0 | 34 | 25 | 4 | 337 | 0.862 | 0.069 | **0.262** | 0.735 |
| q=0.9999999, x1.5 | 0 | 2 | 2 | 0 | 360 | 1.000 | 0.006 | **0.027** | 1.000 |
| q=0.9999999, x1.5, mute | 0 | 2 | 2 | 0 | 360 | 1.000 | 0.006 | **0.027** | 1.000 |
| q=1.0 | 0 | 288 | 176 | 24 | 186 | 0.880 | 0.486 | **0.757** | 0.640 |
| q=1.0, mute | 3 | 277 | 176 | 21 | 186 | 0.893 | 0.486 | **0.765** | 0.659 |
| q=1.0, x1.25 | 0 | 26 | 22 | 4 | 340 | 0.846 | 0.061 | **0.236** | 0.880 |
| q=1.0, x1.25, mute | 0 | 26 | 22 | 4 | 340 | 0.846 | 0.061 | **0.236** | 0.880 |
| q=1.0, x1.5 | 0 | 2 | 2 | 0 | 360 | 1.000 | 0.006 | **0.027** | 1.000 |
| q=1.0, x1.5, mute | 0 | 2 | 2 | 0 | 360 | 1.000 | 0.006 | **0.027** | 1.000 |

Here validation chose muting (5 channels muted): false detections 29 →
24, F0.5 **0.787 → 0.798**. The ×1.25 margin that would have helped
Mission 1 would have hurt Mission 2 badly (0.262): no single fixed rule
suits every mission, which is why the rule is left to validation.

## Tried and rejected: a memory that never forgets

The compressor learns fast (counters adapt at a rate down to 1/62), so a
rare operation stops being surprising after it has happened a couple of
times — one reason rare events are missed. A second detector with a
never-forgetting memory scores each sample by how rare its transition
(previous value → value) has been over the channel's whole past
(`--slow`; OR-combined, own threshold from training). Lightweight subset
of Mission 1:

Validation (2006-10-01 to 2007-01-01, 3 events): F0.5 per rule q=0.999999: 0.909, q=0.999999, +slow memory: 0.484, q=1.0: 0.909, q=1.0, +slow memory: 0.556; chosen: q=1.0

| Rule | Muted channels | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q=0.999999 | 0 | 108 | 29 | 52 | 36 | 0.358 | 0.446 | **0.373** | 0.537 |
| q=0.999999, +slow memory | 0 | 1331 | 46 | 937 | 19 | 0.047 | 0.708 | **0.058** | 0.123 |
| q=1.0 (chosen on validation) | 0 | 26 | 20 | 0 | 45 | 1.000 | 0.308 | **0.690** | 0.800 |
| q=1.0, +slow memory | 0 | 764 | 40 | 524 | 25 | 0.071 | 0.615 | **0.086** | 0.175 |

It doubles the events found (40 vs 20 of 65) but raises 524 false
detections: in noisy channels almost every value pair is rare in history.
Validation rejected it on its own (0.556 vs 0.909); recorded as a negative
result.


## With ESA-ADB's own preprocessing (30-s grid)

The published algorithms see every channel resampled to a 30-s grid with
zero-order hold (ESA-ADB's data preparation); the results above used the
original samples. Re-run with `--resample 30s`, so the detector sees
exactly the samples the published algorithms saw (same rules searched,
choice on validation):

| Setting (30-s grid) | sedge surprise | (original samples) | Best published | Rank |
|---|---:|---:|---:|---|
| **Mission 1, full set** | **0.292** | 0.279 | 0.061 | **1st, 4.8x** |
| **Mission 2, full set** | **0.815** | 0.798 | 0.079 | **1st, ~10x** |
| Mission 2, lightweight | 0.691 | 0.725 | 0.949 | 3rd |
| Mission 1, lightweight | **0.103** | 0.690 | 0.786 | far behind |

On both full sets the result holds — slightly better, even — with the
exact preprocessing. The Mission 1 lightweight subset collapses.

**Why.** In Mission 1 the grid drops a sample whenever two arrive within
one 30-s bin, which happens sporadically (channel 41: 4.8% of samples,
median interval 30 s). Each dropped sample turns an ordinary step into an
unusual jump; those artefacts produce the highest costs in the training
years (channel 41: maximum 46.3 bits at a point where samples were 12.9 s
apart, against 32.2 bits on the original samples) and push the threshold
above every real event (0 of 106 event rows exceed it, against 9 on the
original samples). Mission 2 loses far more samples to the grid (50%:
median interval 18 s) but **regularly**, a pattern the model learns; it
is unaffected. A first prediction — that Mission 2 would lose few samples
— was wrong and refined the explanation: what hurts is *irregular* loss,
not the amount. A detector on board sees the original samples.

### Full tables (30-s grid)

Mission 1, full set (chosen: q=1.0, x1.25, mute):

| Rule | Muted channels | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q=0.999999 | 0 | 540 | 40 | 346 | 51 | 0.104 | 0.440 | **0.122** | 0.202 |
| q=0.999999, mute | 9 | 439 | 32 | 288 | 59 | 0.100 | 0.352 | **0.117** | 0.208 |
| q=0.999999, x1.25 | 0 | 119 | 26 | 56 | 65 | 0.317 | 0.286 | **0.310** | 0.394 |
| q=0.999999, x1.25, mute | 2 | 116 | 25 | 54 | 66 | 0.316 | 0.275 | **0.307** | 0.385 |
| q=0.9999999 | 0 | 152 | 28 | 88 | 63 | 0.241 | 0.308 | **0.252** | 0.431 |
| q=0.9999999, mute | 2 | 148 | 24 | 87 | 67 | 0.216 | 0.264 | **0.224** | 0.393 |
| q=0.9999999, x1.25 | 0 | 43 | 11 | 16 | 80 | 0.407 | 0.121 | **0.276** | 0.407 |
| q=0.9999999, x1.25, mute | 0 | 43 | 11 | 16 | 80 | 0.407 | 0.121 | **0.276** | 0.407 |
| q=1.0 | 0 | 113 | 24 | 59 | 67 | 0.289 | 0.264 | **0.284** | 0.436 |
| q=1.0, mute | 2 | 109 | 20 | 58 | 71 | 0.256 | 0.220 | **0.248** | 0.392 |
| q=1.0, x1.25 | 0 | 33 | 10 | 10 | 81 | 0.500 | 0.110 | **0.292** | 0.435 |
| q=1.0, x1.25, mute (chosen on validation) | 0 | 33 | 10 | 10 | 81 | 0.500 | 0.110 | **0.292** | 0.435 |

Mission 2, full set (chosen: q=0.999999, mute):

| Rule | Muted channels | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q=0.999999 | 0 | 468 | 252 | 60 | 110 | 0.808 | 0.696 | **0.783** | 0.606 |
| q=0.999999, mute (chosen on validation) | 14 | 395 | 239 | 37 | 123 | 0.866 | 0.660 | **0.815** | 0.653 |
| q=0.999999, x1.25 | 0 | 51 | 36 | 1 | 326 | 0.973 | 0.099 | **0.353** | 0.667 |
| q=0.999999, x1.25, mute | 0 | 51 | 36 | 1 | 326 | 0.973 | 0.099 | **0.353** | 0.667 |
| q=0.9999999 | 0 | 277 | 168 | 29 | 194 | 0.853 | 0.464 | **0.730** | 0.656 |
| q=0.9999999, mute | 6 | 230 | 149 | 25 | 213 | 0.856 | 0.412 | **0.704** | 0.703 |
| q=0.9999999, x1.25 | 0 | 23 | 19 | 0 | 343 | 1.000 | 0.052 | **0.217** | 0.760 |
| q=0.9999999, x1.25, mute | 0 | 23 | 19 | 0 | 343 | 1.000 | 0.052 | **0.217** | 0.760 |
| q=1.0 | 0 | 263 | 160 | 25 | 202 | 0.865 | 0.442 | **0.726** | 0.653 |
| q=1.0, mute | 6 | 213 | 141 | 20 | 221 | 0.876 | 0.390 | **0.701** | 0.709 |
| q=1.0, x1.25 | 0 | 18 | 17 | 0 | 345 | 1.000 | 0.047 | **0.198** | 0.850 |
| q=1.0, x1.25, mute | 0 | 18 | 17 | 0 | 345 | 1.000 | 0.047 | **0.198** | 0.850 |

Mission 1, lightweight (chosen: q=1.0, x1.25, mute):

| Rule | Muted channels | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q=0.999999 | 0 | 82 | 12 | 27 | 53 | 0.308 | 0.185 | **0.271** | 0.222 |
| q=0.999999, mute | 5 | 28 | 4 | 11 | 61 | 0.267 | 0.062 | **0.160** | 0.235 |
| q=0.999999, x1.25 | 0 | 30 | 7 | 17 | 58 | 0.292 | 0.108 | **0.217** | 0.538 |
| q=0.999999, x1.25, mute | 2 | 27 | 7 | 14 | 58 | 0.333 | 0.108 | **0.235** | 0.538 |
| q=0.9999999 | 0 | 20 | 5 | 15 | 60 | 0.250 | 0.077 | **0.172** | 1.000 |
| q=0.9999999, mute | 2 | 16 | 4 | 12 | 61 | 0.250 | 0.062 | **0.155** | 1.000 |
| q=0.9999999, x1.25 | 0 | 12 | 4 | 8 | 61 | 0.333 | 0.062 | **0.177** | 1.000 |
| q=0.9999999, x1.25, mute | 0 | 12 | 4 | 8 | 61 | 0.333 | 0.062 | **0.177** | 1.000 |
| q=1.0 | 0 | 19 | 5 | 14 | 60 | 0.263 | 0.077 | **0.177** | 1.000 |
| q=1.0, mute | 2 | 15 | 4 | 11 | 61 | 0.267 | 0.062 | **0.160** | 1.000 |
| q=1.0, x1.25 | 0 | 8 | 2 | 6 | 63 | 0.250 | 0.031 | **0.103** | 1.000 |
| q=1.0, x1.25, mute (chosen on validation) | 0 | 8 | 2 | 6 | 63 | 0.250 | 0.031 | **0.103** | 1.000 |

Mission 2, lightweight (chosen: q=0.999999, mute):

| Rule | Muted channels | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q=0.999999 | 0 | 169 | 129 | 15 | 221 | 0.896 | 0.369 | **0.697** | 0.849 |
| q=0.999999, mute (chosen on validation) | 2 | 145 | 117 | 7 | 233 | 0.944 | 0.334 | **0.691** | 0.860 |
| q=0.999999, x1.25 | 0 | 14 | 14 | 0 | 336 | 1.000 | 0.040 | **0.172** | 1.000 |
| q=0.999999, x1.25, mute | 0 | 14 | 14 | 0 | 336 | 1.000 | 0.040 | **0.172** | 1.000 |
| q=0.9999999 | 0 | 111 | 95 | 4 | 255 | 0.960 | 0.271 | **0.637** | 0.896 |
| q=0.9999999, mute | 1 | 108 | 93 | 4 | 257 | 0.959 | 0.266 | **0.630** | 0.903 |
| q=0.9999999, x1.25 | 0 | 8 | 8 | 0 | 342 | 1.000 | 0.023 | **0.105** | 1.000 |
| q=0.9999999, x1.25, mute | 0 | 8 | 8 | 0 | 342 | 1.000 | 0.023 | **0.105** | 1.000 |
| q=1.0 | 0 | 111 | 94 | 4 | 256 | 0.959 | 0.269 | **0.633** | 0.887 |
| q=1.0, mute | 1 | 108 | 92 | 4 | 258 | 0.958 | 0.263 | **0.627** | 0.893 |
| q=1.0, x1.25 | 0 | 6 | 6 | 0 | 344 | 1.000 | 0.017 | **0.080** | 1.000 |
| q=1.0, x1.25, mute | 0 | 6 | 6 | 0 | 344 | 1.000 | 0.017 | **0.080** | 1.000 |

## Two more rules, tried and not adopted

* **False-alarm budget** (`--budgets`): the threshold that allows at most k
  detections per year in nominal training data, an operational criterion
  robust to one extreme value. On the Mission 1 lightweight subset with the
  30-s grid it scores 0.271 (1/year) against 0.177 for the maximum on the
  test years, but validation (3 events, none detected under the grid)
  cannot tell the rules apart. Not adopted.
* **Time-aware thresholds** (`--time-aware`): separate thresholds for
  samples after a shorter-than-usual interval, a usual one, or a gap.
  Original samples, Mission 1 lightweight: 27 events found instead of 20,
  but 12 false detections instead of 0 (F0.5 0.611 vs 0.690): the rare
  short-interval class gets a low threshold from few training samples.
  Validation tied and kept the simpler rule.
