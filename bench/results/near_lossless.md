# Error-bounded compression: stop paying for sensor noise

Everything else in this repository is lossless. Lossless coding must
reproduce the sensors' noise bit for bit, and on Venus Express that noise
is most of what remains (`side_information.md`). An **error-bounded**
("near-lossless") mode guarantees instead that every reconstructed value is
within ±δ of the original — the approach of JPEG-LS and of CCSDS 123
near-lossless for images, not yet of CCSDS packet telemetry. This is an
**optional mode**, reported separately; no lossless result changes.

## Method (`bench/analysis/near_lossless.py`)

* Bytes 0–9 (CCSDS header, sequence count, time) stay exact.
* Each numeric field (layout found from history by
  `bench/analysis/fields.py`) is reconstructed by a closed-loop quantiser:
  r_t = r_{t−1} + (2δ+1)·round((v_t − r_{t−1}) / (2δ+1)), so |v_t − r_t| ≤ δ
  for every value; the maximum error is checked for every field.
* δ per field = k × the field's **robust noise σ** (1.4826 · MAD of first
  differences / √2, a white-noise estimate robust to spikes), estimated on
  the first 10% of the packets only.
* The reconstructed packets are compressed **losslessly** by the existing
  codecs, so the bound holds exactly after decoding.

## Venus Express (151,200 packets)

| Mode | v2, 2^18 | vs lossless | vs best CCSDS 124 (5,289,939) | Fast profile |
|---|---:|---:|---:|---:|
| lossless | 2,999,548 | — | −43.3% | 3,845,622 |
| **safe**, error ≤ ¼ σ | 2,470,050 | −17.7% | **−53.3%** | 3,293,886 |
| **safe**, error ≤ ½ σ | 2,274,616 | −24.2% | **−57.0%** | 3,093,072 |
| **safe**, error ≤ 1 σ | 2,061,620 | −31.3% | **−61.0%** | 2,889,848 |
| safe, error ≤ 2 σ | 1,906,966 | −36.4% | −64.0% | 2,735,977 |
| all fields, error ≤ ¼ σ | 2,081,825 | −30.6% | −60.6% | 2,691,894 |
| all fields, error ≤ ½ σ | 1,835,222 | −38.8% | −65.3% | 2,344,525 |
| all fields, error ≤ 1 σ | 1,597,494 | −46.7% | −69.8% | 2,011,264 |

"Safe" keeps exact the three fields at bytes 33–36, 37–40 and 42–44,
whose estimated noise is in the millions of units: they are probably not
plain integers (floating point, or a layout the heuristic got wrong), and
an integer error bound would be meaningless or harmful there.

Fixed δ for all fields, for comparison (v2 2^18): δ = 1: 2,956,048 (−1.5%);
δ = 15: 2,685,644; δ = 255: 2,016,160; δ = 1023: 1,672,052 (−44.3%). A
single δ is not meaningful physically (1,023 units are noise for one
sensor and signal for another); bounds relative to each field's noise are.

## What this is and is not

* The error bound is exact and verified; the decompressed values are
  within ±δ of the originals, never more.
* Whether an error of ¼ σ or 1 σ is acceptable is a decision for the
  mission's engineers, per parameter. A real deployment would take the
  field types, units and tolerances from the mission's telemetry database,
  not from a heuristic layout and a noise estimate.
* Errors are bounded, not random: quantisation error is not independent
  noise, and averaging reconstructed values does not recover the
  originals.
* It is not lossless and does not compete with the lossless results; it
  answers a different question: how much of the remaining cost was noise.

## Checking the field layout (what the heuristic might have missed)

The bound above is guaranteed for the fields as the heuristic layout
defines them. Three alternative readings of the bytes were checked:

* **Two 12-bit values packed in 3 bytes** (typical ADC output): splitting
  every 3-byte field into two 12-bit values makes the first-difference
  entropy *higher* for all ten 3-byte fields (e.g. bytes 18–20: 12.00 bits
  as one 24-bit value, 12.80 as two 12-bit values). Not packed 12-bit.
* **IEEE float32**: the 4-byte fields read as big-endian floats give
  values like −1.2·10³⁰ or denormals; no field is plausible as float32.
* **Signed 32-bit integers aligned at byte 21** (bytes 21–24, 25–28, …
  start with 02/03 or f0/f1/ed, suggesting big-endian signed integers):
  plausible. On that reading the heuristic's 3-byte fields are the low 24
  bits of 32-bit values, and a carry into the high byte could in principle
  break the bound. Measured on the 32-bit reading, the maximum error of
  every field is still exactly the δ chosen (e.g. bytes 21–24: 568 at
  k = 1, for a median change of 580 between packets; bytes 57–60: 11; no
  carry occurred). The alignment itself is ambiguous: the sum of
  first-difference entropies prefers 32-bit fields starting at byte 18
  (161.7 bits) to those starting at 21 (165.2).

So the bound held on every reading tried, but by observation, not by
construction for the 32-bit reading. This is the concrete reason a
deployment must take field boundaries, types and tolerances from the
mission's telemetry database rather than from a heuristic.

