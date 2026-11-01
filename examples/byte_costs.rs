//! Write the general model's per-byte cost (f32 bits) for a file.
//!
//!     cargo run --release --example byte_costs -- IN OUT.f32 [MEM_BITS] [RECORD_LEN]
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let data = std::fs::read(&a[0]).expect("read");
    let bits = a.get(2).map_or(20, |v| v.parse().expect("MEM_BITS"));
    let rec = a.get(3).map_or(0, |v| v.parse().expect("RECORD_LEN"));
    let c = shannon_edge::byte_costs(&data, bits, rec);
    let out: Vec<u8> = c.iter().flat_map(|v| v.to_le_bytes()).collect();
    std::fs::write(&a[1], out).expect("write");
}
