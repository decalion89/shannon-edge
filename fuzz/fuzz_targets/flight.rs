//! The flight profile's frame decoder fed arbitrary frames: never a panic or
//! hang; decoded samples always fit the session's sample width.
#![no_main]
use libfuzzer_sys::fuzz_target;
use shannon_edge::flight::FlightSession;

fuzz_target!(|data: &[u8]| {
    let Some((&b, mut rest)) = data.split_first() else {
        return;
    };
    let bits = 1 + (b as u32 % 16);
    let mut rx = FlightSession::new(bits, 12);
    while let Some((&n, tail)) = rest.split_first() {
        let n = (n as usize).min(tail.len());
        let (frame, next) = tail.split_at(n);
        rest = next;
        if let Ok(s) = rx.decompress(frame) {
            assert!(s.iter().all(|&v| u32::from(v) >> bits == 0));
        }
    }
});
