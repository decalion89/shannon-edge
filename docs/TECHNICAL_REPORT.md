# Learning compression for spacecraft housekeeping telemetry

**Smaller, faster and loss-tolerant compared with CCSDS 124, measured on
real telemetry.**

Technical report, shannon-edge (`sedge`). Every figure below is
reproducible from this repository; every compressed packet is decompressed
and verified byte for byte, and every comparison codec is run on the same
data. Detailed write-ups are linked per section (`bench/results/`).

## Abstract

CCSDS 124.0-B-1 (POCKET+) is the CCSDS standard for compressing
fixed-length housekeeping packets on board. On the real Venus Express
housekeeping packets of its public test vectors (151,200 packets of 90
bytes), against the best configuration of a parameter sweep of an open
implementation verified byte-identical to the ESA reference:

* **Size, lossless:** sedge's packet profiles produce 27.3% (fast
  profile, 193 KiB of model memory) to 43.3% (profile v2, 6 MiB) fewer
  bytes.
* **Speed:** the fast profile executes 3.0x fewer instructions per byte
  than the open CCSDS 124 implementation on RISC-V (191 vs 590,
  cross-compiled and counted exactly under QEMU), and runs ~1.9x faster on
  a desktop core.
* **Loss tolerance:** with payloads packed into 223-byte transfer frames
  and Reed–Solomon parity over frames, sedge recovers 100% of the packets
  at 0.1%, 1% and 5% frame loss with 42–47% fewer bytes. CCSDS 124 under
  the same frame loss needs its maximum robustness (R = 7) and recovers
  98.75% at 1% and 51.9% at 5%. Given the same frame protection, CCSDS 124
  is 39.3% larger at every loss rate.
* **Optional error-bounded mode:** a reconstruction error bounded per
  field by a fraction of the sensor's own noise (¼ σ to 1 σ) gives 53–61%
  fewer bytes than CCSDS 124.

On 14 years of ESA Anomaly Dataset telemetry (Mission 1, 734 million
samples), the flight profile is 38% smaller than CCSDS 121 in total and
smaller on all 75 channels measured. Its per-sample "surprise", computed
identically on both ends at no extra cost, is also an anomaly detector: on
ESA's own benchmark (ESA-ADB, corrected event-wise F0.5, test sets
matching the paper's event counts) it beats every algorithm in ESA-ADB's
Table 2 on the full channel sets of both missions (later methods, with
monthly retraining or supervision and other protocols, score higher; see
`bench/results/esa_adb.md`) — 0.279 vs 0.061 (Mission 1) and
0.798 vs 0.079 (Mission 2) — while ranking 2nd and 3rd on the small
lightweight subsets. The report also lists the ideas that did not work,
with their measurements.

## 1. Codecs

All codecs are integer-only and deterministic: the same bytes on every
platform (pinned by golden-stream tests on Linux, macOS and Windows; the
RISC-V build produces the same bytes as x86). They predict each bit or
symbol and code it with an arithmetic coder, so the cost of a datum is the
surprise it carries under the model.

* **Packet profile v1** (`packet::PacketSession`): each byte position is a
  column, predicted from the byte above (previous packet), two packets
  back and its left neighbour by a transition model and a residual model,
  chosen per column by recent cost.
* **Packet profile v2** (`PacketSession::v2`): first a byte-level
  decision "same as the byte above?" in contexts the bit models do not see
  (left neighbour changed, column run length, bytes changed so far); the
  bit models are compared on one packet in 16; SSE stages
  (`bench/results/packet_v2.md`).
* **Fast profile** (`packet_fast::FastPacketSession`): one cheap decision
  per byte and one adaptive symbol (the delta from the byte above) per
  changed byte, with per-column Fenwick frequency tables. The ground,
  which holds the history, chooses per-column context recipes and coding
  classes (static / normal / always-changing) and uplinks one byte per
  column each: the ground does the thinking, the spacecraft executes
  (`bench/results/packet_fast.md`).
* **Flight profile** (`flight::FlightSession`): integer sample streams
  (one channel), residual and transition models switched per sample.
