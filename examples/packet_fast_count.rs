//! Compress-only driver for instruction counting on other architectures
//! (e.g. under QEMU for RISC-V). Compresses the first N packets of a file
//! with the fast profile and prints the total payload size; run with N = 0
//! to measure the start-up cost to subtract.
//!
//!     packet_fast_count PACKETS.bin PACKET_LEN N

use shannon_edge::packet_fast::FastPacketSession;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let data = std::fs::read(&args[0]).expect("read packets");
    let len: usize = args[1].parse().expect("PACKET_LEN");
    let n: usize = args[2].parse().expect("N");
    let mut tx = FastPacketSession::new(len);
    let mut total = 0usize;
    for p in data.chunks_exact(len).take(n) {
        total += tx.compress(p).len();
    }
    println!("{n} packets -> {total} bytes");
}
