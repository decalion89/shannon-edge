//! Benchmark the packet profile on a file of fixed-length packets.
//!
//!     cargo run --release --example packet_bench -- PACKETS.bin PACKET_LEN [TABLE_BITS]
//!
//! Sends every packet through a sender and a receiver `PacketSession`,
//! verifies each one, and prints the total payload size (no framing: the
//! packet length is fixed, as for CCSDS 124 output) and the speed. Set
//! SEDGE_PACKET_V2=1 to run version 2 of the profile.

use shannon_edge::packet::PacketSession;
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let data = std::fs::read(&args[0]).expect("read packets");
    let len: usize = args[1].parse().expect("PACKET_LEN");
    let table_bits: u32 = args.get(2).map_or(16, |v| v.parse().expect("TABLE_BITS"));
    let v2 = std::env::var_os("SEDGE_PACKET_V2").is_some();
    let make = || {
        if v2 {
            PacketSession::v2(len, table_bits)
        } else {
            PacketSession::new(len, table_bits)
        }
    };
    let (mut tx, mut rx) = (make(), make());
    let packets: Vec<&[u8]> = data.chunks_exact(len).collect();
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
        "{n} packets x {len} bytes ({} bytes) -> {total} bytes ({:.2}x), tables 2^{table_bits}{}, \
         memory {:.0} KiB, compress {:.1} MB/s, decompress {:.1} MB/s (verified), {:.2}s",
        n * len,
        (n * len) as f64 / total as f64,
        if v2 { ", v2" } else { "" },
        tx.memory_bytes() as f64 / 1024.0,
        mb / enc,
        mb / dec,
        enc + dec
    );
}
