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
| **sedge** `-b 0` (one block) | **21,793,239** | **21.79%** | **1.743** |
| **sedge** (default: 8 MiB blocks, parallel) | 22,691,880 | 22.69% | 1.815 |

In single-block mode, 12% smaller than xz -9e and 15% smaller than brotli -11. For perspective, the
best research compressors (cmix, nncp) reach ~15 MB on enwik8 at hundreds of times less
speed: there is still a lot of edge left to take.

### Speed — the honest part

A context-mixing model is expensive: one core runs at **~0.5 MiB/s**. So
`sedge` splits large inputs into independent 8 MiB blocks and compresses and
decompresses them on all cores. The output depends only on the block size,
never on the number of cores, so the same file gives the same bytes on any
machine. enwik8 on 4 cores of a 2.1 GHz Xeon:

| Mode | Size (bytes) | Compress | Decompress | vs. single block |
|---|---:|---:|---:|---:|
| `-b 0` (one block, max ratio) | 21,793,239 | 0.48 MiB/s | 0.48 MiB/s | — |
| `-b 32` | 22,097,516 | 1.39 MiB/s | 1.47 MiB/s | +1.4% |
| `-b 16` | 22,354,674 | 1.53 MiB/s | 1.50 MiB/s | +2.6% |
| **`-b 8` (default)** | **22,691,880** | **2.01 MiB/s** | **2.02 MiB/s** | +4.1% |

