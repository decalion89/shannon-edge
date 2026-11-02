//! Write the flight profile's per-sample cost and the cost of each sample's
//! two least significant bits (the transition model's last binary
//! decisions, given the high bits and the past), both in 1/256 bits.
//!
//!     cargo run --release --example flight_lowbits -- SAMPLES.u16 COST.u32 LOW.u32 [TABLE_BITS]
//!
//! The low-bit cost is a free, fine-scale increment of the coded entropy: a
//! local estimate of how many bits one more bit of resolution costs.
//! Used by `bench/tsbad_lowbits.py`.

use shannon_edge::flight::FlightSession;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let raw = std::fs::read(&args[0]).expect("read samples");
    let table_bits: u32 = args.get(3).map_or(14, |v| v.parse().expect("TABLE_BITS"));
    let samples: Vec<u16> = raw
        .chunks_exact(2)
        .map(|c| u16::from_le_bytes([c[0], c[1]]))
        .collect();
    let max = *samples.iter().max().unwrap_or(&0) as u32;
    let bits = (32 - max.leading_zeros()).max(1);
    let mut s = FlightSession::new(bits, table_bits);
    let (mut cost, mut low) = (
        Vec::with_capacity(samples.len()),
        Vec::with_capacity(samples.len()),
    );
    for packet in samples.chunks(256) {
        s.compress_scored_split(packet, &mut cost, &mut low);
    }
    let w = |v: &[u32]| v.iter().flat_map(|c| c.to_le_bytes()).collect::<Vec<u8>>();
    std::fs::write(&args[1], w(&cost)).expect("write costs");
    std::fs::write(&args[2], w(&low)).expect("write low-bit costs");
}
