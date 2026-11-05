# Contributing

Ideas that move the edge are welcome — especially ones that make prediction
faster, or prediction better per unit of time.

## The rules of the game

1. **Lossless, always.** Every change must keep `cargo test` green; the tests
   round-trip random, structured, empty and corrupted inputs.
2. **Claims need numbers.** A change that affects compression must include a
   before/after table from `bench/compare.py` on at least the Canterbury
   corpus, with sizes in bytes. Report losses as well as wins.
3. **Model changes are format changes.** If the golden test
   (`golden_v1_stream_is_reproduced_exactly`) fails, your change altered the
   compressed bytes. Bump `FORMAT_VERSION`, keep decoding older versions, and
   regenerate the fixture with `SEDGE_BLESS=1 cargo test --release`.
4. **Integer arithmetic only** in the model, so every platform agrees.

## Before opening a pull request

```sh
cargo fmt
cargo clippy --all-targets -- -D warnings
cargo test --release
```
