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

## Result (run once; `bench/results/data/joint_coupling.csv`)

A first launch ran out of memory on Mission 2 before writing anything.
It cached the valid null starts for every event length; the cache was
removed and nothing else changed.

| Set | Events broken | Controls broken |
|---|---:|---:|
| M1-light | 3/65 | 0/65 |
| M1-groups | 5/43 | 2/43 |
| M2-light | 30/603 | 2/603 |
| **Pooled** | **38/711 = 5.3%** (95% CI 3.9–7.3%) | **4/711 = 0.6%** |

**R1: REFUTED.** The difference is 4.8 percentage points, below the
pre-set 5, although one-sided Fisher p = 1.9·10⁻⁸.

**What the data do say:**
* The coupling between sensors breaks during real anomalies about
  **9 times as often** as in control windows from the same period.
  That effect is unmistakable.
* But it affects only about **1 event in 20**, just under the size
  threshold set in advance.

**Post hoc, not results:**
* The rate differs by class:
  * Mission 2 class_30: 20/83 broken;
  * Mission 1 class_7, the recurring class that surprise misses: 5/42;
  * Mission 2 class_19, the commonest class: 6/343.
* Of the 38 broken events, 32 were also visible to per-channel tests in
  the level-frequency diagnostic, and 6 were not. So most coupling
  breaks come with a marginal change a per-sensor alarm could see.
  The events that only a joint test can see are, on these data,
  **about 6 in 711 (under 1%)**.

**Conclusion for the zero-rate question.** On ESA's spacecraft
telemetry, anomalies that exist only between sensors are rare: about
1% of events. The 15–67% figures of the earlier, confounded tests were
artefacts. Per-sensor alarms lose little here. The theorem's blind spot
is real but small on these data.
