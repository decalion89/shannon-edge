# Do real anomalies break a balance law hidden below the noise floor? Pre-registration

Committed before the test. The script is
`bench/discovery/hidden_law.py`.

## The law (found on training data only, before this file)

On ESA Mission 1, with the first 4,000,000 training samples (before
2006-10-01), the sample-to-sample increments of channels 41, 43 and 45
nearly cancel:
* var(Δ41 + Δ43 + Δ45) is **0.178x** the sum of their variances.
* No other triple of channels 41–46 is below 0.30.
* Their levels do not sum to a constant: the balance holds for the
  fine, fast fluctuations, below the noise scale the protocol discards.
  It looks like a shared reference or supply.

The labels were not looked at.

## Test (fixed)

* **Violation statistic of a window:** mean of (Δ41 + Δ43 + Δ45)² in
  the window, divided by its training mean.
* **Events:** labelled events touching channels 41–46 that start in the
  test period (from 2007-01-01), excluding communication gaps and
  windows shorter than 2 samples.
* **Controls:** for each event, one unlabelled test-period window of
  the same length, drawn at random (seed 0).
* **On-board alarms:** the Kraft rule of `esa_edge_link.py` on channels
  41–46. An event is "missed" if no alarm falls in its window.

## Hypotheses

* **V1.** Events show more violation than controls: one-sided
  Mann–Whitney AUC ≥ 0.65 and p < 0.01.
* **V2.** On events the on-board detector misses, AUC ≥ 0.60 and
  p < 0.05. The hidden law would then see what surprise does not.

A breakdown by anomaly class is reported.

## Meaning

**If V1 and V2 hold:** a law found only in the "noise" detects real
anomalies, including ones the compressor's surprise misses. That turns
discarded noise into a new diagnostic channel.

**If they fail:** the balance is real, but anomalies do not show up in
it on this mission.

## Result (run once; `bench/results/data/hidden_law.csv`)

```
55 test events (16 with an on-board alarm, 39 without)
V1 all events: AUC 0.924, p = 8.6e-15 (needs AUC >= 0.65 and p < 0.01): HOLDS
V2 events the on-board detector misses: AUC 0.909, p = 2.55e-10 (needs AUC >= 0.60 and p < 0.05): HOLDS
           n    V_event  V_control  alarmed
cls                                        
class_10   1      0.874      0.814    0.000
class_12   2      1.277      0.797    0.000
class_14  16     10.753      0.763    0.125
class_15   2      0.795      0.794    0.000
class_16   4      0.908      0.802    0.000
class_17   2      3.137      0.749    0.000
class_2    2      1.309      0.756    0.000
class_22   1      1.070      0.762    0.000
class_3   13  16622.679      0.443    1.000
class_4    3      2.893      0.828    0.333
class_8    8      0.908      0.824    0.000
class_9    1    761.967      0.766    0.000
```

* **V1 holds:** AUC 0.924, p = 8.6·10⁻¹⁵.
* **V2 holds:** on the 39 of 55 test events the on-board Kraft detector
  misses, AUC 0.909, p = 2.6·10⁻¹⁰.

### Confound check (post hoc, done immediately, same windows)

**The concern.** A jump in any one channel also raises
(Δ41 + Δ43 + Δ45)², so the statistic may measure plain **activity**
rather than a broken law.

**Comparison** with the activity statistic
A = mean of Δ41² + Δ43² + Δ45², normalised the same way, and with the
scale-free "pure violation" V/A:

| Events | AUC: law statistic V | AUC: activity A | AUC: pure violation V/A |
|---|---:|---:|---:|
| all 55 | 0.924 | 0.899 | 0.677 |
| 39 missed on board | **0.909** | 0.822 | 0.618 |

**What this means:**
* **Most of the detection power is activity:** a rise in fine-scale
  fluctuation during anomalies. The per-sample Kraft threshold
  (t = 26 bits) is too strict to fire on it. A windowed fine-scale
  activity detector alone reaches AUC 0.82 on the missed events. This is
  a practical finding, but variance-change detection is well known.
* **The hidden law adds information beyond activity:** +0.09 AUC on the
  missed events (0.909 vs 0.822). Its scale-free violation alone gives
  AUC 0.62–0.68. The balance does break during anomalies, but
  moderately.
* **Interpretation:** the noise the protocol discards carries
  **detection information the on-board detector does not use.** Mostly
  that is fine-scale activity, and partly the breaking of a balance
  that exists only below the noise floor.

**Caveats:**
* One mission, one law, 55 events.
* The confound check is post hoc. A pre-registered replication on
  another channel group would be needed before claiming the law adds
  value in general.
