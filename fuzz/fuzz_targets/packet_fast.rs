//! A receiver of the fast packet profile fed arbitrary payloads: the first
//! byte picks the packet length, then each payload is a 1-byte length plus
//! bytes. Decoding garbage must never panic, and every payload that decodes
//! must have exactly the session's packet length.
#![no_main]
use libfuzzer_sys::fuzz_target;
use shannon_edge::packet_fast::FastPacketSession;

fuzz_target!(|data: &[u8]| {
    let Some((&l, mut rest)) = data.split_first() else {
        return;
    };
    let len = 1 + l as usize;
    let mut rx = FastPacketSession::new(len);
    let mut index = 0u64;
    while let Some((&n, tail)) = rest.split_first() {
        let n = (n as usize).min(tail.len());
        let (payload, next) = tail.split_at(n);
        rest = next;
        let r = if index % 3 == 2 {
            rx.decompress_indexed(index + 1, payload)
        } else {
            rx.decompress(payload)
        };
        if let Ok(p) = r {
            assert_eq!(p.len(), len);
        }
        index += 1;
    }
});
