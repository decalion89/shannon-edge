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

## Every ESA-ADB metric, computed with ESA-ADB's own code

`--official PATH` imports ESA-ADB's metric modules (`ESAScores`,
`ChannelAwareFScore`, `ADTQC`; MIT) unmodified from a checkout and scores
the rule chosen on validation with all of them. The test labels are built
as ESA-ADB builds them: target channels, events entirely inside the test
period, anomaly-type columns. Subsystems come from `channels.csv`. A
flagged sample covers the interval up to the next sample. Original samples.

    python3 bench/anomaly_esaadb.py ESA-Mission1.zip --channels 41 42 43 44 45 46 \
        --quantiles 1.0 --official ESA-ADB/

**Cross-check.** ESA-ADB's code reproduces our corrected event-wise F0.5
exactly on three of the four settings: 0.690, 0.725 and 0.798. On Mission 1
full it gives 0.284 instead of our 0.279: it counts one more event as
detected (40 of 91), because a flag covers the interval up to the next
sample, which reaches into one more event.

Published values: ESA-ADB Table 2 (all events except communication gaps).
The rank counts ours among the published algorithms that report the metric.
The benchmark ranks hierarchically, corrected event-wise F0.5 first.

| Metric | sedge | Best published | Rank |
|---|---:|---:|---:|
| **Mission 1, lightweight (6 channels, 65 events)** | | | |
| Corrected event-wise F0.5 | 0.690 | 0.786 (Telemanom-ESA-Pruned) | 2nd of 12 |
| Alarming precision | 0.833 | 0.875 (Telemanom-ESA-Pruned) | 3rd |
| ADTQC score | **0.949** | 0.901 (DC-VAE-ESA STD3) | **1st** |
| Affiliation-based F0.5 | 0.525 | 0.734 (DC-VAE-ESA STD5) | 7th |
| Channel-aware F0.5 | 0.205 | 0.837 (Telemanom-ESA) | 6th of 7 |
| **Mission 1, full set (58 channels, 91 events)** | | | |
| Corrected event-wise F0.5 | **0.284** | 0.061 (Telemanom-ESA-Pruned) | **1st** |
| Alarming precision | **0.388** | 0.206 (Telemanom-ESA-Pruned) | **1st** |
| ADTQC score | **0.894** | 0.752 (DC-VAE-ESA STD3) | **1st** |
| Affiliation-based F0.5 | **0.636** | 0.607 (Telemanom-ESA-Pruned) | **1st** |
| Subsystem-aware F0.5 | 0.384 | 0.689 (Telemanom-ESA) | 7th of 7 |
| Channel-aware F0.5 | 0.180 | 0.477 (Telemanom-ESA) | 7th of 7 |
| **Mission 2, lightweight (11 channels, 350 events)** | | | |
| Corrected event-wise F0.5 | 0.725 | 0.949 (Windowed iForest) | 3rd of 12 |
| Alarming precision | 0.813 | 0.912 (Telemanom-ESA) | 3rd |
| ADTQC score | 0.996 | 0.999 (PCC) | 5th |
| Affiliation-based F0.5 | 0.599 | 0.976 (iForest) | 9th |
| Channel-aware F0.5 | 0.220 | 0.822 (Telemanom-ESA) | 7th of 7 |
| **Mission 2, full set (47 channels, 362 events)** | | | |
| Corrected event-wise F0.5 | **0.798** | 0.079 (PCC) | **1st** |
| Alarming precision | 0.689 | 0.790 (Telemanom-ESA-Pruned) | 3rd of 11 |
| ADTQC score | 0.972 | 0.993 (GlobalSTD5) | 5th |
| Affiliation-based F0.5 | 0.714 | 0.831 (GlobalSTD5) | 4th |
| Subsystem-aware F0.5 | 0.541 | 0.969 (GlobalSTD5) | 5th of 7 |
| Channel-aware F0.5 | 0.221 | 0.791 (GlobalSTD3) | 7th of 7 |

