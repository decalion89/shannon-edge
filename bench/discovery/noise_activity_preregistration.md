# Is the discarded noise a diagnostic channel? Replication, pre-registration

Committed before the run. The script is
`bench/discovery/noise_activity.py`.

**Why.** On Mission 1 channels 41–46 (`hidden_law_preregistration.md`),
anomalies the on-board Kraft detector missed (39 of 55) were separated
from control windows with AUC 0.82 by fine-scale activity alone. That
check was post hoc. This replicates the activity finding, which is the
larger effect, on two channel groups never used for it:
* **Mission 2, channels 18–20:** training before 2001-07-01, test from
  2001-10-01.
* **Mission 1, channels 14, 21, 29, 30, 38:** subsystem 6, group 4;
  shared 90 s timestamps; training before 2006-10-01, test from
  2007-01-01.

**Statistic (fixed).** For a window: the mean of Σ_c (Δ_c / s_c)², with
s_c the channel's training standard deviation of increments,
normalised by the training mean.

**Events, controls and alarms** are defined as in `hidden_law.py`:
* events touching the set's channels and starting in the test period;
* communication gaps excluded, and windows of at least 2 samples;
* one random unlabelled control window of the same length per event,
  from the test period (seed 0);
* "missed" means no on-board Kraft alarm on the set's channels in the
  window.

**Hypotheses, for each set separately:**
* **R1.** All events: AUC ≥ 0.65, one-sided Mann–Whitney p < 0.01.
* **R2.** Missed events: AUC ≥ 0.60, p < 0.05.

**Meaning.** If R1 and R2 hold on both sets, the noise that every
error-bounded scheme discards carries detection information the
compressor's surprise does not use, on two missions. The design
consequence: the spacecraft should **monitor** its discarded noise and
send an alarm when its activity changes, instead of dropping it.

## Result (run once; `bench/results/data/noise_activity.csv`)

```
M2-18-20: 349 test events, 325 missed on board
  R1 all events: AUC 1.000, p = 7.49e-116 (needs >= 0.65, p < 0.01): HOLDS
  R2 missed events: AUC 1.000, p = 5.13e-108 (needs >= 0.60, p < 0.05): HOLDS
M1-group4: 50 test events, 45 missed on board
  R1 all events: AUC 0.472, p = 0.687 (needs >= 0.65, p < 0.01): REFUTED
  R2 missed events: AUC 0.440, p = 0.836 (needs >= 0.60, p < 0.05): REFUTED
```

**Mixed result:**
* **Mission 2, channels 18–20: R1 and R2 hold,** with AUC 1.000 on all
  349 events and on the 325 the on-board detector misses.
* **Mission 1, group 4: R1 and R2 are refuted** (AUC 0.47 and 0.44, no
  signal).

**Why the Mission 2 result is "perfect" (checked immediately).**
* Control windows have activity 0.02 times the training mean (median;
  90th percentile 0.03). Events have a median of 8.7.
* In Mission 2, labelled events (mostly class_19 "Rare Event") **are**
  bursts of fine-scale activity, while unlabelled test periods are
  almost still.
* The per-sample Kraft threshold (t = 31 bits) is too strict to fire on
  these bursts. Any windowed activity measure separates them. That is
  consistent with the windowed e-value rule scoring 0.724 on this
  mission (`esa_chronological.md`).
* So the separation is real but easy. It says more about the on-board
  per-sample rule's blind spot than about hidden structure in the
  noise.

**Why Mission 1 group 4 fails.** Its events are mostly class_7, the
recurring class that surprise also misses. They do not change
fine-scale activity at all.

**Conclusion.**
* The discarded noise is a useful diagnostic channel where anomalies
  are activity bursts: Mission 2, and Mission 1 channels 41–46.
* It is useless where anomalies are shape or level patterns: class_7.
* It is not a general unlock. Its practical value is a cheap windowed
  activity alarm alongside the per-sample Kraft alarm.
* class_7 remains invisible to surprise, to activity and to fine-scale
  balance.
