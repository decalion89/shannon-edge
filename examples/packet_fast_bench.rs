//! Benchmark the fast packet profile on a file of fixed-length packets.
//!
//!     cargo run --release --example packet_fast_bench -- PACKETS.bin PACKET_LEN
//!
//! Compresses every packet, then decompresses and verifies every one, and
//! prints the total payload size, the model memory and both speeds.

use shannon_edge::packet_fast::FastPacketSession;
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let data = std::fs::read(&args[0]).expect("read packets");
    let len: usize = args[1].parse().expect("PACKET_LEN");
    let packets: Vec<&[u8]> = data.chunks_exact(len).collect();
    let (mut tx, mut rx) = (FastPacketSession::new(len), FastPacketSession::new(len));
    let t = Instant::now();
    let payloads: Vec<Vec<u8>> = packets.iter().map(|p| tx.compress(p)).collect();
    let enc = t.elapsed().as_secs_f64();
    let t = Instant::now();
    for (n, (payload, packet)) in payloads.iter().zip(&packets).enumerate() {
        assert_eq!(&rx.decompress(payload).unwrap(), packet, "packet {n}");
    }
    let dec = t.elapsed().as_secs_f64();
    let n = packets.len();
    let total: usize = payloads.iter().map(Vec::len).sum();
    let mb = (n * len) as f64 / 1e6;
    println!(
        "{n} packets x {len} bytes ({} bytes) -> {total} bytes ({:.2}x), fast profile, \
         memory {:.0} KiB, compress {:.1} MB/s, decompress {:.1} MB/s (verified)",
        n * len,
        (n * len) as f64 / total as f64,
        tx.memory_bytes() as f64 / 1024.0,
        mb / enc,
        mb / dec
    );
}