Supporting values (precision / recall):

| Setting | Event-wise | Affiliation | Channel-aware | Subsystem-aware | ADTQC after ratio |
|---|---|---|---|---|---:|
| Mission 1, lightweight | 1.000 / 0.308 | 0.650 / 0.297 | 0.308 / 0.103 | 0.308 / 0.308 | 1.000 |
| Mission 1, full | 0.261 / 0.440 | 0.683 / 0.500 | 0.386 / 0.072 | 0.440 / 0.277 | 0.975 |
| Mission 2, lightweight | 0.914 / 0.397 | 0.697 / 0.385 | 0.394 / 0.091 | 0.397 / 0.397 | 1.000 |
| Mission 2, full | 0.894 / 0.558 | 0.773 / 0.545 | 0.547 / 0.078 | 0.550 / 0.527 | 1.000 |

What this shows:

* **Under the benchmark's own hierarchy (event-wise F0.5 first) the
  surprise is the best method on both full sets.** On Mission 1 full it is
  also best on every secondary metric except channel attribution.
* **Timing is a strength.** The after ratio is about 1: the surprise never
  fires before an event starts, because it is not a forecaster. Mission 1
  ADTQC is the best published on both channel sets.
* **Channel attribution is the clear weakness**: last on channel-aware F0.5
  in all four settings. Channel recall is 7–10%. When an event is detected,
  only one or two of the many channels ESA labels as affected cross their
  thresholds; the detection is right, the list of channels is too short. The
  next improvement targets this.
* The lightweight subsets keep the weaknesses already reported: recall.

## Training-free thresholds (Kraft) and the unlabelled detections

**The bound.** Code a sample in an alphabet of 2^b values. A calibrated
model assigns it more than b + t bits with probability at most 2^-t: at
most 2^b outcomes can each have probability at or below 2^-(b+t). A
threshold of b + t bits therefore needs no training data. `--kraft auto`
sets t = ceil(log2(test samples over all target channels)): at most one
expected false sample-alarm in the whole test set if the model is
calibrated.

**Does the flight model obey it?** On Mission 1 channels 41–46, nominal
training samples (7.63 M per channel):

* With margins up to 20 bits, every channel exceeds b + t less often than
  2^-t. At t = 4 to 16 the margin is 10 to 400 times.
* At t = 24 and 28, one sample in 7.6 M on channel 43 exceeds the bound.
  At t = 24 that is expected by chance; at t = 28, under one in 30
  (Poisson).

Script: `bench/analysis/kraft_calibration.py ESA-Mission1.zip 2007-01-01 41 42 43 44 45 46`.

**Scores.** Corrected event-wise F0.5, rule fixed a priori by `auto`, not
chosen on validation:

| Setting | t (auto) | Kraft, no training | Trained, chosen on validation | Best published |
|---|---:|---:|---:|---:|
| Mission 1, lightweight | 26 | **0.705** (0 false alarms; ADTQC 1.000) | 0.690 | 0.786 |
| Mission 1, full set | 29 | **0.576** (3 false alarms, 22 events) | 0.279 | 0.061 |
| Mission 2, lightweight | 26 | 0.200 (recall 0.049) | 0.725 | 0.949 |

On Mission 1 the training-free rule beats the trained one. On Mission 1
full it scores 9x the best published method. On Mission 2 lightweight the
a-priori margin is far too strict: the mission has 350 short labelled
events, most below b + 26 bits. For the record, smaller margins score 0.509
(t = 16) and 0.582 (t = 20); they were not chosen, since that choice would
look at the test.

The bound guarantees the false-alarm rate; it does not say how much risk
a mission should accept.

**What are the unlabelled detections?** `--report` on Mission 1 full
(trained rule, 113 detections that overlap no labelled event in any
channel), analysed by `bench/analysis/spikes.py`:

