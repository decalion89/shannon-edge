# `.sedge` container format — version 1

All integers are little-endian.

| Offset | Size | Field | Description |
|---:|---:|---|---|
| 0 | 4 | `magic` | ASCII `SEDG` |
| 4 | 1 | `version` | Format version, currently `1` |
| 5 | 1 | `method` | `0` = stored, `1` = context mixing (CM), `2` = parallel blocks, `3` = CM with dictionary |
| 6 | 1 | `mem_bits` | Model memory level, `16..=24` for CM, `0` otherwise |
| 7 | 1 | `reserved` | Must be `0` |
| 8 | 8 | `length` | Original size in bytes (v1: below 2^32 − 1) |
| 16 | 4 | `crc32` | CRC-32 (IEEE, as in gzip/zip/PNG) of the original data |
| 20 | … | `payload` | Stored bytes, or the arithmetic-coded CM stream |

## Methods

* **Stored (`0`)** — the payload is the original data. The compressor uses it
  whenever CM would not make the file smaller, so no input ever grows by more
  than the 20-byte header.
* **CM (`1`)** — the payload is the output of a 32-bit binary arithmetic coder
  driven by the model in `src/model.rs`, with hashed context tables of
  `2^mem_bits` slots. The decoder must allocate the same tables, so
  `mem_bits` also sets the decoder's memory use (≈140 MiB at 22).
* **CM with dictionary (`3`)** — like CM, but before coding, the model reads
  a dictionary that both sides hold (it is never stored in the stream), so
  it starts out knowing that kind of data. The payload starts with the
  dictionary's CRC-32 (4 bytes) and length (4 bytes), followed by the CM
  stream. Decoding without the dictionary fails with `DictionaryRequired`;
  with a different one, with `DictionaryMismatch`. Priming means the model
  processes `dict + data` and only `data` is coded, so its match model can
  also copy straight from the dictionary.

* **Parallel blocks (`2`)** — the input was split into fixed-size blocks,
  each compressed independently so that blocks can be encoded and decoded on
  different cores. Payload layout:

  | Size | Field |
  |---:|---|
  | 4 | `block_size` used by the compressor (informational) |
  | 4 | `n`, number of blocks (≥ 1) |
  | 4 × n | byte length of each block stream |
  | … | the `n` block streams, back to back |

  Each block stream is a complete method-0, 1 or 3 stream with its own
  20-byte header and CRC (nesting method 2 is invalid). The decoded blocks,
  concatenated, must have exactly `length` bytes and match the outer CRC.
  The compressed bytes depend only on the data, `mem_bits` and `block_size`,
  never on how many threads were used. With a dictionary, every block is
  primed with the same dictionary, so blocks stay independent. If the
  blocked result would not be smaller than the input, the whole input is
  stored instead.

## Primed-model files (`.sedgem`)

A saved `PrimedModel`: the model state after reading a dictionary. It is a
cache for speed, not a stream format — `.sedge` streams never depend on
whether a model file or the raw dictionary was used.

| Size | Field |
|---:|---|
| 8 | magic `SEDGMODL` |
| 1 | format version (`1`) |
| 1 | memory level (`16..=24`) |
| 2 | reserved, `0` |
| 4 | CRC-32 of the dictionary |
| 4 | dictionary length `d` |
| d | the dictionary |
| … | model state, little-endian, in the order written by `Predictor::save` |
| 4 | CRC-32 of everything above |

Loading verifies both CRCs and range-checks every index and pointer; any
mismatch is `BadModel`. The state layout is tied to the model version: a
model change that bumps the format version also invalidates model files.

## Integrity

The decoder always recomputes the CRC-32 of its output and rejects the stream
(`ChecksumMismatch`) if it differs. Inconsistent block tables are rejected
(`BadBlockTable`). Corrupted or truncated payloads never
cause a panic: the arithmetic decoder reads missing bytes as zeros and the
checksum catches the result.

## Determinism and versioning

The CM payload is defined by the exact model arithmetic. The model therefore
uses integer arithmetic only, so every platform produces and accepts the same
bytes. The test `golden_v1_stream_is_reproduced_exactly` pins a reference
stream (`tests/fixtures/golden-v1.sedge`) in CI on Linux, macOS and Windows.

**Any change to the model that changes its output is a format change.** It
must bump `FORMAT_VERSION`, and the decoder must keep supporting every
earlier version, so files compressed today stay readable.
