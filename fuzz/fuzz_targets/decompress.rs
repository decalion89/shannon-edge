//! Any byte string given to the file decoder must yield Ok or Err, never a
//! panic, hang or out-of-bounds access.
#![no_main]
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    let _ = shannon_edge::decompress(data);
});
