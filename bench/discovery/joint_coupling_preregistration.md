# Does the coupling between sensors break during real anomalies? Pre-registration

Committed before the run. The script is
`bench/discovery/joint_coupling.py`.

## Why a new test

The "joint-only" tests (`joint_only_preregistration.md`,
`joint_only_confirm_preregistration.md`) were confounded. Their joint
statistic was a cost difference that responds to **any** change,
including a marginal change of one channel. So it could not show that
the *relationship* between sensors had changed.

This test removes the marginals **by construction**:
* inside each window, every channel is quantised by its own ranks into
  8 equal-count levels, so each channel's levels are uniform whatever
  its values do;
* the statistic compares the true pairing of x and y with a circularly
  shifted pairing of the **same values**.

**Coupling of the ordered pair x → y in a window:**
I = H(y_t | y_{t−1}, x shifted by half the window) − H(y_t | y_{t−1}, x_t),
using plug-in conditional entropies in bits per sample.

It measures what x's true timing tells about y beyond y's own past.

## Synthetic check, run before this commit

Two coupled random-walk channels, 200,000 samples:

| Window | p | Flagged |
|---|---:|---|
| coupling broken for 300 samples (y replaced by its own values from elsewhere) | 0.0005 | yes |
| a normal window | 0.076 | no |
| both channels shifted together by +50 | 0.98 | no |

## Data

All three event sets of the earlier runs:
* **M1-light:** Mission 1, channels 41–46.
* **M1-groups:** Mission 1, channels 14, 21, 29, 30, 38 and 70–76, only
  events not touching 41–46, aligned onto channel 14's timestamps.
* **M2-light:** Mission 2, channels 18–28.

**Disclosure.** These events were seen before under different
statistics, never under this one. The statistic was designed from the
diagnosis of the confound, not tuned on these events.

## Procedure (fixed)

* **Pairs.** Per set, the C ordered pairs (C = number of channels) with
  the highest median coupling over 200 random normal training windows
  of 512 samples. Only coupled pairs can break.
* **Events.**
  * Each event's window runs from its earliest labelled start to its
    latest end on the set's channels.
  * Events shorter than 64 samples are untestable.
  * Windows longer than 2,000 samples use their central 2,000.
* **Null.**
  * 1,999 random windows of the same length inside unlabelled training
    data; the random generator is seeded with 0.
  * One-sided p = (1 + #{null I ≤ observed I}) / (1 + #valid null).
  * A pair is skipped in a window where either channel has fewer than 4
    distinct values, and needs at least 200 valid null windows.
* **Broken:** min p over the testable pairs ≤ 0.01 / (number of
  testable pairs).
* **Controls** (the check the earlier tests lacked). For every event,
  one unlabelled window of the same length is drawn at random from
  **after** the training period and tested identically against the same
  null. This measures the flag rate from drift and chance alone.

## Hypothesis

* **R1.** Pooled over the three sets, the share of events flagged
  "broken" exceeds the share of control windows flagged:
  * the difference is ≥ 5 percentage points;
  * the one-sided Fisher exact test gives p < 0.01.

**Also reported:**
* per-set rates for events and controls;
* the event rate with its Wilson CI;
* the cross-tabulation by ESA locality.

## Meaning

**If R1 holds:** during a measurable share of real anomalies, the
coupling between sensors breaks beyond what drift explains. That
coupling is invisible to per-sensor statistics by construction: no
statistic of one sensor's own values can see it.
* By the zero-rate theorem (Shalaby and Papamarcou 1992), a design that
  ships only per-sensor alarms cannot exploit it.
* Such a design may still see the same event through a marginal change.
  That share is a separate question, not claimed here.

**If R1 fails:** no coupling signal beyond drift is shown on these
data, and that is reported.