* The two strongest are one-sample spikes in two channels of the same
  physical unit (channels 57 and 59, subsystem 6, group 13) on the same
  day, 2009-04-18, with no label anywhere. Their excess over the
  threshold is 29 and 14 bits.
* 44 of the 113 are single-sample excursions: the value jumps and the
  next sample returns. Measured in local quantisation steps, their sizes
  cluster at **16–19 steps** in 12 different channels (20 of 43; peak at
  17). A physical event would have no reason to share an amplitude across
  sensors measured in different units. This points to a common
  acquisition effect.
* Hypothesis tested and rejected: radiation bit flips. A flip moves the
  raw code by exactly 2^k, but only 8 of the 35 excursions of 3 or more
  steps are powers of two, close to chance (3 of the 17 sizes from 3 to
  19 are powers of two).

Whether these spikes matter to operators (data errors, acquisition
glitches, or events worth a label) cannot be decided from the data
alone. They are listed with times and channels for an expert to check.

**Correction, after a census** (`bench/analysis/spike_census.py`, 18
channels, the whole mission). One-sample spikes are not rare at all:
* 26.1 M in total, of which 1.3 M are of 8 steps or more.
* Their sizes fall off smoothly: 8 steps 328 k, 9 167 k, 10 157 k …
  16 73 k, 17 32 k, 18 22 k, 19 12 k.

The clustering at 16–19 steps among the *detections* is a selection
effect: those are simply the largest spikes, the ones that cross the
threshold. It is not a distinct phenomenon. Most of these channels carry
heavy-tailed, spiky noise at the sample level. The genuinely unexplained
candidates are those both far from labels and coincident across channels
of one unit, such as channels 57 and 59 on 2009-04-18.

**2009-04-18, examined, and not rare.** Results:
* At 01:24 no telecommand was sent in the previous 30 minutes. Besides
  channel 57, only channel 47 jumps, and both are in physical unit 3.
* At 19:14, five unit-3 channels jump together, by 9–18 times their
  typical step: channels 18, 20, 24, 31 and 59. The last telecommands
  were 22 minutes earlier.
* The base rate is the deciding test. Over 2009, 2.0% of random 4-minute
  windows have at least five of unit 3's 42 channels jumping by more than
  8 typical steps. That is roughly 2,600 such windows a year. 15% of
  windows have three or more.

The 19:14 coincidence is ordinary for this unit, and the candidate does
not survive.

After three checks of this kind (a near-miss label, a selection effect, a
base rate), **no unlabelled event in this data stands out as a missed
anomaly.** The compressor flags what is rare for its model, and in these
channels rare-looking bursts are common.

## Cumulative Kraft (`--kraft-cusum`): a gain where the model is calibrated, a collapse where it is not

Per channel, CUSUMs of the per-sample e-values log2((1−e) + e·2^(cost−b))
are run for four values of e. A calibrated model gives each increment
expectation at most 1, so with t = log2(test samples) + 2 bits the
expected number of false alarms is at most 1, as for `--kraft auto`. The
difference is that evidence from several moderately surprising samples
now adds up. No training.

| Setting | Per-sample Kraft | Cumulative Kraft | Trained | Best published |
|---|---:|---:|---:|---:|
| Mission 1, lightweight | 0.705 | **0.766** (recall 0.477; validation also picks it) | 0.690 | 0.786 |
| Mission 1, full set | 0.576 | 0.000 (9 detections covering the test) | 0.279 | 0.061 |
| Mission 2, lightweight | 0.200 | 0.000 (2 detections covering the test) | 0.725 | 0.949 |

On Mission 1 lightweight the official code gives:
* alarming precision 0.939;
* affiliation F0.5 0.605 (per-sample rule: 0.536);
* channel-aware F0.5 0.340;
* ADTQC 0.580, down from 1.000. Accumulated evidence can cross the
  threshold before the labelled start.

