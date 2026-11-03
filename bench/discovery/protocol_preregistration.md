# A noise-scale telemetry protocol against the space standard. Pre-registration

Committed before the run. The script is `bench/discovery/protocol.py`.

## The protocol

Every test in this project hit the same wall: **sensor noise**.
* Two thirds of a lossless stream is noise below 1σ
  (`bit_layers_preregistration.md`).
* Surprise is dominated by it.
* A receiver-side prior cannot use the noise-like bits
  (`receiver_prior_preregistration.md`).

What worked every time was acting **at the source, at the noise scale**
(`bench/results/esa_edge_link_preregistration.md`). The protocol puts
that together:

1. Each channel declares its noise scale σ, estimated once on training
   data. Values are sent on a lattice with |error| ≤ δ = 1σ, guaranteed
   on every sample.
2. The lattice indices are coded by the flight profile.
3. Anomaly alarms are computed **on board, on the exact values**, with
   the Kraft/Ville threshold, and sent losslessly.
4. A channel whose indices do not fit 16 bits, or whose bound fails, is
   sent lossless.

Prior art: near-lossless coding (CCSDS 123.0-B-2, JPEG-LS), on-board
detection, and censoring. The claim is the measured combination against
today's standard, not the parts.

## Comparison (fixed)

**Data.** ESA-ADB whole missions:
* Mission 1, channels 41–46; σ from before 2006-10-01; alarms on the
  test split from 2007-01-01.
* Mission 2, channels 18–28; σ from before 2001-07-01; test from
  2001-10-01.

**Encodings:**
* **B1, today's standard:** CCSDS 121.0-B (libaec, unit-delay
  preprocessor, block 16, 256-sample packets), lossless, on the value
  codes, exactly as in `bench/mission.py`.
* **B2, the standard coder at the noise scale:** CCSDS 121 on the same
  lattice indices, plus the same alarms.
* **Protocol:** the flight profile on the lattice indices, plus the
  alarms.

**Caveat on the value codes.** Values are mapped to their distinct-value
codes, merged into 65,536 ordered bins where there are more. Both the
standard and the protocol see the same codes. `bench/mission.py`
skipped such channels instead.

## Hypotheses

* **P1.** On each mission, the protocol needs **at most half** the
  bytes of today's standard: (protocol + alarms) / B1 ≤ 0.50.
* **P2.** On each mission, the protocol is **≥ 15% smaller** than the
  standard coder on the same noise-scale data:
  (protocol + alarms) / (B2 + alarms) ≤ 0.85.
  This isolates the coder from the quantisation.

Both are reported whatever they show, per channel and per mission.

## Meaning

**If both hold:** sending telemetry at its own noise scale with
certified on-board alarms needs at most half the bytes of today's
standard on two real missions. At least 15 points of that comes from
the coder rather than the quantisation alone.

**It would not mean:**
* that 1σ error is acceptable for every user;
* that ground analyses other than the on-board detector are preserved.
  Ground re-detection on reconstructed data was refuted.

## Amendment (before the verdict)

The first run printed per-channel sizes for Mission 1 only. Channels
42, 44 and 46 showed the CCSDS 121 noise-scale size (B2) **larger than
raw**, which is impossible for a working coder. The cause was our call,
not the standard.
* The lattice indices of those channels fit in 8 bits.
* For bits ≤ 8, libaec reads 1-byte samples, but it was given 2-byte
  samples, so it saw twice as many samples, half of them zeros.

The fix codes 1-byte samples when bits ≤ 8 and 2-byte samples
otherwise.
* It makes the standard **smaller**, so it can only make P2 harder.
* Nothing else changes.
* `bench/mission.py`, whose CCSDS 121 result is published, always passes
  16 bits with 2-byte samples. It is unaffected. That costs CCSDS about
  1% against the best width, for example 146,027 vs 144,247 bytes on
  the first 512k samples of channel 41.

## Result (run once after the amendment; `bench/results/data/protocol_esa.csv`)

| | CCSDS 121 lossless (today) | CCSDS 121 at noise scale + alarms | **Protocol + alarms** | Protocol / today | Protocol / standard coder at noise scale |
|---|---:|---:|---:|---:|---:|
| Mission 1 (6 ch.) | 51,775,835 B | 26,658,545 B | **20,365,530 B** | **0.393** | **0.764** |
| Mission 2 (11 ch.) | 109,994,398 B | 46,182,678 B | **29,165,234 B** | **0.265** | **0.632** |
| Mission 2, channels 18–24 only | 57,912,485 B | 27,065,884 B | 12,467,625 B | 0.215 | 0.461 |

* **P1 holds.** The protocol needs 39% (Mission 1) and 27% (Mission 2)
  of today's standard.
* **P2 holds.** On the same noise-scale data, the protocol is 24% and
  37% smaller than the standard coder.
* The error bound held on every bounded channel. The alarms are
  computed on exact values: 111 B and 83 B in total.

**Caveats:**
* **Mission 2 channels 25–28** take values of order 10⁻¹⁰ with
  floating-point jitter.
  * 26–28 are bounded at σ ≈ 4·10⁻¹³, so their saving is on jitter, not
    sensor noise.
  * 25 does not fit 16-bit indices and goes lossless.
  * The row for channels 18–24 removes them; the protocol is then at
    22% of the standard.
* **Channels 21–24** have σ = 0 and go lossless in every encoding.
* **Lossless comparison.** On these lightweight channels, the flight
  profile alone is 10.8% (Mission 1) and 24.0% (Mission 2) below
  CCSDS 121. Most of the protocol's gain comes from the noise scale;
  the coder adds the P2 margin.
* **1σ is a design choice.** Whether it is acceptable is the user's
  decision, and ground re-detection on reconstructed values is not
  preserved (refuted earlier).
