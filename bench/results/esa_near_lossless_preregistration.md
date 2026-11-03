# Half the link, every anomaly kept? Error-bounded telemetry on ESA-ADB (pre-registration)

Committed before any error-bounded run on ESA data.

**Why.** On ESA Mission 1, 43–63% of lossless bits go to the four finest
levels of each value (`near_lossless.md`), largely sensor noise.
Agencies send everything losslessly so that no fault signature is lost.
This tests whether an error-bounded link keeps the anomaly detection
intact while sending far fewer bits.

**Data and protocol.** ESA-ADB Mission 1 lightweight (channels 41–46),
the ESA-ADB split, scored with ESA-ADB's own metric code (`--official`),
as in `esa_adb.md`.

**Reconstruction.** For each channel, a closed-loop quantiser on the
values (as in `bench/analysis/near_lossless.py`):
* r_t = r_{t−1} + 2δ·round((v_t − r_{t−1})/(2δ)), so |v_t − r_t| ≤ δ
  holds for every sample (real-valued channels, hence 2δ rather than
  the integer 2δ+1);
* δ = K × robust noise σ, where σ = 1.4826·MAD(first differences)/√2 is
  estimated on the training part only (before the validation start).

The detector then runs on the reconstructed values (`--near-lossless K`).

**Budgets.**
* **Primary: K = 1**, the "safe ≤ 1 σ" level of the Venus Express study.
* Reported as well: K = 0.5.

**Measures.**
* **Bits:** the flight profile's total cost over all samples of the six
  channels, reconstructed vs lossless.
* **Detection:** the corrected event-wise F0.5 (official) for two
  rules, on reconstructed vs lossless data:
  * the trained rule (q = 1.0, chosen on validation);
  * the training-free Kraft auto rule.

**Success, all required at K = 1:**
* bits saved ≥ 40%;
* |ΔF0.5| ≤ 0.01 for both rules.

Anything else is reported as it is.