**Can validation pick a better margin? No.** With `--cusum-offsets -6 -4
-2 0 2 4` on Mission 1 lightweight, the test scores are:

| Margin t (bits) | 20 | 22 | 24 | **26 (a priori)** | 28 | 30 |
|---|---:|---:|---:|---:|---:|---:|
| Test event-wise F0.5 | 0.717 | 0.742 | 0.751 | **0.766** | 0.747 | 0.666 |

Validation, with only 3 events, picks t = 30, which scores 0.666 on test.
No margin reaches the best published 0.786. The a-priori margin is the
best of the grid, but choosing it after seeing the test would not count.

**Why it collapses elsewhere.** The guarantee assumes calibration, and
accumulation punishes even mild overconfidence. On Mission 2, channels
18–20 exceed b + t bits about 4 times more often than 2^−t at t ≥ 16
(`bench/analysis/kraft_calibration.py`). That is harmless for one sample
at a time and fatal when summed over millions of samples.

The cumulative rule is therefore not adopted. It needs a model that
measures and corrects its own overconfidence online.

**Self-calibration (`--self-calibrate`): tried, does not rescue it.**
Each channel estimates online, from its own past and without labels, how
overconfident its model is. D is the largest log2(observed tail rate ×
2^m) over margins m = 4..24 seen at least 10 times. Costs are then lowered
by D bits.

The estimate is consistent with the calibration table. The test-period
median of D is:

| Channels | D (bits) |
|---|---:|
| 18, 19, 20 | 5.3, 6.0, 3.6 |
| 25–28 | 1.5–2.0 |
| others | 0 |

It does not help. On Mission 2 lightweight the per-sample rule drops to
0.067, because the higher bar removes real detections, and the cumulative
rule still collapses. The overconfidence is clustered in time: in bursts
the model is far more overconfident than on average. A constant correction
cannot fix that. A local one would also absorb the slow anomalies that the
cumulative rule is meant to find. This is a real trade-off, not a bug.

**Correction.** An earlier version of this section called the strongest
"unlabelled" cumulative detection on Mission 2 lightweight a candidate
missed event: 2002-09-09 22:43, nine channels, peaking at 39 bits, for
hours. It is not. ESA labels the rare event `id_368` (class_19) on
channels 21–28 from 22:42:01 to 22:43:15. The detection starts 16 s after
that label ends, so the exact-overlap test in `--report` missed it. The
cumulative statistic then carries the event's evidence for hours: it is
the tail of a labelled event.

The Mission 1 full candidates were checked again against the distance to
any label boundary, in any channel. 98 of the 113 unlabelled detections
are more than a day away. The strongest, channels 57 and 59 on
2009-04-18, are about 25 days from any label.

## Naming the affected channels

**The ceiling.** ESA-ADB's channel-aware F0.5 averages a per-event score,
and a missed event scores 0. So it cannot exceed event recall. On
Mission 1 lightweight, 62 of the 65 test events label all 6 channels.
Of the 120 affected channel slots in the 20 detected events, the detector
flags 40 and none wrongly. The loss is 0.692 from missed events, 0.103 from
missed channels in detected events and 0 from extra channels.

**Kraft attribution (`--attribute`, no training, no parameter).** Around
each detection (± the merge window), name every channel whose cost reaches
b + log2(samples examined in that window over all channels) bits. That is
at most one expected false channel per detection if the model is
calibrated. Detections are not changed, so event-wise scores stay the
same. Official code:

| Setting | Channel recall | Channel precision | Channel-aware F0.5 | Best published |
|---|---|---|---|---:|
| Mission 1, lightweight | 0.103 → 0.244 | 0.308 → 0.308 | 0.205 → **0.289** | 0.837 |
| Mission 2, lightweight | 0.091 → 0.291 | 0.394 → 0.394 | 0.220 → **0.363** | 0.822 |
| Mission 1, full set | 0.072 → 0.144 | 0.386 → 0.395 | 0.180 → **0.255** | 0.477 |