* **Erasure code** (`fec`): systematic Cauchy Reed–Solomon over GF(2^8)
  across packets or transfer frames.

## 2. Methodology

* **Data.** Venus Express housekeeping packets from the CCSDS 124 test
  vectors; ESA Anomaly Dataset Missions 1–3 (CC BY 3.0 IGO,
  doi:10.5281/zenodo.12528696).
* **Reference codec.** CCSDS 124: the open C implementation
  tanagraspace/ccsds124 (MIT), whose output was checked byte-identical
  (size and MD5) to the ESA reference output; its parameters (R, pt, ft,
  rt) were swept and its best configuration used for each comparison.
  CCSDS 121: libaec.
* **Verification.** Every compressed packet is decompressed and compared
  with the original; CCSDS 124 outputs under loss are compared with the
  original data, not trusted.
* **Held-out evaluation.** Anything learned from data (recipes, classes,
  noise estimates, field layouts) is learned on the first 10% of the
  packets and measured on the other 90%.
* **Speed.** Wall-clock time measured in-process for both codecs
  (compression only). Because wall clock on a shared machine varies, work
  is also counted in executed instructions: callgrind on x86, and exact
  guest-instruction counts from QEMU's execution log for RISC-V builds
  (`bench/analysis/qemu_count.awk`).

## 3. Results

### 3.1 Lossless size, Venus Express

| Codec | Model memory | Bytes | vs best CCSDS 124 |
|---|---:|---:|---:|
| CCSDS 124, best of sweep (R=0, pt=14, ft=10⁵, rt=10⁶) | < 1 KiB | 5,289,939 | — |
| CCSDS 124, test-vector settings (R=2) | < 1 KiB | 5,891,500 | +11.4% |
| zstd -19, streaming, flushed per packet | ~8 MiB | 8,236,002 | +55.7% |
| sedge fast profile | 193 KiB | 3,846,435 | −27.3% |
| sedge packet profile v1, 2^14 | 321 KiB | 3,650,124 | −31.0% |
| sedge packet profile v2, 2^12 | 372 KiB | 3,350,925 | −36.7% |
| sedge general model, lean session + record model | ~70 MiB | 3,202,177 | −39.5% |
| sedge packet profile v2, 2^18 | 6.0 MiB | 2,999,548 | −43.3% |

On the held-out 90%, the fast profile with ground-learned recipes takes
3,237,712 bytes, −32.2% vs CCSDS 124 R=0 on the same packets (4,772,219).
The other CCSDS 124 test inputs (synthetic, not used for tuning) improve
as well (`packet_v2.md`, `packet_fast.md`).

### 3.2 Speed (compression)

| Measure | CCSDS 124 (open implementation) | sedge fast profile |
|---|---:|---:|
| Instructions per byte, RISC-V (QEMU, exact) | 590 | **191** (3.1x fewer) |
| Instructions per byte, x86 (callgrind) | 1,288 | 153–184 (7–8x fewer) |
| Wall clock, one desktop core | ~26 MB/s | ~50 MB/s |

Ground-chosen coding classes cut a further 11–17% of instructions at
≤ 0.4% size cost. Instruction counts are not cycles; nothing has been
timed on flight hardware.

### 3.3 Loss of transfer frames (`bench/results/frame_loss.md`)

Payloads packed into 223-byte frames (1-byte length per payload, 2-byte
first-header pointer per frame; every byte counted), Reed–Solomon parity
frames over groups of G frames, frames lost i.i.d. CCSDS 124 framed the
same way and decoded by its own decoder on the surviving packets.

| Frame loss | CCSDS 124 (own robustness) | sedge v2 + RS over frames | Difference |
|---:|---|---|---:|
| 0.1% | R=7: 5,673,343 B, 99.89% correct | 3,037,086 B, 100% | −46.5% |
| 1% | R=7: 5,673,343 B, 98.75% | 3,109,086 B, 100% | −45.2% |
| 5% | R=7, ft=rt=100: 5,807,812 B, 51.90% | 3,343,086 B, 100% | −42.4% |

