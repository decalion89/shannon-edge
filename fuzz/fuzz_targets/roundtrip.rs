//! Losslessness on adversarial inputs: whatever the fuzzer builds must come
//! back bit-exact from the file format and from both packet profiles.
#![no_main]
use libfuzzer_sys::fuzz_target;
use shannon_edge::packet::PacketSession;
use shannon_edge::packet_fast::FastPacketSession;

fuzz_target!(|data: &[u8]| {
    let opts = shannon_edge::Options::default();
    let c = shannon_edge::compress(data, &opts);
    assert_eq!(shannon_edge::decompress(&c).expect("own output"), data);

    let Some((&l, body)) = data.split_first() else {
        return;
    };
    let len = 1 + l as usize % 64;
    let (mut ft, mut fr) = (FastPacketSession::new(len), FastPacketSession::new(len));
    let (mut vt, mut vr) = (PacketSession::v2(len, 12), PacketSession::v2(len, 12));
    for p in body.chunks_exact(len) {
        assert_eq!(fr.decompress(&ft.compress(p)).expect("fast"), p);
        assert_eq!(vr.decompress(&vt.compress(p)).expect("v2"), p);
    }
});
