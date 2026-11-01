//! Fast packet profile: one cheap decision per byte, one symbol per changed
//! byte.
//!
//! For fixed-length housekeeping packets, like [`crate::packet`], but built
//! for speed on weak processors:
//!
//! * every byte first codes "same as the byte above (previous packet)?",
//!   with one adaptive probability per column and small context (how long
//!   the column has been constant, whether the left neighbour just changed,
//!   whether this column changed last time) — no hashing, no mixing;
//! * a changed byte is coded as **one symbol**, its difference from the byte
//!   above, with an adaptive frequency table per column (a Fenwick tree,
//!   so coding and updating cost O(log 256)).
//!
//! Integer arithmetic only, deterministic, one arithmetic-coded payload per
//! packet with a minimal flush, no framing. Both ends must use the same
//! packet length and process the same packets in order.

use crate::coder::{Decoder, Encoder};
use crate::Error;

/// Frequency increment and the total that triggers halving.
const INC: u32 = 32;
const LIMIT: u32 = 1 << 15;
/// Symbols: deltas 1..=255 (a changed byte never has delta 0).
const SYMS: usize = 255;

/// Adaptive frequencies of the 255 possible deltas, with a Fenwick tree.
#[derive(Clone)]
struct Freq {
    f: [u16; 256],
    tree: [u32; 257],
    total: u32,
}

impl Freq {
    fn new() -> Self {
        let mut s = Self {
            f: [0; 256],
            tree: [0; 257],
            total: 0,
        };
        for f in &mut s.f[..SYMS] {
            *f = 1;
        }
        s.rebuild();
        s
    }

    fn rebuild(&mut self) {
        self.tree = [0; 257];
        self.total = 0;
        for i in 0..256 {
            self.total += self.f[i] as u32;
            let mut j = i + 1;
            while j <= 256 {
                self.tree[j] += self.f[i] as u32;
                j += j & j.wrapping_neg();
            }
        }
    }

    /// Sum of the frequencies of symbols below `s`.
    #[inline]
    fn cum(&self, s: usize) -> u32 {
        let mut j = s;
        let mut c = 0;
        while j > 0 {
            c += self.tree[j];
            j &= j - 1;
        }
        c
    }

    /// The symbol whose range contains `v`, and its cumulative start.
    #[inline]
    fn find(&self, mut v: u32) -> (usize, u32) {
        let mut pos = 0;
        let mut cum = 0;
        let mut mask = 256;
        while mask > 0 {
            let next = pos + mask;
            if next <= 256 && self.tree[next] <= v {
                pos = next;
                v -= self.tree[next];
                cum += self.tree[next];
            }
            mask >>= 1;
        }
        (pos.min(SYMS - 1), cum)
    }

    #[inline]
    fn update(&mut self, s: usize) {
        if self.total + INC > LIMIT {
            for f in &mut self.f[..SYMS] {
                *f = (*f >> 1).max(1);
            }
            self.rebuild();
        }
        self.f[s] += INC as u16;
        self.total += INC;
        let mut j = s + 1;
        while j <= 256 {
            self.tree[j] += INC;
            j += j & j.wrapping_neg();
        }
    }
}

/// Per-column state.
#[derive(Clone, Copy, Default)]
struct Column {
    /// Packets since the column last changed (capped at 15).
    run: u8,
    changed_last: bool,
}

/// One end of a link carrying fixed-length packets (fast profile).
#[derive(Clone)]
pub struct FastPacketSession {
    len: usize,
    above: Vec<u8>,
    cols: Vec<Column>,
    /// "Same" probabilities (16-bit), 64 contexts per column.
    same: Vec<u16>,
    /// Delta frequencies, two tables per column (left neighbour changed or not).
    freq: Vec<Freq>,
    /// Epoch length in packets (0 = none) and the state to restart from.
    epoch: u64,
    origin: Option<Box<FastPacketSession>>,
    /// Packets processed (both ends) and, receiver only, lost sync.
    count: u64,
    desynced: bool,
}

enum Io<'a, 'b> {
    Enc(&'a mut Encoder),
    Dec(&'a mut Decoder<'b>),
}

impl FastPacketSession {
    /// A session for packets of `packet_len` bytes (1..=65536).
    ///
    /// # Panics
    /// If `packet_len` is out of range.
    pub fn new(packet_len: usize) -> Self {
        assert!((1..=65536).contains(&packet_len), "packet_len in 1..=65536");
        Self {
            len: packet_len,
            above: vec![0; packet_len],
            cols: vec![Column::default(); packet_len],
            same: vec![1 << 15; packet_len * 64],
            freq: vec![Freq::new(); packet_len * 2],
            epoch: 0,
            origin: None,
            count: 0,
            desynced: false,
        }
    }

    /// Learn from historical packets before the link starts (both ends must
    /// prime with the same packets). Nothing is transmitted.
    ///
    /// # Panics
    /// If a packet has the wrong length, or epochs are already enabled.
    pub fn prime<'a>(&mut self, packets: impl IntoIterator<Item = &'a [u8]>) {
        assert!(self.origin.is_none(), "prime before enabling epochs");
        for p in packets {
            self.compress(p);
        }
        self.count = 0;
    }