With the same frame-level Reed–Solomon protection for both codecs, CCSDS
124 (R=0) is 39.3% larger at every loss rate: under equal protection only
compression differs. The protection overhead is +1.0%, +3.4% and +11.2%
(theoretical minimum with unlimited delay: 0.1%, 1.0%, 5.3%).

### 3.4 Loss of individual packets (`robustness_cost.md`, `venus_fec.md`)

With i.i.d. packet loss (CCSDS 124's decoder told about every gap), sedge
v2 plus packet-level Reed–Solomon recovers 100% of the packets: −42.0%,
−41.0% and −32.3% vs the best CCSDS 124 configuration at 0.1%, 1% and 5%
loss (R=1, 2, 3, which recover 99.89%, 99.02% and 95.04%). The protection
overhead was decomposed into a finite-block margin (the finite-blocklength
law of Polyanskiy, Poor and Verdú) and the padding of parity packets to
the longest payload of a group; larger groups reduced it from 14.9% to
6.3% at 1% loss. Frames (3.3) remove the padding entirely.

### 3.5 A whole mission, CCSDS 121 (`bench/results/esa_mission1.md`)

ESA-AD Mission 1, every channel (75 measured, one skipped with more than
65,536 distinct values), 734 million samples over 14 years, 256-sample
packets: the flight profile is 38% smaller than CCSDS 121 (libaec) in
total and smaller on 75 of 75 channels.

### 3.6 Anomaly detection as a by-product, on ESA's benchmark (`esa_adb.md`)

The flight profile's per-sample cost is computed identically by sender and
receiver, so a compressor on board gets an anomaly score for free. Scored
on ESA-ADB (Kotowski et al.) with its Mission 1 protocol (train before
2007, test after, validation = last 3 months of training) and its main
metric (corrected event-wise F0.5, logic of ESA-ADB's own code), with a
per-channel threshold = the maximum cost seen in nominal training data
(rule chosen on validation):

| Setting | sedge surprise | Best published | Next best published |
|---|---:|---:|---:|
| Mission 1, lightweight subset (channels 41–46) | 0.690 (precision 1.000, no false alarm in 7 test years) | 0.786 (Telemanom-ESA-Pruned) | 0.253 (GlobalSTD5) |
| Mission 1, lightweight, anomalies only | 0.905 | 0.968 (Telemanom-ESA-Pruned) | 0.211 |
| **Mission 1, full set (58 target channels)** | **0.279** | 0.061 (Telemanom-ESA-Pruned) | 0.008 (Telemanom-ESA) |
| Mission 2, lightweight subset (channels 18–28) | 0.725 | 0.949 (Windowed iForest) | 0.842 (Telemanom-ESA-Pruned) |
| **Mission 2, full set (47 target channels)** | **0.798** | 0.079 (PCC) | 0.071 (Telemanom-ESA-Pruned) |

No neural network is trained; the surprise detects anomalies (19 of 29 in
the lightweight test set) and is nearly blind to "rare events" (1 of 36),
which are infrequent but known operations. Caveats: the lightweight rule
choice ties on only 3 validation events (the other tied rule scores 0.373).
With ESA-ADB's exact preprocessing (30-s grid) the full-set scores hold —
0.292 (Mission 1) and 0.815 (Mission 2) — but the Mission 1 lightweight
subset collapses to 0.103: the grid drops samples irregularly in Mission 1,
and each drop looks like an anomaly to the model. Earlier simple controls (`esa_mission1_anomaly.md`): at
0.1% false alarms it flags 2,173 of 3,520 events against 1,696 for a
rolling z-score.

All of ESA-ADB's metrics, computed with ESA-ADB's own code (`--official`;
it reproduces our event-wise F0.5 exactly on three settings, 0.284 against
0.279 on the fourth). On both full sets the surprise ranks first under
the benchmark's hierarchy. On Mission 1 full it is also first on alarming
precision (0.388 vs 0.206), ADTQC timing (0.894 vs 0.752) and
affiliation F0.5 (0.636 vs 0.607); Mission 1 lightweight timing is best
too (0.949 vs 0.901). It is last on channel-aware F0.5 in every setting
(0.18–0.22 vs 0.48–0.84): it detects the event but names too few of the
affected channels (channel recall 7–10%).

**Training-free thresholds** (`docs/KRAFT_DETECTION.md`). Through the
Kraft inequality, a sample costing ≥ b + t bits under a calibrated code
(alphabet 2^b) has probability ≤ 2^−t. This holds for any lossless code,
with no independence assumption, and degrades by 2^D for a model off by a
max-divergence D. The flight model obeys the bound on 45.8 M nominal
samples.

With t fixed by a formula before scoring (at most one expected false
alarm in the test set) and no training, the corrected event-wise F0.5 is:

* Mission 1 lightweight: 0.705 (trained 0.690).
* Mission 1 full: 0.576 (trained 0.279; best published 0.061).
* Mission 2 lightweight: 0.200 (trained 0.725).

The bound fixes false alarms, not misses: how much risk a mission accepts
remains a choice.

### 3.7 Optional error-bounded mode (`bench/results/near_lossless.md`)

Header and time exact; every numeric field reconstructed within ±δ by a
closed-loop quantiser (as in JPEG-LS and CCSDS 123 near-lossless), δ a
fraction of the field's robust noise σ estimated on history; the result is
then compressed losslessly, so the bound holds exactly (verified for every
value). Three fields with implausibly large noise, probably not integers,
are kept exact.

| Error bound per field | v2, 2^18 | vs best CCSDS 124 |
|---|---:|---:|
| lossless | 2,999,548 | −43.3% |
| ≤ ¼ σ | 2,470,050 | −53.3% |
| ≤ ½ σ | 2,274,616 | −57.0% |
| ≤ 1 σ | 2,061,620 | −61.0% |

Acceptable error is a mission decision per parameter; a deployment would
take field types and tolerances from the mission's telemetry database.

### 3.8 Distance to the strongest known compressor, and numeric prediction (`packet_fast.md`, `packet_v2.md`)

paq8px -8 on the whole Venus Express file is extrapolated at ≈2.39 MB
(it stopped at 96.2%). sedge CM on the whole file gives 2,849,785 (+19%),
so the remainder is *not* all noise.

Column by column, the gap concentrates in about ten columns. An ablation
of paq8px's models, each muted in turn, then keeping one model only,
shows that **numeric prediction** is the piece sedge lacked: paq8px with
only its linear-prediction model reaches 12,953 bytes on column 59,
against 27,980 for sedge CM.

`PacketSession::v2_lp` (opt-in) adds it to v2, integer-only:
* 14 predictors per column, including 16-bit byte-pair predictors that
  paq8px does not have;
* residual histograms, selected by each predictor's recent error;
* per-column mixer weights.

| Dataset | v2 | v2_lp |
|---|---:|---:|
| Venus Express, 2^18 | 2,999,548 | **2,874,663 (−4.16%; −45.7% vs CCSDS 124)** |
| ECG / power / AIS / MetroPT | | −4.41% / −1.75% / −5.62% / −5.98% |

It closes about 21% of the paq8px gap, at about 3x the time.

The fast profile's own losses were measured too. It codes within 1.3% of
its model, and that 1.3% is the per-packet flush. Model v2 of the fast
profile adds:
* two-speed flags;
* ground-learned windows per column;
* checked slope-following columns.
Together they cut Venus Express by 2.3% with learned layouts, at the same
speed class. All of it is ported to C, bit-exact.

### 3.9 Training-free anomaly detection with a provable false-alarm bound (`docs/KRAFT_DETECTION.md`, `esa_adb.md`)

For any sequential lossless code with a 2^b alphabet, P(cost ≥ b + t) ≤
2^(D−t), where D is the max-divergence of the truth from the code (Kraft).
With t fixed by a formula (t = log2 N, at most one expected false alarm)
and no training, ESA-ADB's own metric code gives:

| Setting | Corrected event-wise F0.5 | Best published |
|---|---:|---:|
| Mission 1, full set | **0.576** | 0.061 |
| Mission 2, full set | **0.249** | 0.079 |
| Mission 1, lightweight | 0.705; cumulative rule 0.766 | 0.786 |
| Mission 2, lightweight | 0.200 | 0.949 |

Limits found:
* the strict guarantee is too strict on dense, frequent events;
* the cumulative rule needs a calibrated model;
* channel attribution stays weak, even with a Kraft attribution step
  (0.205 → 0.289 / 0.363);
* the surprise does not predict anomalies days ahead.

The flight profile and the detector are in C99, bit-exact with Rust on
157 M ESA samples.

### 3.10 Ground-learned field relations (`general_data.md`, `fields`)

On 12-lead ECG the ground finds, with no ECG knowledge, the derived leads
(Einthoven/Goldberger) as exact integer relations. With per-field deltas,
packet v2 goes from 2.77x to 3.82x. `fields::RecordTransform` is a 60-byte
uplink, also in C99 and fuzzed.

### 3.11 What anomalies look like to a compressor (`esa_adb.md`, `ecg_kraft.md`, `kepler.md`, `ucr_anomaly.md`)

* **Information.** Across ESA, UCR, MIT-BIH and Kepler, labelled
  anomalies carry about as much information per sample as normal
  operation (1.0–1.2x). What sets them apart is that it is concentrated
  near their onset: a spike at lag 0 of 6–22x the pre-onset level.
* **Consequences, measured:**
  * Keeping rare values exact in the error-bounded mode costs about 0.1%,
    and 90% of ESA's labelled events contain such values.
  * Downlinking the largest compressed packets first brings about 2x the
    anomalies to the ground under tight budgets.
* **Rarity limit.** A detector with false-alarm rate α can only flag
  events about as rare as α. Frequent clinical abnormalities (ventricular
  beats are 15–34% of some records) are not rare. With a beat-shape code,
  85% of ventricular beats are flagged on held-out MIT-BIH records at a
  loose bound.
* **Not universal.** On the UCR archive the surprise scores 0.27–0.35,
  against 0.54 for the matrix profile. A per-file choice based on each
  detector's training margin reaches 0.564; that rule was designed after
  seeing the first one fail.
* **Planets.** In Kepler data a compression-based search finds Kepler-10b
  and 10c with no astronomy in the code. With cotrending, split-half
  evidence and depth-consistency vetting it rejects 62 of 62 quiet stars,
  but recovers only 11 of 40 injected 150-ppm planets. No discovery is
  claimed.

## 4. What did not work (measured)

| Idea | Result | Write-up |
|---|---|---|
| Epochs / key packets inside the compressor for loss tolerance | only −4.8% vs CCSDS 124 R=1; separation (erasure code) is far better | `venus_robustness.md` |
| Slepian–Wolf: XOR-only encoder, model on the ground | ideal −28%; real code −13.8% only with per-packet feedback; worse than CCSDS 124 without feedback, even with a ground-uplinked rate table | `slepian_wolf.md` |
| Mixing the two bit models instead of choosing per column | +4% and +23% | `packet_v2.md` |
| Cross-channel dependency contexts (best predictor column) | −0.7% overall | `packet_fast.md` |
| Numeric-field deltas as a transform (Venus, heuristic byte layout) | worse (+0.5% fast, +10% v2); with a declared field layout (`fields`) they help v2 by 3–6% on other data, and numeric prediction inside v2 helps everywhere (3.8) | `packet_fast.md`, `general_data.md` |
| Coding the packet change mask as flips; batch-learned tables | +5%; no faster and +0.3% | `packet_fast.md` |
| Telecommand timeline as shared side information | no excess surprise after commands | `side_information.md` |
| Fleet knowledge (models learned elsewhere) | bounded by the learning cost: 0.02% on long missions | `side_information.md` |
| Hidden structure in the remaining "noise" | none found: heavy-tailed spikes | `side_information.md` |

An earlier version concluded that, once history is modelled well, what
remains is sensor noise. That is **corrected** by the paq8px comparison
(3.8): about 19% of headroom remains at the whole-file level, and numeric
prediction recovers part of it. What is noise is the per-sample remainder
*after* a strong model. Further measured dead ends:
* the 24-h orbit as a context (−1.9% worse);
* habituation, relation-break detection and early warning in the anomaly
  work;
* every "unlabelled anomaly" candidate examined, each explained by a
  near-miss label, a selection effect or the base rate.

## 5. Limitations and threats to validity

* Packet-level results come from one mission (Venus Express); the other
  CCSDS 124 test inputs are synthetic. Replication on other missions'
  packet streams is needed.
* The CCSDS 124 code measured is an open reference implementation, not
  necessarily the fastest flight code. Instruction counts are not cycles;
  no measurement on flight hardware (LEON, NOEL-V) yet. The fast profile's
  coder uses one 32-bit division per symbol (no 64-bit arithmetic), which
  32-bit flight CPUs do in hardware.
* Model memory: 0.2–6 MiB against a few hundred bytes for CCSDS 124.
* Loss models are i.i.d. (packets or frames); burst losses longer than a
  group's parity require interleaving, not evaluated. Erasure-code
  recovery adds latency after a loss (up to a group of frames).
* Field layouts and noise levels for the error-bounded mode are estimated
  heuristically from the data, not taken from a telemetry database.

## 6. Reproducing

| Figure | Command (after `cargo build --release --examples`) |
|---|---|
| 3.1 | `python3 bench/ccsds124.py ccsds124/test-vectors --cli <ccsds124 CLI>`; `SEDGE_PACKET_V2=1 target/release/examples/packet_bench venus-express.ccsds 90 18`; `target/release/examples/packet_fast_bench venus-express.ccsds 90` |
| 3.1 held-out, 3.2 classes | `SEDGE_FAST_RECIPES=1 target/release/examples/packet_fast_bench venus-express.ccsds 90` |
| 3.2 | `examples/packet_fast_count.rs`, `bench/c/ccsds124_count.c` under `qemu-riscv64 -d in_asm,exec,nochain` with `bench/analysis/qemu_count.awk` |
| 3.3 | `target/release/examples/frame_fec venus-express.ccsds 90 223`; CCSDS 124: `frame_fec --sizes` and `bench/c/ccsds124_loss.c` with a mask file |
| 3.4 | `SEDGE_PACKET_V2=1 target/release/examples/packet_fec venus-express.ccsds 90 16 <ccsds sizes>`; `bench/analysis/overhead.py` |
| 3.5, 3.6 | `python3 bench/mission.py ESA-Mission1.zip`; `python3 bench/anomaly.py ESA-Mission1.zip` |
| 3.7 | `python3 bench/analysis/near_lossless.py venus-express.ccsds OUT_ --safe 0.25 0.5 1`, then the codecs on the outputs |

## 7. Next steps

1. Replicate on other missions' housekeeping packet streams.
1. Speed up v2_lp, with ground-learned predictor subsets, and port it to
   C.
1. Detector combination with a guarantee (UCR: the oracle reaches 0.64).
2. Time the fast profile on flight-class hardware (NOEL-V/LEON).
3. Burst-loss evaluation with interleaved erasure-code groups.
4. Error-bounded mode inside the codecs, driven by a telemetry database.
5. C and Python bindings for the packet profiles.

## References

* CCSDS 124.0-B-1, Robust Compression of Fixed-Length Housekeeping Data
  (POCKET+); tanagraspace/ccsds124 (open implementation, MIT).
* CCSDS 121.0-B, Lossless Data Compression; libaec.
* Kotowski et al., European Space Agency Benchmark for Anomaly Detection
  in Satellite Telemetry, arXiv:2406.17826; ESA-AD, doi:10.5281/zenodo.12528696.
* Y. Polyanskiy, H. V. Poor, S. Verdú, Channel Coding Rate in the Finite
  Blocklength Regime, IEEE Trans. Inf. Theory 56(5), 2010.
* D. Slepian, J. K. Wolf, Noiseless Coding of Correlated Information
  Sources, IEEE Trans. Inf. Theory 19(4), 1973.
* C. E. Shannon, A Mathematical Theory of Communication, Bell System
  Technical Journal 27, 1948.
