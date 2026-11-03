# Anomalies that exist only between sensors: pre-registration

Committed before any number below is computed. The script
(`bench/discovery/joint_only.py`) is committed with it.

## The overlooked theorem

**Zero-rate distributed hypothesis testing.** A sensor may send the
decision centre only a vanishing number of bits: alarms, events, "send
on surprise". The optimal error exponent is then the one Han (one bit)
and Shalaby and Papamarcou (1992, any sublinear number of bits) found.
* It is achieved by checking that each party's observations are
  **marginally typical**.
* No zero-rate scheme can exploit the **joint** statistics of what
  different sensors see.
* Later work: Ueda and Kuzuoka 2015; Bounhar, Sarkiss and Wigger,
  arXiv:2601.07989.

**Why it is easy to miss.** Information theorists know it as a
statement about exponents. Sensor networks and edge AI, which build
precisely such architectures, rarely state what it implies:
* censoring sensors (Rago, Willett and Bar-Shalom 1996);
* event-triggered links;
* per-device alarm thresholds;
* our own per-channel Kraft alarms.

**The implication.** An anomaly that leaves every sensor's own
behaviour typical, and changes only the **relationship** between
sensors, is invisible to every architecture that sends only per-sensor
alarms, whatever the detector on each sensor.

**The question nobody seems to have asked, with real labels:** what
share of real anomalies are of that kind?

**Prior art checked.** We searched for distributed testing with
unknown alternatives, for anytime-valid testing under rate limits, and
for censoring. We found no measurement of this share on labelled
real-world data.
* Multivariate "correlation anomaly" detection exists (e.g. Idé et al.,
  KDD 2009, and many successors). It is a detector design, not this
  measurement.

## Data

ESA-ADB, whole missions:
* **Mission 1 lightweight,** channels 41–46; training before
  2006-10-01.
* **Mission 2 lightweight,** channels 18–28; training before
  2001-07-01.

Channels share timestamps within each mission (checked).

**Events.** Every labelled event ID that touches the chosen channels,
except those of category "Communication Gap" (data gaps, not
behaviour). The event's window runs from the earliest start to the
latest end over the chosen channels.

## Tests (frozen models, empirical null)

**Quantisation.** Per channel, 32 levels between the 0.5% and 99.5%
quantiles of its unlabelled training samples ("normal"), clipped.

**Models.** KT counts fitted on the normal samples, then frozen.
* **Local cost** of channel j: −log2 P(y_t | y_{t−1}). This uses only
  that sensor's own data.
* **Joint excess** of the pair (i → j):
  −log2 P(y_t | y_{t−1}, x_t) − local cost. It rises when the usual
  relationship between i and j breaks.

**Statistic and null.** For each statistic, the event's mean over its
window is compared with the means over 19,999 random windows of the
same length.
* The null windows lie entirely inside normal training samples.
* The generator is seeded with 0.
* p = (1 + #null ≥ observed) / 20,000.

**Verdict per event, α = 0.01 with Bonferroni:**
* **local:** some channel's local p ≤ α/C;
* **joint-only:** not local, but some ordered pair's joint p ≤
  α/(C(C−1));
* **invisible:** neither;
* **untestable:** fewer than 100 possible null windows of the event's
  length.

## Hypotheses

* **J1.** The share of joint-only events has a 95% Wilson lower bound
  ≥ 5%, on Mission 1 and on Mission 2 separately.
* **J2.** Joint-only is more common among events ESA labels "Local"
  (anomalous within the normal range) than among "Global" ones. Both
  missions are pooled; one-sided Fisher exact test, p < 0.05. This is
  the mechanism the theorem predicts: global anomalies leave the
  marginal range, so marginal checks see them.

Every breakdown is reported: by class, by locality, and the invisible
share.

## What a pass would and would not mean

**A pass would mean:** a measurable share of real spacecraft anomalies
exists, within this model class, only between channels. Any architecture
that ships only per-sensor alarms is then blind to them by theorem, not
by a weak detector. That changes how distributed sensing should be
designed: some rate must be spent on the joint.

**It would not mean:**
* **That a spacecraft is blind.** Its channels meet in one on-board
  computer, so the joint can be computed there. The theorem bites where
  sensors are physically apart: sensor networks, IoT, constellations,
  and per-channel pipelines such as our cascade.
* **A complete measurement.** The tests are first-order and quantised.
  A richer local model could reclassify some joint-only events as
  local, so the share is an estimate within this model class.
* **That the theorem's asymptotic i.i.d. setting holds exactly.**

## Result (run once; `bench/results/data/joint_only_esa.csv`)

| | Local | Joint-only | Invisible | Joint-only share (95% CI) |
|---|---:|---:|---:|---:|
| Mission 1 (114 events) | 61 | 33 | 20 | 0.289 (0.214–0.379) |
| Mission 2 (621 testable) | 276 | 318 | 27 | 0.512 (0.473–0.551) |

* **J1 holds.**
* **J2 is refuted, in the opposite direction:** Local 31/79 (0.392) vs
  Global 320/656 (0.488), p = 0.96.

**Reading.** Global anomalies leave the normal range, so a sound
per-channel test should see them. That so many came out "joint-only"
points to a weak local test, not to joint structure. The first-order
transition cost misses a channel parked at a rare level, and the
zero-rate theorem's marginal check includes level frequencies.

### Post-hoc diagnostic (`--marginal`; not a result)

Adds a level-frequency local test per channel
(`bench/results/data/joint_only_esa_marginal.csv`):

| | Local | Joint-only | Invisible | Joint-only share (95% CI) |
|---|---:|---:|---:|---:|
| Mission 1 | 76 | 20 | 18 | 0.175 (0.117–0.256) |
| Mission 2 | 507 | 98 | 16 | 0.158 (0.131–0.189) |

* Local 19/79 (0.241) vs Global 99/656 (0.151), one-sided Fisher
  p = 0.034, now in the predicted direction.
* About a sixth of the events remain visible only between channels.
* Being post hoc, this is confirmed or refuted on fresh events in
  `joint_only_confirm_preregistration.md`.
