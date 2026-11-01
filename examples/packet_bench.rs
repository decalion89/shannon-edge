//! Benchmark the packet profile on a file of fixed-length packets.
//!
//!     cargo run --release --example packet_bench -- PACKETS.bin PACKET_LEN [TABLE_BITS]
//!
//! Sends every packet through a sender and a receiver `PacketSession`,
//! verifies each one, and prints the total payload size (no framing: the
//! packet length is fixed, as for CCSDS 124 output) and the speed.

use shannon_edge::packet::PacketSession;
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let data = std::fs::read(&args[0]).expect("read packets");
    let len: usize = args[1].parse().expect("PACKET_LEN");
    let table_bits: u32 = args.get(2).map_or(16, |v| v.parse().expect("TABLE_BITS"));
    let (mut tx, mut rx) = (
        PacketSession::new(len, table_bits),
        PacketSession::new(len, table_bits),
    );
    let t = Instant::now();
    let mut total = 0usize;
    let mut n = 0usize;
    for packet in data.chunks_exact(len) {
        let payload = tx.compress(packet);
        total += payload.len();
        assert_eq!(rx.decompress(&payload).unwrap(), packet, "packet {n}");
        n += 1;
    }
    let secs = t.elapsed().as_secs_f64();
    println!(
        "{n} packets x {len} bytes ({} bytes) -> {total} bytes ({:.2}x), tables 2^{table_bits}, {:.1} MB/s (both directions, verified), {:.2}s",
        n * len,
        (n * len) as f64 / total as f64,
        (n * len) as f64 / secs / 1e6,
        secs
    );
}