## Surprise-adaptive: bounded error for the expected, exact for the surprising

**The question.** Can the downlink spend its precision where the
information is? Predictable values would carry the ±δ error bound; any
value that surprises would be kept exact, so no anomaly loses a bit.
`bench/analysis/surprise_adaptive.py` reuses the "safe" field set and the
closed-loop quantiser above. A value is kept exact when it lies at least
Z = 6 robust σ from the previous reconstructed value. Z was fixed before
any measurement.

The receiver must know which values are exact. That flag stream is
costed at its ideal adaptive entropy (about 108 KB) and added to the size.
Errors are checked for every value: ≤ δ, and exactly 0 on flagged values.

| Bound on predictable values | Uniform error bound (v2 2^18) | **Surprise-adaptive** (v2 2^18 + flags) | Values kept exact | vs lossless (2,999,548) |
|---|---:|---:|---:|---:|
| ≤ ¼ σ | 2,470,050 | 2,613,693 | 16.5% | −12.9% |
| ≤ ½ σ | 2,274,616 | 2,443,975 | 16.5% | −18.5% |
| ≤ 1 σ | 2,061,620 | 2,270,665 | 16.5% | −24.3% |

**Results.**
* With every surprising value kept exact, the adaptive mode still saves
  13–24% against lossless.
* It costs 6–10% more than a uniform error bound.
* The Venus Express fields are heavy-tailed, so "6 robust σ" is not rare
  here: it flags 16.5% of the values.

**Rarity learned on the ground (`--rarity=10`).** Instead of a fixed Z,
each field's threshold is the jump that history (the first 10%) shows at
most once in 2^10 values. On the remaining data that keeps 0.120% of the
values exact:

| Bound on predictable values | Uniform error bound | **Rare values exact** (v2 + ~3.1 KB of flags) | Extra cost | vs lossless |
|---|---:|---:|---:|---:|
| ≤ ¼ σ | 2,470,050 | 2,472,990 | +0.12% | **−17.6%** |
| ≤ ½ σ | 2,274,616 | 2,277,172 | +0.11% | **−24.1%** |
| ≤ 1 σ | 2,061,620 | 2,065,203 | +0.17% | **−31.1%** |

**Keeping every rare jump bit-exact costs about 0.1% of the downlink.**
Error-bounded coding of the expected and exact coding of the rare come
almost for the price of the first alone.

The point of the mode is the guarantee, not the size: everything the
detector would flag reaches the ground exactly, and the rest stays within
a stated fraction of sensor noise.

### Do real anomalies fall on the values kept exact? (ESA-AD, labelled)

The same rule was applied to ESA-AD channels:
* the threshold is the jump seen at most once in 2^10 nominal training
  samples per channel;
* it is applied to the test period.

The question: how many labelled test events have at least one value kept
exact? The scripted check (`bench/analysis/surprise_adaptive.py`'s rule,
inline analysis in the session) gives:

| Mission (channels) | Test values kept exact | Anomalies touched | Rare events touched |
|---|---:|---:|---:|
| Mission 1 lightweight (41–46) | 0.11% | 26/29 | 26/36 |
| Mission 2 lightweight (18–28) | 0.10% | 0/1 | 323/349 |

So **90% of ESA's labelled test events (375/415) contain values that the
rule sends exactly**, while keeping only about 0.1% of all values exact.
"Contains an exact value" is not "is entirely exact": the rest of each
event stays within the error bound.

## How much of a lossless link is the finest scale? ESA-AD Mission 1 (whole mission)

The flight profile's own split (`FlightSession::compress_scored_split`,
`examples/flight_lowbits`) gives the cost of each sample's 2 least
significant code bits, i.e. the 4 finest distinct levels, given the high
bits and the past:

| Channel | Samples | Bits/sample | Of which the 2 low bits | Share | Low-bit cost / 2-bit saturation |
|---:|---:|---:|---:|---:|---:|
| 41 | 15,381,169 | 3.388 | 1.773 | **52.3%** | 0.89 |
| 42 | 15,381,169 | 4.537 | 1.968 | **43.4%** | 0.98 |
| 14 | 5,272,893 | 1.169 | 0.733 | **62.7%** | 0.37 |
| 58 | 14,639,410 | 1.250 | 0.724 | **58.0%** | 0.36 |
| 12 | 14,258,506 | 1.103 | 0.642 | **58.2%** | 0.32 |
| 21 | 5,272,893 | 1.210 | 0.697 | **57.6%** | 0.35 |

* **43–63% of every lossless bit is spent on the four finest levels.**
* On channels 41 and 42 those levels are almost saturated, i.e. close
  to white noise by the saturation law in `tsbad.md`.
* On the others they are a predictable flicker, but still more than
  half the cost.

This is the ESA counterpart of the Venus Express result above: an
error-bounded mode of a few quanta, with rare values kept exact, would
cut roughly half of the link. It has not been run on ESA yet. The test
that matters is the anomaly-preservation check: ESA-ADB detection on
reconstructed data vs original, pre-registered.
