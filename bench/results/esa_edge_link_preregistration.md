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