With the default, `sedge` is faster than single-threaded `xz -9e` (~1.9 MiB/s on the same
machine) and still 8.6% smaller. zstd remains in another league for speed
(hundreds of MiB/s). Each worker holds its own model (~140 MiB), so memory
grows with the thread count; `-t` limits threads. Closing the rest of the gap
is [Phase 1](ROADMAP.md#phase-1--speed-the-main-frontier).

### Shared knowledge: dictionaries (`-D`)

If sender and receiver already share some data `K`, the true cost of a new
file `X` is the conditional information `H(X | K)`, which can be far below
`H(X)`. With `-D K`, the model reads `K` before coding (`K` is never stored;
the stream records only its CRC and length, and decoding requires the same
file).

**Small messages.** Dictionary = two English books from the Canterbury corpus
(908,615 bytes). Real `.sedge` sizes, all verified:

| File | Original | brotli -11 | sedge | **sedge -D** |
|---|---:|---:|---:|---:|
| xargs.1 | 4,227 | 1,464 | 1,483 | **1,322** |
| grammar.lsp | 3,721 | 1,124 | 1,019 | **965** |
| cp.html | 24,603 | 6,894 | 6,485 | **6,152** |
| fields.c | 11,150 | 2,717 | 2,461 | **2,442** |
| 3 KB of *Alice in Wonderland* (bytes 1,000–4,000 of `alice29.txt`) | 3,000 | 1,217 | 1,278 | **962** |

**Block mode.** Every block is primed with the same dictionary, so blocks stay
independent (parallel) yet none starts from zero. enwik8 minus its first
4 MiB (95.8 MB), with dictionaries cut from that first 4 MiB (no overlap with
the data), 4 cores:

| Mode | Size (bytes) | Speed | Block-mode loss recovered |
|---|---:|---:|---:|
| one block (`-b 0`) | 20,896,796 | 0.53 MiB/s | — |
| 8 MiB blocks | 21,758,838 | 2.06 MiB/s | 0% |
| 8 MiB blocks + 1 MiB dictionary | 21,502,540 | 1.87 MiB/s | 30% |
| 8 MiB blocks + 4 MiB dictionary | 21,261,762 | 1.28 MiB/s | 58% |

**Primed models: pay for the dictionary once.** Reading a dictionary runs at
model speed, so `sedge prime` does it once and saves the primed model;
`-M` then loads it instead of re-reading. It is only a cache: streams made
with `-M` decode with `-D` and vice versa, byte-identical when the memory
level matches. Total command time for one 3 KB message, all verified:

| Message | Dictionary | `-D` (re-read) | `-M` (load) | Size with knowledge | Size without |
|---|---|---:|---:|---:|---:|
| *Alice* excerpt | 2 books, 908 KB | 1,664 ms | **427 ms** | 962 | 1,278 |
| last 3 KB of enwik8 | 4 MiB of enwik8 | 7,623 ms | **446 ms** | 764 | 1,211 |

The bigger the knowledge, the bigger the win: loading costs roughly the
same, re-reading grows with the dictionary. Model files are large (≈ the
model's memory, ~144 MB at the default level; `-m 20` gives ~43 MB and
986 bytes instead of 962 for the *Alice* excerpt). In a
long-running process, keep a `PrimedModel` in memory and skip the load too.

```sh
sedge prime samples.json                       # -> samples.json.sedgem
sedge compress msg.json -M samples.json.sedgem
sedge decompress msg.json.sedge -D samples.json   # either works
```

Reproduce the first table with `bench/shared_knowledge.py`.

### Small messages vs. the industry standard (zstd + trained dictionary)

For small records (API payloads, events, logs) the standard answer is zstd
with a dictionary trained on samples. Test: 1,000 real GitHub events from
GH Archive (2024-01-15, 16:00 UTC), each compressed **separately**. All
knowledge comes from 5,000 events of the previous hour (15:00 UTC); no test
record was ever seen. All sedge results verified bit-for-bit.

| Compressor (1,000 records, one by one) | Knowledge the receiver holds | Total bytes | vs zstd + dict |
|---|---|---:|---:|
| zstd -19 | none | 833,210 | +106.1% |
| brotli -11 | built-in | 727,176 | +79.9% |
| sedge | none | 726,386 | +79.7% |
| zstd -19 + its trained dictionary | 110 KiB | 404,285 | — |
| sedge -M, zstd's trained dictionary | 110 KiB | 334,447 | −17.3% |
| **sedge -M, sedge's own trained dictionary** | **110 KiB** | **327,667** | **−19.0%** |
| zstd -19, all 5,000 samples as raw dictionary | 18 MB | 376,960 | −6.8% |
| **sedge -M, primed on all 5,000 samples** | **18 MB** | **290,450** | **−28.2%** |

At **equal knowledge**, sedge wins at both budgets: −19% with 110 KiB
(and `sedge train` builds its dictionary in 2 s where zstd's trainer takes
113 s), −23% against zstd with the same 18 MB. The difference grows with
knowledge because a predictive model turns every sample into statistics,
while a copy-based dictionary can only reuse literal strings.

The price is speed. `PrimedModel::compress_message` (used by `sedge -M`)
works on the primed model in place and undoes its changes from a journal,
so a record costs time proportional to the record, not to the model:
~14 ms per record per direction (1,000 records compress + decompress +
verify in 28 s, whether the model was primed on 110 KiB or on 18 MB; before
the journal: 63 s and 130 s). zstd takes microseconds. `.sedgem` model
files are large (here 162 MB). Reproduce with
`bench/small_messages.py`.

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
./target/release/sedge compress   big.log -b 0 -m 24 # max ratio: one block, more memory
./target/release/sedge compress   big.log -t 2       # limit to 2 threads
./target/release/sedge train samples/*.json -o samples.dict    # distil samples into a dictionary
./target/release/sedge compress   msg.json -D samples.dict   # shared-knowledge dictionary
./target/release/sedge decompress msg.json.sedge -D samples.dict
```

As a library:

```rust
let opts = shannon_edge::Options::default();
let packed = shannon_edge::compress(&data, &opts);
let back = shannon_edge::decompress(&packed)?; // CRC-32 verified
assert_eq!(back, data);

// With shared knowledge both sides hold:
let packed = shannon_edge::compress_with_dictionary(&data, &dict, &opts);
let back = shannon_edge::decompress_with_dictionary(&packed, &dict, 0)?;

// Prime once, then compress many messages from the primed state
// (in place, journaled: cost proportional to the message):
let mut model = shannon_edge::PrimedModel::new(&dict, &opts);
let packed = model.compress_message(&msg, &opts);
let back = model.decompress_message(&packed)?;
std::fs::write("dict.sedgem", model.to_bytes())?; // PrimedModel::from_bytes to load
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
| `src/train.rs` | Dictionary trainer (`sedge train`) |
| `src/main.rs` | `sedge` command-line tool |
| `tests/` | Round-trip, adversarial, corruption and golden-format tests |
| `bench/compare.py` | Benchmark against gzip, bzip2, xz, zstd and brotli |
| `bench/shared_knowledge.py` | Compression with vs. without a shared dictionary |
| `bench/small_messages.py` | Many small records: sedge vs zstd with a trained dictionary |
| `docs/THEORY.md` | The limits, with proofs, and how to move them honestly |
| `docs/FORMAT.md` | `.sedge` format specification |
| `ROADMAP.md` | Where this goes next |

## License

MIT — see [LICENSE](LICENSE).
