# shannon-edge

**Lossless compression by prediction — pushing toward the Shannon limit.**

`sedge` is a context-mixing compressor written in Rust with zero dependencies.
It does not look for repeated strings the way gzip, zstd or xz do. Instead,
before every single bit it **predicts** what comes next, using a set of models
blended by small online neural networks, and an arithmetic coder stores only
the *surprise*. Better prediction means fewer bits, all the way down to the
entropy of the data.

> **Mission:** compression as smart as AI and as fast as zstd.
> v0.1 delivers the "smart" half. Speed is the next frontier — see the
> [roadmap](ROADMAP.md).

## Results

Every `sedge` number below was decompressed and verified bit-for-bit.
Competitors run at their strongest standard settings. Smaller is better;
the best result in each row is in bold.

### Canterbury corpus (the classic benchmark)

| File | Original | gzip -9 | bzip2 -9 | xz -9e | zstd -19 | brotli -11 | **sedge** |
|---|---:|---:|---:|---:|---:|---:|---:|
| alice29.txt | 152,089 | 54,170 | 43,202 | 48,528 | 49,211 | 46,487 | **37,704** |
| asyoulik.txt | 125,179 | 48,778 | 39,569 | 44,592 | 45,137 | 42,712 | **35,111** |
| cp.html | 24,603 | 7,940 | 7,624 | 7,652 | 7,713 | 6,894 | **6,485** |
| fields.c | 11,150 | 3,115 | 3,039 | 3,032 | 3,015 | 2,717 | **2,461** |
| grammar.lsp | 3,721 | 1,222 | 1,283 | 1,292 | 1,211 | 1,124 | **1,019** |
| kennedy.xls | 1,029,744 | 207,029 | 130,280 | 51,868 | 64,825 | 61,498 | **41,244** |
| lcet10.txt | 426,754 | 144,439 | 107,706 | 119,488 | 121,336 | 113,416 | **91,658** |
| plrabn12.txt | 481,861 | 194,332 | 145,577 | 165,456 | 167,438 | 163,267 | **129,350** |
| ptt5 | 513,216 | 52,221 | 49,759 | **39,860** | 43,640 | 40,939 | 44,755 |
| sum | 38,240 | 12,838 | 12,909 | **9,500** | 11,107 | 10,144 | 10,147 |
| xargs.1 | 4,227 | 1,736 | 1,762 | 1,812 | 1,724 | **1,464** | 1,483 |
| **Total** | 2,810,784 | 727,820 (25.9%) | 542,710 (19.3%) | 493,080 (17.5%) | 516,357 (18.4%) | 490,662 (17.5%) | **401,417 (14.3%)** |

`sedge` wins 8 of 11 files and the total: its output is **18% smaller than
the best competitor** (brotli -11). It still loses on a fax image (`ptt5`)
and a SPARC executable (`sum`), which need 2-D and record models (Phase 2),
and on `xargs.1`, where brotli's built-in English dictionary — shared
knowledge — pays off (Phase 3).

### enwik8 (first 100 MB of English Wikipedia, the Hutter Prize data)

| Compressor | Size (bytes) | Ratio | Bits per byte |
|---|---:|---:|---:|
| gzip -9 | 36,475,792 | 36.48% | 2.918 |
| bzip2 -9 | 29,008,758 | 29.01% | 2.321 |
| zstd -19 | 26,936,936 | 26.94% | 2.155 |
| brotli -11 | 25,742,001 | 25.74% | 2.059 |
| xz -9e | 24,831,648 | 24.83% | 1.987 |
| **sedge** (default, ~140 MiB) | **21,793,239** | **21.79%** | **1.743** |

12% smaller than xz -9e, 15% smaller than brotli -11. For perspective, the
best research compressors (cmix, nncp) reach ~15 MB on enwik8 at hundreds of times less
speed: there is still a lot of edge left to take.

### Speed — the honest part

