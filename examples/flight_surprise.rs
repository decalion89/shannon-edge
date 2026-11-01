//! Write the flight profile's per-sample surprise for a stream of samples.
//!
//!     cargo run --release --example flight_surprise -- SAMPLES.u16 OUT.u32 [TABLE_BITS] [OTHER.u32]
//!
//! With OTHER.u32, also writes the cost the unused model would have paid.
//!
//! Compresses SAMPLES (16-bit little-endian) in 256-sample packets with a
//! `FlightSession`, checks the receiver decodes every packet and computes
//! the same surprise, and writes one little-endian u32 per sample: its cost
//! in 1/256 bits. Used by `bench/anomaly.py`.

use shannon_edge::flight::FlightSession;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let raw = std::fs::read(&args[0]).expect("read samples");
    let table_bits: u32 = args.get(2).map_or(14, |v| v.parse().expect("TABLE_BITS"));
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
    let (mut sent, mut received) = (Vec::with_capacity(samples.len()), Vec::new());
    let mut other = Vec::with_capacity(samples.len());
    let mut bytes = 0usize;
    for packet in samples.chunks(256) {
        let frame = tx.compress_scored_both(packet, &mut sent, &mut other);
        bytes += frame.len() + 1;
        received.clear();
        assert_eq!(rx.decompress_scored(&frame, &mut received).unwrap(), packet);
        assert_eq!(&received[..], &sent[sent.len() - packet.len()..]);
    }
    let out: Vec<u8> = sent.iter().flat_map(|c| c.to_le_bytes()).collect();
    std::fs::write(&args[1], out).expect("write surprise");
    if let Some(p) = args.get(3) {
        let o: Vec<u8> = other.iter().flat_map(|c| c.to_le_bytes()).collect();
        std::fs::write(p, o).expect("write other");
    }
    eprintln!(
        "{} samples ({bits}-bit) -> {bytes} bytes; surprise written to {}",
        samples.len(),
        args[1]
    );
}
