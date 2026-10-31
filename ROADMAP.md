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
- [ ] Shared warm-up between blocks (prime each block's model on the end of
      the previous block) to recover most of the block-mode ratio loss
- [ ] Model pruning: measure each model's contribution per data type and skip
      the useless ones
- [ ] Fast "analysis" pass that detects data type and picks a model set
- [ ] Profile-guided optimisation in release builds

## Phase 2 — Strength (closer to the entropy)

- [ ] Bit-history state machines instead of raw counters (better handling of
      deterministic and non-stationary contexts)
- [ ] Indirect and record/column models (tables, spreadsheets, binary
      structures — today `ptt5` and `sum` still lose to xz)
- [ ] Data transforms: x86 call/jump (E8/E9) filter for executables, 2-D image
      models, delta coding for numeric series
- [ ] Higher-precision coder probabilities (removes the ~0.0003 bit/bit floor
      visible on long runs)
- [ ] 2-layer mixer network and learned mixer-context selection
- [ ] Small recurrent / transformer predictor as an extra model input

## Phase 3 — Shared knowledge (moving the edge itself)

- [ ] Pre-trained model "packs" shipped with the decoder (logs, JSON, source
      code, natural language), honestly reporting pack size separately
- [ ] User-trainable dictionaries for many small similar files
- [ ] Measure `H(X | K)` gains per pack on public datasets

## Phase 4 — Production

- [ ] Streaming API and bounded memory for files of any size (> 4 GiB)
- [ ] Library bindings (C ABI, Python)
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
