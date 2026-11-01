# Roadmap

## The mission

> **Compression as smart as AI and as fast as zstd.**

Today you choose: fast compressors (gzip, zstd, LZ4) that barely understand
the data, or context-mixing / neural compressors that understand it far
better but run 100–10,000× slower. Closing that gap would cut storage and
bandwidth for the data the world actually produces — without breaking any law
of information theory (see [`docs/THEORY.md`](docs/THEORY.md)).

Every milestone is measured in public, on standard corpora, with every result
verified bit-for-bit.

## v0.1 — A working baseline ✅

- [x] Bitwise context-mixing model: order 0–4 and 6, word, bigram-word,
      sparse and match models
- [x] Three online neural mixers + a final mixer + three SSE stages
- [x] 32-bit arithmetic coder, integer-only (bit-identical on every CPU)
- [x] `.sedge` container with CRC-32, stored fallback (worst case +20 bytes)
- [x] Cache-line bucketed hash tables (1 cache miss per context per nibble)
- [x] Golden-stream test pinning the format across Linux/macOS/Windows
- [x] Benchmarks vs gzip, bzip2, xz, zstd, brotli

## Phase 1 — Speed (the main frontier)

v0.1 single core: ~0.5 MiB/s. Target: 10× without losing ratio, then more.

- [x] Block mode: independent 8 MiB blocks compressed and decompressed on all
      cores (4.2× on 4 cores for +4% size on enwik8; output independent of
      the thread count)
- [ ] Explicit SIMD mixers (AVX2 / NEON) with runtime dispatch
- [x] Shared-knowledge dictionaries (`-D`): every block is primed with the
      same dictionary, which recovers part of the block-mode loss without
      breaking parallel decoding. (Priming each block on the end of the
      *previous* block, the original idea here, would make block N wait for
      block N−1 to decode — no longer parallel.)
- [ ] Model pruning: measure each model's contribution per data type and skip
      the useless ones
- [ ] Fast "analysis" pass that detects data type and picks a model set
- [ ] Profile-guided optimisation in release builds

## Phase 2 — Strength (closer to the entropy)

- [ ] Bit-history state machines instead of raw counters (better handling of
      deterministic and non-stationary contexts)
- [x] Record/column model with auto-detected record length (spreadsheets,
      fax scanlines, telemetry packets): `ptt5` now beats xz by 20%
- [ ] Indirect models, and a model for executables (`sum` still loses to xz)
- [ ] Data transforms: x86 call/jump (E8/E9) filter for executables, 2-D image
      models, delta coding for numeric series
- [ ] Higher-precision coder probabilities (removes the ~0.0003 bit/bit floor
      visible on long runs)
- [ ] 2-layer mixer network and learned mixer-context selection
- [ ] Small recurrent / transformer predictor as an extra model input

## Phase 3 — Shared knowledge (moving the edge itself)

- [x] Dictionary priming in the format and CLI (`-D`), with CRC-checked
      dictionary identity
- [x] Model-state snapshots (`sedge prime`, `-M`, `PrimedModel`): load the
      primed model instead of re-reading the dictionary (17× faster for a
      3 KB message with a 4 MiB dictionary)
- [ ] Smaller model files: sparse/compressed snapshot encoding, and
      memory-mapped loading
- [ ] Pre-trained model "packs" shipped with the decoder (logs, JSON, source
      code, natural language), honestly reporting pack size separately
- [x] `sedge train`: our own dictionary trainer (document-frequency segment
      selection, best content last). On 1,000 GitHub events at a 110 KiB
      budget: 19% smaller than zstd with its own trained dictionary; trains
      in 2 s vs 113 s
- [ ] Model-aware training: choose dictionary content by how much it
      lowers sedge's actual coding cost on held-out samples
- [x] Fast start for small messages: journaled in-place coding
      (`PrimedModel::compress_message`), each slot logged at most once per
      record, buffers reused: 1,000 records in 16 s (was 63 s with 110 KiB
      knowledge, 130 s with 18 MB); using knowledge now costs about the same
      as not using it. The model is restored bit-for-bit (tested)