A tuned alternative from an independent analysis (in the session
scratchpad, not in the repository) gives about the same. It propagates an
alarm to the other channels of its subsystem whose cost exceeds s times
their threshold, with s chosen on validation: 0.299 (Mission 1
lightweight) and 0.349 (Mission 2 lightweight). Both stay well below the
best published because **the real limit is event recall**: Telemanom-ESA
reaches 0.837 with event recall 0.894, at an event-wise F0.5 of 0.178.

**A finding about the thresholds.** On Mission 1 lightweight, in every
channel the highest "nominal" training cost (which becomes the trained
threshold) lies within 36 s of a labelled event boundary. It is the event
spilling past its label. Channel 43, for example, gets 40.4 bits, against
25.5 with a 60-s guard band around labels.

Ignoring training samples near labels raises test event recall: Mission 1
from 0.308 to 0.415, and Mission 2 test event-wise F0.5 to 0.812. But
validation cannot tell the guard band from no guard band, so the
validation rule does not adopt it. On Mission 1 test it lowers event-wise
F0.5 to 0.600. A longer validation window is the honest way to decide.

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

## Persistent score: partly closing the weak spot

Grid artefacts in Mission 1 are isolated spikes (one unusual jump, then
normal again); a real anomaly tends to last. `--persist` scores each sample
by the minimum of its cost and the next sample's (one sample of delay), so
isolated spikes vanish. Mission 1 lightweight subset, rule chosen on
validation (maximum of training nominal cost in both cases):

| Mission 1, lightweight | Without `--persist` | With `--persist` |
|---|---:|---:|
| 30-s grid (the weak spot) | 0.103 | **0.238** (0.292 for the 0.999999 quantile, not chosen) |
| Original samples | **0.690** | 0.609 |

It more than doubles the score where the grid hurts, and costs some where
there are no artefacts to remove (it also erases genuinely brief
anomalies). So it is an option for irregularly resampled inputs, not a
default: a detector on board, seeing the original samples, should not use
it. The weak spot is narrowed, not closed (0.238 vs 0.786 for the best
published method there).

## Does surprise rise before anomalies? No (`bench/analysis/early_warning.py`)

**Question.** Complex systems often grow erratic before a tipping point
("early-warning signals", Scheffer et al., 2009). If spacecraft do too,
the median surprise would rise in the days before an anomaly.

**Method.** For each "Anomaly" event, take the median surprise of its
labelled channels over the 3 days before its start, divided by the median
over the window 30 to 10 days before. The ratio, in log2, is compared with
the same ratio at random placebo times.

| Mission | Events with data | Mean log2(pre / base) | Placebo mean | One-sided p |
|---|---:|---:|---:|---:|
| Mission 1, lightweight | 51 | +0.001 | −0.001 (sd 0.011) | 0.16 |
| Mission 2, lightweight | 19 | −0.089 | −0.012 (sd 0.065) | 1.00 |

The Mission 2 placebo times only need to be 3 days from any event,
because its events are too dense for a 30-day gap. On these data, no
early warning is visible in the compressor's surprise. The compressor is a
detector, not a predictor. This agrees with ADTQC's after-ratio of about 1:
the surprise never fires before an event starts.

## The packet's size is an anomaly score (`bench/analysis/packet_size_priority.py`)

**Why it works.** A compressed packet is short when its samples were
predictable and long when they surprised the model. Its size is
therefore an anomaly score, and anyone on the path can read it without
decoding: the spacecraft, a relay or the ground. When the downlink is
short, sending the largest packets first sends the surprising data first.

**Method.** Flight profile, 256 samples per packet, all test packets of
the lightweight channels ranked by size. Each top fraction is compared
with the same number of random packets (mean of 20 draws).

