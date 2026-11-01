//! Benchmark the integer flight profile on a stream of 16-bit samples.
//!
//!     cargo run --release --example flight_bench -- SAMPLES.u16 [EXTRA_BYTES] [TABLE_BITS]
//!
//! Sends 256-sample packets through a sender and a receiver
//! `FlightSession`, verifies every packet, and prints the total size
//! (+1 kind byte per packet, as in a lean session frame, + EXTRA_BYTES,
//! e.g. a codebook)
//! and the speed.

use shannon_edge::flight::FlightSession;
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let raw = std::fs::read(&args[0]).expect("read samples");
    let extra: usize = args.get(1).map_or(0, |v| v.parse().expect("EXTRA_BYTES"));
    let table_bits: u32 = args.get(2).map_or(18, |v| v.parse().expect("TABLE_BITS"));
    let samples: Vec<u16> = raw
        .chunks_exact(2)
        .map(|c| u16::from_le_bytes([c[0], c[1]]))
        .collect();
    let max = *samples.iter().max().unwrap_or(&0) as u32;
    let bits = (32 - max.leading_zeros()).max(1);
    let (mut tx, mut rx) = (
        FlightSession::new(bits, table_bits),
        FlightSession::new(bits, table_bits),
    );
    let t = Instant::now();
    let mut total = extra;
    for packet in samples.chunks(256) {
        let frame = tx.compress(packet);
        // The frame already carries the sample count (the length); a lean
        // session frame adds one kind byte.
        total += frame.len() + 1;
        assert_eq!(rx.decompress(&frame).expect("decode"), packet);
    }
    let secs = t.elapsed().as_secs_f64();
    println!(
        "{}: {} samples ({bits}-bit), {} bytes, {:.2} M samples/s (both directions, verified), tables 2^{table_bits}",
        args[0],
        samples.len(),
        total,
        samples.len() as f64 / secs / 1e6
    );
}