- [ ] Below ~8 ms per record per direction: needs a faster model. Ablation
      on Canterbury + 4 MB of enwik8: two of the three SSE stages are free
      to drop (≤ +0.05%, ~10% faster); the rest each cost 0.2–3.7% if
      removed, so the next 10× needs a different architecture, not pruning
- [x] Sessions that keep learning (`Session`): compact ≈8-byte frames,
      sequence numbers, rollback of corrupt records. On 1,000 consecutive
      GitHub events: 27% smaller than zstd's streaming mode with context
      takeover, 29% with a trained starting dictionary
- [x] Sessions: bounded history (sliding window, default 32 MiB) for
      unbounded streams; even a 64 KiB window stays 20% below zstd
      streaming with its 8 MiB window
- [x] Lean session frames (no sequence number/CRC) for links that already
      protect integrity and order, e.g. CCSDS space links
- [x] Spacecraft telemetry benchmark (ESA-AD, 6 channels, 6 M samples):
      43% smaller than CCSDS 121 in total; ties on smooth channels, −41% to
      −50% on noisy ones
- [x] Onboard-class research prototype (`examples/telemetry_lite.rs`): a
      residual model and an order-1 model, switched per sample by recent
      cost with no side information: −33% vs CCSDS 121 at 2–3 M samples/s,
      −40% with order-2 mixing at ~1 M samples/s
- [x] Integer-only flight profile in the library (`flight::FlightSession`,
      C `sedge_flight_*`, Python `FlightSession`): −40% vs CCSDS 121 with
      ~3 MiB of tables, −39% with ~0.2 MiB, 2–4 M samples/s on a desktop
      core; golden-pinned format
- [x] Anomaly detection for free: per-sample surprise from the flight codec
      (identical on both ends). ESA Mission 1, all 58 target channels,
      3,520 labelled events: 2,173 found at 0.1% false alarms vs 1,696
      (z-score) and 1,322 (jump); 1,527 vs 903 vs 785 at 0.01%; best on
      54/58 channels
- [x] Compare with CCSDS 124.0-B-1 (POCKET+): on the real Venus Express
      packets of its test vectors, a lean session with the record model is
      45.6% smaller than the ESA reference output (packet by packet)
- [x] Record model (column contexts, auto-detected record length, method 4):
      kennedy.xls −47%, ptt5 −29%, Venus Express whole file −34%
- [ ] Record model in the flight profile (column contexts for packets of
      several fields), and a robustness mode that survives lost packets
- [x] Whole-mission measurement (ESA-AD Mission 1, 75 channels, 734 M
      samples, 14 years): flight profile beats CCSDS 121 on 75/75 channels,
      −38% in total; 16 channels below 1% of float32
- [ ] Missions 2 and 3, and a public "where 1% is possible" scoreboard of
      real-world data streams
- [ ] Anomaly scoring with a label-free threshold, ESA-ADB's own metrics,
      and comparison with its learned detectors
- [ ] Time the flight profile on flight-class hardware (LEON3/4, RISC-V)
      or an instruction-accurate emulator
- [ ] Write it up: reproducible note/paper for the space data systems
      community (CCSDS, SpaceOps, DCC)
- [ ] Measure `H(X | K)` gains per pack on public datasets

## Phase 4 — Production

- [ ] Streaming API and bounded memory for files of any size (> 4 GiB)
- [x] Library bindings: C ABI (`include/shannon_edge.h`) and a
      dependency-free Python binding, tested on Linux, macOS and Windows
- [ ] Python wheels on PyPI (`pip install shannon-edge`)
- [ ] Fuzzing (cargo-fuzz) of the decoder
- [ ] Published releases and binaries

## Public scoreboard targets

- enwik8 / enwik9 (Wikipedia; the Hutter Prize data)
- Silesia corpus
- Canterbury corpus

## Explicit non-goals

- Compressing random, encrypted or already-compressed data (JPEG, H.265, ZIP).
  No method can; we guarantee at most +20 bytes instead.
- "1% of any file". Excluded by counting — see `docs/THEORY.md`, Section 2.
