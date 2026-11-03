# The edge link: exact detection on board, error-bounded values on the link (pre-registration)

Committed before the run.

**Architecture.** The two failed tests show what not to do: re-running
detection on lossy reconstructed data. Here:
* **On board:** the flight profile codes the exact values and its Kraft
  alarm rule runs on them (t = ceil(log2 N), N = samples scored). The
  alarm sample indices go down losslessly, as varint deltas.
* **On the link:** each value is replaced by its index on the lattice
  v₀ + 2δ·k, δ = 1 × the robust noise σ of the training part. That index
  stream is compressed by the same flight profile. The ground
  reconstructs v₀ + 2δ·k, so |error| ≤ δ for every sample.

**Data:** ESA-ADB Mission 2 lightweight (channels 18–28, training before
2001-10-01, validation from 2001-07-01). It has not been used in any
error-bounded test.

**Measured: real bytes,** not cost estimates (`examples/flight_surprise`
reports the frame bytes).
* Lossless: the flight profile on the exact codes.
* Edge link: the flight profile on the lattice indices, plus the alarm
  stream.

**Claims (all required):**
1. Bytes saved ≥ 40%, alarm stream included.
2. Maximum reconstruction error ≤ δ on every sample of every channel,
   checked.
3. The on-board alarms are identical to the lossless system's. This is
   true by construction, and it is checked anyway.

**Not claimed.** That a ground method run on the reconstructed values
matches the same method run on exact values. The two previous tests
refute that for ESA-ADB's detectors.

Script: `bench/esa_edge_link.py`.

## Result (Mission 2 lightweight, run once; per-channel values in `bench/results/data/edge_link_ESA-Mission2.csv`)

| Channels | Lossless (B) | Edge link (B, alarms included) | Saved |
|---|---:|---:|---:|
| All 11 | 83,650,643 | 17,912,630 (alarms: 83 B, 22 alarms) | **78.6%** |
| 18–24 only (excluding 25–28, see below) | 33,993,928 | 12,467,625 | **63.3%** |
| 18–20 only (the channels with σ > 0 at sensor scale) | 26,740,023 | 5,213,704 | **80.5%** |

1. **Claim 1 (≥ 40% saved): holds,** 78.6% overall and 63.3% without
   channels 25–28.
2. **Claim 2 (error ≤ δ everywhere): holds,** checked on every sample
   of every channel.
3. **Claim 3 (on-board alarms identical): holds by construction.** They
   are computed on the exact values: 22 alarms, sent as 83 bytes.

**Caveats, stated before anyone else has to.**
* **Channels 25–28** take values on a scale of about 10⁻¹⁰ with
  floating-point jitter. Their robust σ is about 5·10⁻¹³, so their
  "error bound" is numerical noise. Their 90% saving is real, but it
  comes from not transmitting float jitter, not sensor noise. That is
  why the table also gives the figure without them.
* **Channels 21–24** have σ = 0 (mostly constant), so the edge link
  leaves them unchanged.
* **The lossless baseline merges** channels with more than 65,536
  distinct values (18, 20, 23, 24, 25–28) into 65,536 ordered bins
  before coding, as everywhere else in the ESA benchmarks. A truly
  lossless stream of those channels would be larger, so the savings
  shown are conservative.
* **What is preserved is the on-board detector**, Kraft auto, whose
  ESA-ADB F0.5 on Mission 2 lightweight is 0.200 (`esa_adb.md`). A ground
  method run on the reconstructed values is not covered: that is the
  refuted test above.