Measured on a 2.1 GHz Xeon (one core): **~0.5 MiB/s** compression and
decompression (enwik8 takes ~3.5 minutes each way). xz -9e runs at ~1.9 MiB/s and zstd at
hundreds of MiB/s on the same machine. Like every context-mixing compressor,
`sedge` buys ratio with computation. Making that computation cheap is the
main goal of [Phase 1](ROADMAP.md#phase-1--speed-the-main-frontier).

### Preliminary: shared knowledge

If sender and receiver already share some data `K`, the true cost of a new
file `X` is the conditional information `H(X | K)`. A first measurement, with
`K` = just two English books from the Canterbury corpus (~900 KB) and cost
estimated as `size(K + X) − size(K)`:

| File | Original | brotli -11 | sedge | **sedge given K** |
|---|---:|---:|---:|---:|
| xargs.1 | 4,227 | 1,464 | 1,483 | **1,290** |
| grammar.lsp | 3,721 | 1,124 | 1,019 | **935** |
| cp.html | 24,603 | 6,894 | 6,485 | **6,123** |
| fields.c | 11,150 | 2,717 | 2,461 | **2,410** |
| 3 KB of *Alice in Wonderland* (bytes 1,000–4,000 of `alice29.txt`) | 3,000 | 1,217 | 1,278 | **930** |

Small messages gain the most — and small messages are most of what networks
carry. Reproduce with `bench/shared_knowledge.py`. Turning this into real
knowledge packs is Phase 3 of the [roadmap](ROADMAP.md).

### What it cannot do (and nothing can)

Random, encrypted or already-compressed data (JPEG, H.265 video, ZIP) does
not compress — by `sedge` or by anything else. Compressing *every* file to 1%
is not hard; it is **mathematically excluded** by a one-line counting
argument. [`docs/THEORY.md`](docs/THEORY.md) has the proof, plus the one lever
that genuinely moves the limit (shared knowledge). What `sedge` guarantees
instead: incompressible input grows by at most 20 bytes.

## Quick start

```sh
cargo build --release

./target/release/sedge compress   big.log            # -> big.log.sedge
./target/release/sedge decompress big.log.sedge      # -> big.log
./target/release/sedge bench      file1 file2 ...    # ratio + speed, verified
./target/release/sedge compress   big.log -m 24      # more memory, better ratio
```

As a library:

```rust
let packed = shannon_edge::compress(&data, &shannon_edge::Options::default());
let back = shannon_edge::decompress(&packed)?; // CRC-32 verified
assert_eq!(back, data);
```

Reproduce the benchmark tables:

```sh
pip install zstandard brotli   # optional competitors
python3 bench/compare.py path/to/canterbury/*
```

## How it works

```
             ┌──────────── models (each predicts P(next bit = 1)) ────────────┐
 history ──▶ │ order 0 · order 1 · order 2 · order 3 · order 4 · order 6      │
             │ word · previous word + word · sparse · match (long repeats)    │
             └───────────────────────────────┬────────────────────────────────┘
                                             ▼
                3 online neural mixers (weights picked by context)
                                             ▼
                          final mixer ─▶ 3 SSE / APM stages
                                             ▼
                      p ─▶ arithmetic coder ─▶ -log2(p) bits
```

* **Context models** keep adaptive bit probabilities in hash tables laid out
  so that each context touches one 64-byte cache line per nibble.
* **The match model** finds the longest earlier occurrence of the recent
  bytes and predicts that history repeats.
* **Mixers** are online logistic regressions that learn, while compressing,
  which models to trust in which situation.
* **SSE stages** correct the remaining bias of the mixed probability.
* The decoder runs the exact same model on the same history, so nothing but
  the coded surprise is stored. All arithmetic is integer, so output is
  bit-identical on every platform — enforced by a golden-stream test on
  Linux, macOS and Windows.

The file format is specified in [`docs/FORMAT.md`](docs/FORMAT.md).

## Project layout

| Path | Contents |
|---|---|
| `src/model.rs` | The predictor: context models, match model, mixers, SSE |
| `src/coder.rs` | Binary arithmetic coder |
| `src/math.rs` | Integer logistic functions and hashing |
| `src/lib.rs` | Public API and `.sedge` container |
| `src/main.rs` | `sedge` command-line tool |
| `tests/` | Round-trip, adversarial, corruption and golden-format tests |
| `bench/compare.py` | Benchmark against gzip, bzip2, xz, zstd and brotli |
| `bench/shared_knowledge.py` | Shared-knowledge (conditional cost) experiment |
| `docs/THEORY.md` | The limits, with proofs, and how to move them honestly |
| `docs/FORMAT.md` | `.sedge` format specification |
| `ROADMAP.md` | Where this goes next |

## License

MIT — see [LICENSE](LICENSE).
