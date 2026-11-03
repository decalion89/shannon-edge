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
