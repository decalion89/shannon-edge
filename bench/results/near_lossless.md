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
