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
- [ ] Indirect and record/column models (tables, spreadsheets, binary
      structures — today `ptt5` and `sum` still lose to xz)
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
- [ ] Sessions: bounded history (sliding window) for unbounded streams, and
      an optional shorter checksum for links that already have one
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
