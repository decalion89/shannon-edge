//! Uplinked record transforms are untrusted: any byte string must be
//! rejected or yield a transform whose inverse undoes its forward step.
#![no_main]
use libfuzzer_sys::fuzz_target;
use shannon_edge::fields::RecordTransform;

fuzz_target!(|data: &[u8]| {
    let (cfg, recs) = data.split_at(data.len().min(64));
    if let Ok(mut tx) = RecordTransform::from_bytes(cfg) {
        let mut rx = RecordTransform::from_bytes(cfg).unwrap();
        let len = tx.layout().len();
        if len == 0 || len > 4096 {
            return;
        }
        for r in recs.chunks_exact(len).take(64) {
            assert_eq!(rx.inverse(&tx.forward(r)), r);
        }
    }
});
