# Bits needed as the shared model accumulates knowledge (ESA-AD Mission 1, 14 years)

`bench/discovery/knowledge_curve.py`; per-year values in
`bench/results/data/knowledge_curve_m1.csv`.

**Question.** If spacecraft and ground share a model that keeps learning,
does the link need fewer bits year after year? How far is it from what a
much stronger model could still save?

The flight profile's cost per sample is measured three ways:
* **A, memory:** one session over the whole 14 years.
* **B, amnesia:** a fresh model every day.
* **C:** the general sedge model, on one mid-mission month.

| Channels | A memory (bits/sample, 2000 → 2013) | B amnesia | A saves vs B | Mid-mission month: A vs C (general model) |
|---|---|---|---:|---|
| 41, 42 | 3.96 → 3.97, flat | 4.17 → 4.18 | **4.6–5.2%**, flat | 3.36 vs 3.29 (41); 4.46 vs 4.40 (42) |
| 14, 58 | 1.19 → 1.26, flat | 1.25 → 1.31 | **4.3–5.1%**, flat | — |

**Result.**
* **Accumulated knowledge beyond one day is worth about 5%, and that
  share does not grow over 14 years.** The shared model learns what
  there is to learn within days. Every later year costs the same.
* **A much stronger model would save only about 2% more** (C vs A on a
  mid-mission month).
* **The floor is about 1.2–4 bits per sample, and it is noise.** It
  matches the earlier finding that these channels' unpredictable bits
  are ADC flicker (`bench/results/esa_adb.md`).

So, for these channels, a single-channel shared model has essentially no
law left to discover. **The "system that speaks less every year" does
not happen here.**

**What is not measured.**
* Structure *across* channels: the compression-gap microscope with pairs
  of channels.
* Other missions or other kinds of signals.

The microscope's next target is therefore cross-channel structure. If
that is also noise, these data hold no hidden law worth bits, and that
is the answer.

## First cross-channel look (`bench/discovery/cross_channel.py`; preliminary)

**Setup.**
* Channels 41, 42 and 43, one mid-mission week (21,056 samples),
  quantised to 32 levels.
* For each pair x → y and lag 0 or 1: the gap between coding y knowing
  its own previous value and knowing also x, against 5 circular shifts
  of x.

**Result.**
* **Every net gain is negative** (−200 to −600 mbit/sample). Knowing
  the other channel never pays for its own learning cost in a week. The
  richer model has 1,024 contexts × 32 symbols, too many to learn from
  21k samples.
* Some pairs beat their 5 shifts by 8–142 mbit/sample. But the shifts
  themselves spread by about ±150 mbit/sample, so these excesses are
  within the null's noise.
* **No exploitable cross-channel law at this resolution and length.**

A conclusive test needs:
* fewer contexts (8 levels for x);
* months, not a week;
* many more shifts (e.g. 100) for a usable null.

Inconclusive, leaning negative.
