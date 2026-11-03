# Joint-only anomalies: confirmation on fresh events. Pre-registration

Committed before the confirmation is run. The script is
`bench/discovery/joint_only_confirm.py`.

## Why

**Exploratory run** (`joint_only_preregistration.md`, ESA Mission 1
channels 41–46 and Mission 2 channels 18–28):
* J1 held: the joint-only share was 29% and 51%.
* J2 was refuted in the opposite direction: joint-only was more common
  among Global anomalies than among Local ones.
* The likely flaw was a weak local test. It used first-order
  transitions only, so a channel parked at a rare level looks normal.

**Post-hoc diagnostic** (`--marginal`, which adds a level-frequency
local test):
* joint-only falls to **17.5%** (Mission 1, 95% CI 11.7–25.6%) and
  **15.8%** (Mission 2, 13.1–18.9%);
* J2 then holds in the predicted direction (Local 24% vs Global 15%,
  one-sided Fisher p = 0.034).

That diagnostic is post hoc. It needs data it has not seen and an even
stronger local test.

## Data (fresh for this question)

* **ESA Mission 1, whole mission; training before 2006-10-01.**
  Channels 14, 21, 29, 30, 38 (subsystem 6, group 4) and 70–76
  (subsystem 3, group 18). These are the two groups with the most
  labelled events outside channels 41–46.
* **Evaluated:** only event IDs that touch these channels and **none of
  channels 41–46**, so no event of the exploratory run is reused. By a
  count of labels only, there are 76 such events: 45 Local and 31
  Global.
* **Normal training samples** exclude every labelled interval on these
  channels.
* The script asserts that the channels share timestamps.

## Tests

As in the exploratory run (32 quantisation levels, frozen KT models,
19,999 same-length null windows, seed 0, α = 0.01), with a **stronger
local family of 3 tests per channel:**
* the first-order transition, −log2 P(y_t | y_{t−1});
* the **second-order** transition, −log2 P(y_t | y_{t−1}, y_{t−2}). It
  has as many contexts as the joint test (32²), which answers "the
  joint test just has more parameters";
* the **level frequency**, −log2 P(y_t).

**Verdicts, with Bonferroni correction:**
* **local:** min local p ≤ α/(3C);
* **joint-only:** not local, and min pair p ≤ α/(C(C−1)), with
  C = 12;
* **invisible:** neither.

## Hypotheses

* **K1.** The joint-only share has a 95% Wilson lower bound ≥ 5%.
* **K2.** Joint-only is more common among Local than among Global
  events (one-sided Fisher exact, p < 0.05).

**Also reported:** how many joint-only events have every local p > 0.05,
i.e. are clearly typical channel by channel.

## Meaning

**If K1 and K2 hold:** a confirmed, measurable share of real spacecraft
anomalies is visible only in the relationship between channels.
* It survives a local test as rich as the joint one, on events never
  used before.
* By the zero-rate testing theorem (Han; Shalaby and Papamarcou 1992),
  any design that ships only per-sensor alarms is blind to that share,
  whatever its detectors.

**If K1 or K2 fails,** the exploratory finding is not confirmed, and
that is reported.

The limits stated in the exploratory pre-registration still apply:
* a spacecraft computes the joint on board;
* the model class is first-order and quantised.

## Amendment (before any result; the first launch stopped at the timestamp assertion)

The assertion failed, so no test was computed:
* channels 14, 21, 29, 30 and 38 share a 90 s grid;
* channels 70–76 are sampled every ~30 s, each with its own offset.

All channels are therefore aligned onto channel 14's timestamps. Each
takes its last value at or before each timestamp, so there is no
look-ahead. Nothing else changes.

## Result (run once; `bench/results/data/joint_only_confirm_m1.csv`)

76 fresh events, all testable: local 14, **joint-only 51**, invisible 11.

* **K1 holds:** the joint-only share is 0.671 (95% CI 0.559–0.766).
* **K2 is refuted, again in the opposite direction.** Joint-only covers
  24/45 Local events and **27/31 Global** ones (p = 0.9997).
* Only 12 of the 51 joint-only events have every local p > 0.05.

**Verdict: the finding is not established.** K1 holds as worded. But
its meaning does not, because the pattern shows the joint test measures
something other than the relationship between sensors.

**Why the measurement is confounded.** 87% of the Global events, which
leave the normal range, come out "joint-only" even with three local
tests per channel.
* The joint statistic is a **difference** of two costs on the same
  samples, so its null spread is small.
* When channel x itself is in a rare state, the context (y_{t−1}, x_t)
  is rare too, and the difference jumps.
* So the joint test is simply **more powerful at detecting change**,
  including a marginal change of x. It does not isolate a change in the
  relationship.
* The local tests are absolute costs with a wide null spread, because
  slow drifts make normal windows vary.

The 15–17% of the post-hoc diagnostic, and its J2 pass, are therefore
not evidence of relationship-only anomalies either.

**What a valid test needs.** A statistic that holds both marginals fixed
inside the event window. For example, the joint cost with x aligned,
minus the joint cost with x circularly shifted inside the same window:
the same values of x and y, only their pairing broken. That is a new
pre-registration, not a fix to this one.