| Mission | Top packets by size | Share of test time | Anomalies overlapped | Random | Rare events overlapped | Random |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 1% | 1.70% | **16/29** | 4.9 | **27/36** | 6.7 |
| 1 | 5% | 5.67% | **26/29** | 9.9 | **31/36** | 17.6 |
| 2 | 1% | 1.00% | 0/1 | 0.2 | 94/349 | 71.3 |
| 2 | 5% | 5.00% | 0/1 | 0.7 | 214/349 | 218.2 |

* **Mission 1:** the 1% largest packets touch 55% of the anomalies and 75%
  of the rare events, 3–4 times more than chance. The 5% largest touch
  90% of the anomalies.
* **Mission 2:** the gain is small at 1% and nil at 5%. Its 350 rare
  events are dense and long, so random packets touch them too.

Prioritising the downlink by compressed size is free, needs no detector
and no decoding, and on Mission 1 it brings most anomalies to the ground
first.

## Surprise-first downlink under a daily budget (`bench/analysis/surprise_first_downlink.py`)

**Scenario.** Each test day may send only a fraction of that day's
compressed bytes (flight profile, 256-sample packets). Two policies:
* FIFO: packets in time order, today's practice;
* surprise-first: the largest packets first, read from their size alone.

An event is delivered that day if a packet that overlaps it on one of its
labelled channels was sent.

| Mission | Daily budget | FIFO: anomalies / rare events | Surprise-first: anomalies / rare events |
|---|---:|---:|---:|
| 1 | 5% | 11/29 / 15/36 | **24/29 / 30/36** |
| 1 | 10% | 16/29 / 25/36 | **27/29 / 34/36** |
| 1 | 25% | **29/29 / 36/36** | 27/29 / 35/36 |
| 2 | 5% | 0/1 / **172/349** | 1/1 / 154/349 |
| 2 | 10% | 1/1 / **340/349** | 1/1 / 177/349 |
| 2 | 25% | 1/1 / **348/349** | 1/1 / 232/349 |

* **Mission 1, tight budgets (5–10%):** surprise-first brings 2–2.2x as
  many anomalies down the same day (24 vs 11, 27 vs 16).
* **Larger budgets, and Mission 2:** FIFO is better.
  * Mission 2's rare events are long and dense, so the first packets of
    each day already overlap them.
  * Surprise-first spends the budget on a few channels' largest packets
    and leaves other channels empty.
* A fairer policy is the obvious next step and is not measured: largest
  first *within* each channel, round-robin across channels.
* **This is a regime result, not a universal one:** surprise-first wins
  when the downlink is scarce and anomalies are short.

## How much information do anomalies carry? (`bench/analysis/anomaly_information.py`)

**Question.** We measured what share of a mission's information, in bits
paid by the flight profile online, falls inside labelled events, and
compared it with the share of time they take.

| Mission (channels) | Category | Share of samples | Share of information | Concentration | Bits/sample inside | Bits/sample overall |
|---|---|---:|---:|---:|---:|---:|
| 1 (41–46) | Anomaly | 0.433% | 0.466% | 1.1x | 4.22 | 3.92 |
| 1 | Rare Event | 0.769% | 0.812% | 1.1x | 4.14 | 3.92 |
| 2 (18–28) | Anomaly | 1.111% | 1.064% | 1.0x | 7.81 | 8.15 |
| 2 | Rare Event | 1.707% | 1.985% | 1.2x | 9.48 | 8.15 |

**Finding, on these data.** Labelled events carry about as much
information per sample as normal operation (1.0–1.2x). Yet the same
events are detected by single-sample peaks of 18–31 bits above b. The two
facts fit only one way: **an event's information is concentrated in a
few dozen bits at its onset, and the rest of its labelled interval is as
ordinary to the model as any other time.**

This one observation accounts for several other results:
* timing that is never early (ADTQC after-ratio about 1);
* slow events that are missed;
* no early-warning signal;
* rare values kept exact for about 0.1% of the downlink.

It is a measurement on two missions with one model, not yet a general law.
