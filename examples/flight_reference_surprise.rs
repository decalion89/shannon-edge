//! Per-sample cost under a *reference* flight model: a session learns
//! the first TRAIN samples, is snapshotted, and every later block of BLOCK
//! samples is coded by a fresh copy of that snapshot. Inside a block the
//! copy still learns, so each block is coded by a valid sequential code and
//! the Kraft bound holds for every sample. Across blocks it never
//! habituates: a long anomalous state stays costly for its whole length
//! instead of only at its onset.
//!
//!     cargo run --release --example flight_reference_surprise -- \
//!         SAMPLES.u16 OUT.u32 TRAIN BLOCK [TABLE_BITS]
//!
//! Writes one little-endian u32 per sample, its cost in 1/256 bits. The
//! first TRAIN samples get the adaptive session's own costs.

use shannon_edge::flight::FlightSession;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let raw = std::fs::read(&args[0]).expect("read samples");
    let train: usize = args[2].parse().expect("TRAIN");
    let block: usize = args[3].parse::<usize>().expect("BLOCK").max(1);
    let table_bits: u32 = args.get(4).map_or(14, |v| v.parse().expect("TABLE_BITS"));
    let samples: Vec<u16> = raw
        .chunks_exact(2)
        .map(|c| u16::from_le_bytes([c[0], c[1]]))
        .collect();
    let max = *samples.iter().max().unwrap_or(&0) as u32;
    let bits = (32 - max.leading_zeros()).max(1);
    let train = train.min(samples.len());
    let mut s = FlightSession::new(bits, table_bits);
    let mut cost = Vec::with_capacity(samples.len());
    for packet in samples[..train].chunks(256) {
        s.compress_scored(packet, &mut cost);
    }
    for b in samples[train..].chunks(block) {
        let mut copy = s.clone();
        for packet in b.chunks(256) {
            copy.compress_scored(packet, &mut cost);
        }
    }
    let out: Vec<u8> = cost.iter().flat_map(|c| c.to_le_bytes()).collect();
    std::fs::write(&args[1], out).expect("write costs");
}
