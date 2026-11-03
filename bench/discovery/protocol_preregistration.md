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