    /// Restart from the current state every `every` packets on both ends,
    /// so that a receiver that missed packets resumes at the next epoch
    /// ([`FastPacketSession::decompress_indexed`]).
    ///
    /// # Panics
    /// If `every` is 0.
    pub fn with_epochs(mut self, every: u64) -> Self {
        assert!(every > 0, "epoch length must be positive");
        self.epoch = every;
        self.count = 0;
        self.origin = Some(Box::new(self.clone()));
        self
    }

    fn restart_at(&mut self, index: u64) {
        let origin = self.origin.take().expect("origin is set with epochs");
        *self = (*origin).clone();
        self.origin = Some(origin);
        self.count = index;
    }

    fn begin_packet(&mut self) {
        if self.epoch > 0 && self.count > 0 && self.count % self.epoch == 0 {
            self.restart_at(self.count);
        }
        self.count += 1;
    }

    /// Packet length this session was created with.
    pub fn packet_len(&self) -> usize {
        self.len
    }

    /// Model memory in bytes.
    pub fn memory_bytes(&self) -> usize {
        self.len * (1 + std::mem::size_of::<Column>())
            + self.same.len() * 2
            + self.freq.len() * std::mem::size_of::<Freq>()
    }

    // `packet` is empty when decoding, so the loop runs over the column index.
    #[allow(clippy::needless_range_loop)]
    fn code_packet(&mut self, packet: &[u8], io: &mut Io, out: &mut Vec<u8>) {
        let mut left_changed = false;
        for k in 0..self.len {
            let above = self.above[k];
            let c = self.cols[k];
            // 1. Same as above?
            let ctx = k * 64
                + (c.run as usize) * 4
                + (left_changed as usize) * 2
                + c.changed_last as usize;
            let p16 = self.same[ctx] as u32;
            let p1 = (p16 >> 4).clamp(1, 4095);
            let same = match io {
                Io::Enc(e) => {
                    let bit = (packet[k] == above) as u32;
                    e.encode(bit, p1);
                    bit
                }
                Io::Dec(d) => d.decode(p1),
            };
            let target = (same << 16) as i32;
            self.same[ctx] = (p16 as i32 + ((target - p16 as i32) >> 4)).clamp(0, 65535) as u16;
            let col = &mut self.cols[k];
            let value = if same == 1 {
                col.run = (col.run + 1).min(15);
                col.changed_last = false;
                left_changed = false;
                above
            } else {
                col.run = 0;
                col.changed_last = true;
                // 2. The delta from above, one symbol.
                let f = &mut self.freq[k * 2 + left_changed as usize];
                let s = match io {
                    Io::Enc(e) => {
                        let s = packet[k].wrapping_sub(above) as usize - 1;
                        let cum = f.cum(s);
                        if !e.encode_freq(cum, f.f[s] as u32, f.total) {
                            for i in (0..8).rev() {
                                e.encode((s as u32 >> i) & 1, 2048);
                            }
                        }
                        s
                    }
                    Io::Dec(d) => match d.decode_target(f.total) {
                        Some(v) => {
                            let (s, cum) = f.find(v);
                            d.decode_freq(cum, f.f[s] as u32, f.total);
                            s
                        }
                        None => {
                            let mut s = 0;
                            for _ in 0..8 {
                                s = (s << 1) | d.decode(2048) as usize;
                            }
                            s.min(SYMS - 1)
                        }
                    },
                };
                f.update(s);
                left_changed = true;
                above.wrapping_add(s as u8 + 1)
            };
            out.push(value);
        }
    }

    /// Compress one packet (exactly `packet_len` bytes) and learn from it.
    ///
    /// # Panics
    /// If the packet has the wrong length.
    pub fn compress(&mut self, packet: &[u8]) -> Vec<u8> {
        assert_eq!(packet.len(), self.len, "packet length");
        self.begin_packet();
        let mut enc = Encoder::new(self.len / 2);
        let mut out = Vec::with_capacity(self.len);
        self.code_packet(packet, &mut Io::Enc(&mut enc), &mut out);
        self.above.copy_from_slice(packet);
        enc.finish_short()
    }

    /// Decompress the next packet and learn from it. A corrupt payload
    /// decodes to a wrong packet (and desynchronises the session) but never
    /// panics; integrity is the link layer's job, as for CCSDS 124.
    pub fn decompress(&mut self, payload: &[u8]) -> Result<Vec<u8>, Error> {
        self.begin_packet();
        let mut dec = Decoder::new(payload);
        let mut out = Vec::with_capacity(self.len);
        self.code_packet(&[], &mut Io::Dec(&mut dec), &mut out);
        self.above.copy_from_slice(&out);
        Ok(out)
    }

    /// Decompress the packet with sequence number `index` (0-based, counted
    /// by the sender). After a gap, packets return
    /// [`Error::SessionOutOfSync`] until the next epoch boundary, where
    /// decoding resumes.
    pub fn decompress_indexed(&mut self, index: u64, payload: &[u8]) -> Result<Vec<u8>, Error> {
        if index < self.count {
            return Err(Error::SessionOutOfSync {
                expected: self.count,
                got: index,
            });
        }
        if index > self.count {
            self.desynced = true;
            self.count = index;
        }
        if self.desynced {
            if self.epoch == 0 || index % self.epoch != 0 {
                self.count = index + 1;
                return Err(Error::SessionOutOfSync {
                    expected: self.count,
                    got: index,
                });
            }
            self.restart_at(index);
            self.desynced = false;
        }
        self.decompress(payload)
    }
}
