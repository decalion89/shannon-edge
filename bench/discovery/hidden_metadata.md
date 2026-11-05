# Hidden data in the technology itself: timing and commands (exploration, training period only)

**Question.** Mission 1's class_7 anomalies, the recurring class, are
invisible to surprise, to fine-scale activity and to fine-scale
balance. Do they leave a trace in data nobody analyses as signal: the
on-board **timestamps**, or the **telecommand log**?

This is exploration on training labels only (before 2006-10-01). No
test-period claim is made.

## 1. Sampling clock (channel 14)

* Intervals are mostly 90 s, with **bursts of high-rate sampling**:
  358,730 intervals of 3.0 s and 44,045 of 0.4 s. There are also gaps
  of 180–540 s. High-rate samples are **8.3%** of the training
  samples.
* **Timing jitter** (|interval − 90 s|) inside class_7 windows equals
  that of control windows: medians 0 and 0, AUC 0.47, p = 0.53.
* **Share of high-rate samples** inside training events, by class:
  * class_7: 4% (any high-rate sample: 1 of 20 events);
  * class_14: 17%;
  * class_4 and class_6: 60–83%, but only 2 events each;
  * most other classes: 0%.
* High-rate modes do not mark class_7.

## 2. Telecommands (698 command series)

For each command: the share of class_7 training onsets (20) preceded
by that command within 1 hour, against 5,000 random training times.
* **No command precedes more than 1 of the 20 onsets** (maximum 5%).
* class_7 is not triggered by any single ground command within an hour.

## Reading

class_7 leaves no trace in timing metadata or in the command log
either. With the earlier tests, it is now invisible to:
* surprise;
* fine-scale activity;
* fine-scale balance;
* cross-channel coupling;
* sampling-mode changes;
* commands.

**What remains untested:**
* longer-range structure: hours to days, e.g. orbit phase or season;
* channels outside the ones examined.

A recurring anomaly that experts label but no local statistic sees
suggests that its definition is **contextual**: "this pattern at this
point of the orbit or mission phase". That would need the mission's
operational context, which ESA-ADB does not provide.
