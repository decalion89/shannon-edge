//! Packet profile: a small, integer-only codec for fixed-length telemetry
//! packets (housekeeping data), the use case of CCSDS 124.0-B-1 / POCKET+.
//!
//! Every byte position of the packet is a *column* (one field, or part of
//! one). Each byte is predicted from its column's history — the byte at the
//! same position in the previous packet ("above"), the one two packets back,
//! and its left neighbour in the current packet — by two small models:
//!
//! * a **transition model** (orders over those column contexts, mixed by a
//!   small integer mixer): "which value tends to follow which";
//! * a **residual model**: the difference from the byte above, with adaptive
//!   contexts per column (what a delta coder does, but adaptive);
//!
//! and each column uses whichever model was cheaper on its recent bytes.
//! Both ends know those bytes, so the choice is never transmitted.
//!
//! One arithmetic-coded payload per packet, minimal flush, no framing,
//! checksum or sequence number: the packet length is fixed and the link
//! layer guarantees integrity and order. Integer arithmetic only. Memory:
//! about `5 * 4 * 2^table_bits` bytes (2^16: ~1.3 MiB).

use crate::coder::{Decoder, Encoder};
use crate::flight::{cost, h2, Table};
use crate::math::{squash, stretch};
use crate::Error;

/// Per-column state.
#[derive(Clone, Copy, Default)]
struct Column {
    above2: u8,
    last_len: u8,
    cost_t: u32,
    cost_r: u32,
    /// v2: packets since this column last changed (capped at 31).
    run: u8,
    /// v2: whether it changed in the previous (key) packet.
    chg_last: bool,
}

/// One end of a link carrying fixed-length packets. Both ends must use the
/// same `packet_len` and `table_bits` and process the same packets in order.
///
/// **Robustness to lost packets** (see [`PacketSession::with_epochs`]): every
/// `E` packets both ends return to a common *origin* state, so a lost packet
/// only affects the rest of its epoch. The origin can be a model already
/// trained on historical packets ([`PacketSession::prime`]), which makes
/// frequent resets cheap: the model restarts knowing the spacecraft.
#[derive(Clone)]
pub struct PacketSession {
    len: usize,
    above: Vec<u8>,
    cols: Vec<Column>,
    t: [Table; 4],
    res: Table,
    /// Mixer weights per bit depth (1.0 = 65536): 4 inputs + bias.
    w: [[i32; 5]; 8],
    /// Epoch length in packets (0 = no epochs) and the state to restart from.
    epoch: u64,
    origin: Option<Box<PacketSession>>,
    /// Packets processed since the session started (sender and receiver).
    count: u64,
    /// Receiver only: lost sync after a gap, waiting for the next epoch.
    desynced: bool,
    /// Epoch number of the current state.
    cur_epoch: u64,
    /// Key-packet interval (1 = every packet teaches the model).
    key: u64,
    /// Whether the packet being coded is a key packet (updates the model).
    learning: bool,
    /// v2: a byte-level "same as above" decision before the bit models.
    v2: bool,
    flag_t: [Table; 3],
    /// v2 flag mixer weights, by whether the left byte changed.
    wf: [[i32; 4]; 2],
    /// v2, per packet: did the previous byte change, how many changed so far.
    left_changed: bool,
    nchanged: u32,
    /// v2: SSE on the transition model, by column and bit position.
    apm: Apm,
    /// v2: SSE on the residual model, by column and coding step.
    apm_r: Apm,
    /// v2: SSE on the "same" decision, by column and run length.
    apm_f: Apm,
}

/// Secondary estimation (SSE): refines a probability given a context.
#[derive(Clone)]
struct Apm {
    t: Vec<u16>,
    idx: usize,
}

impl Apm {
    fn new(contexts: usize) -> Self {
        let row: Vec<u16> = (0..33)
            .map(|j| (squash((j - 16) * 128) * 16) as u16)
            .collect();
        Self {
            t: row.iter().copied().cycle().take(contexts * 33).collect(),
            idx: 0,
        }
    }

    fn pp(&mut self, pr: u32, cx: usize) -> u32 {
        let s = stretch(pr as i32) + 2048;
        let lo = (s >> 7) as usize;
        let w = s & 127;
        let base = cx * 33 + lo;
        self.idx = base + (w >> 6) as usize;
        let p = (self.t[base] as i32 * (128 - w) + self.t[base + 1] as i32 * w) >> 11;
        p.clamp(1, 4095) as u32
    }

    fn update(&mut self, bit: u32) {
        // Rate 1/64; the + 64 - 2 offset keeps the fixed point within u16.
        let g = ((bit as i32) << 16) + ((bit as i32) << 6) - 2 * bit as i32;
        let v = self.t[self.idx] as i32;
        self.t[self.idx] = (v + ((g - v) >> 6)) as u16;
    }
}

enum Io<'a, 'b> {
    Enc(&'a mut Encoder),
    Dec(&'a mut Decoder<'b>),
    Dry,
}

impl Io<'_, '_> {
    #[inline]
    fn bit(&mut self, p1: u32, bit: u32) -> u32 {
        match self {
            Io::Enc(e) => {
                e.encode(bit, p1);
                bit
            }
            Io::Dec(d) => d.decode(p1),
            Io::Dry => bit,
        }
    }
}

impl PacketSession {
    /// A session for packets of `packet_len` bytes (1..=65536) with model
    /// tables of `2^table_bits` entries (12..=24).
    ///
    /// # Panics
    /// If a parameter is out of range.
    pub fn new(packet_len: usize, table_bits: u32) -> Self {
        assert!((1..=65536).contains(&packet_len), "packet_len in 1..=65536");
        assert!((12..=24).contains(&table_bits), "table_bits in 12..=24");
        Self {
            len: packet_len,
            above: vec![0; packet_len],
            cols: vec![Column::default(); packet_len],
            t: [
                Table::new(table_bits),
                Table::new(table_bits),
                Table::new(table_bits),
                Table::new(table_bits),
            ],
            res: Table::new(table_bits),
            w: [[16_000; 5]; 8],
            epoch: 0,
            origin: None,
            count: 0,
            desynced: false,
            cur_epoch: 0,
            key: 1,
            learning: true,
            v2: false,
            flag_t: [Table::new(1), Table::new(1), Table::new(1)],
            wf: [[22_000; 4]; 2],
            left_changed: false,
            nchanged: 0,
            apm: Apm::new(0),
            apm_r: Apm::new(0),
            apm_f: Apm::new(0),
        }
    }

    /// Version 2 of the packet profile (a different, incompatible stream):
    /// each byte first codes one decision, "same as the byte above?", in
    /// contexts the bit models do not see (did the left neighbour change,
    /// how long the column has been constant, how many bytes of this packet
    /// changed so far); only changed bytes go through the bit models. In
    /// housekeeping data most bytes repeat, so this is both faster and
    /// smaller. Memory: `23 * 2^table_bits` bytes plus about 3.2 KiB per
    /// byte of packet ([`PacketSession::memory_bytes`]).
    ///
    /// # Panics
    /// If a parameter is out of range (as for [`PacketSession::new`]).
    pub fn v2(packet_len: usize, table_bits: u32) -> Self {
        let mut s = Self::new(packet_len, table_bits);
        let fb = table_bits - 2;
        s.v2 = true;
        s.flag_t = [Table::new(fb), Table::new(fb), Table::new(fb)];
        s.apm = Apm::new(packet_len * 16);
        s.apm_r = Apm::new(packet_len * 16);
        s.apm_f = Apm::new(packet_len * 16);
        s
    }

    /// v2: code "byte k equals the byte above" (1) or not (0).
    fn same_flag(&mut self, k: usize, same: u32, io: &mut Io) -> u32 {
        let c = self.cols[k];
        let col = k as u64 + 1;
        let lc = self.left_changed as usize;
        let s = [
            self.flag_t[0].slot(h2(col, c.run as u64 + 1)),
            self.flag_t[1].slot(h2(h2(col, (lc * 2) as u64 + c.chg_last as u64 + 1), 5)),
            self.flag_t[2].slot(h2(
                h2(col, self.nchanged.min(15) as u64 * 2 + lc as u64 + 1),
                9,
            )),
        ];
        let x = [
            stretch(self.flag_t[0].t[s[0]].p12() as i32),
            stretch(self.flag_t[1].t[s[1]].p12() as i32),
            stretch(self.flag_t[2].t[s[2]].p12() as i32),
            256,
        ];
        let w = &mut self.wf[lc];
        let dot: i64 = x
            .iter()
            .zip(w.iter())
            .map(|(&a, &b)| a as i64 * b as i64)
            .sum();
        let p0 = squash(((dot >> 16) as i32).clamp(-2047, 2047)).clamp(1, 4095) as u32;
        let a = self.apm_f.pp(p0, (k * 8 + c.run.min(7) as usize) * 2 + lc);
        let p = ((p0 + 3 * a) >> 2).clamp(1, 4095);
        let bit = io.bit(p, same);
        if self.learning {
            self.apm_f.update(bit);
            let err = ((bit as i32) << 12) - p0 as i32;
            for (wk, xk) in w.iter_mut().zip(x) {
                *wk += (xk * err) >> 10;
            }
            for (t, &sk) in self.flag_t.iter_mut().zip(&s) {
                t.t[sk].update(bit);
            }
        }
        bit
    }

    /// Only one packet in `every` (a *key packet*) teaches the model and
    /// becomes the reference ("above") for the next ones; the others are
    /// coded with the model frozen, relative to the last key packet. Losing
    /// a non-key packet then affects nothing else: only key packets need
    /// protection (e.g. sent twice, or with retransmission). Both ends must
    /// use the same interval; combine with [`PacketSession::with_epochs`]
    /// (a multiple of it) to recover from a lost key packet.
    ///
    /// # Panics
    /// If `every` is 0, or epochs are already enabled.
    pub fn with_key_interval(mut self, every: u64) -> Self {
        assert!(every > 0, "key interval must be positive");
        assert!(self.origin.is_none(), "set the key interval before epochs");
        self.key = every;
        self
    }

    fn is_key(&self, index: u64) -> bool {
        index % self.key == 0
    }

    /// Learn from historical packets before the link starts (both ends must
    /// prime with the same packets). Nothing is transmitted.
    ///
    /// # Panics
    /// If a packet has the wrong length, or epochs are already enabled.
    pub fn prime<'a>(&mut self, packets: impl IntoIterator<Item = &'a [u8]>) {
        assert!(self.origin.is_none(), "prime before enabling epochs");
        let key = std::mem::replace(&mut self.key, 1); // learn from all of them
        for p in packets {
            self.compress(p);
        }
        self.key = key;
        self.count = 0;
    }

    /// Restart from the current state (fresh, or primed) every `every`
    /// packets, on both ends. A receiver that misses packets resumes at the
    /// next epoch boundary ([`PacketSession::decompress_indexed`]).
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

    /// Return to the origin when packet `self.count` starts a new epoch.
    fn maybe_restart(&mut self) {
        if self.epoch > 0 && self.count / self.epoch != self.cur_epoch {
            self.restart_at(self.count);
        }
    }

    fn restart_at(&mut self, index: u64) {
        let origin = self.origin.take().expect("origin is set with epochs");
        *self = (*origin).clone();
        self.origin = Some(origin);
        self.count = index;
        self.cur_epoch = index / self.epoch;
    }

    /// Packet length this session was created with.
    pub fn packet_len(&self) -> usize {
        self.len
    }

    /// Model memory in bytes (tables, SSE stages and per-column state),
    /// excluding the epoch origin copy if epochs are enabled.
    pub fn memory_bytes(&self) -> usize {
        let tables: usize = self
            .t
            .iter()
            .chain([&self.res])
            .chain(&self.flag_t)
            .map(|t| t.t.len() * 4)
            .sum();
        let apms = (self.apm.t.len() + self.apm_r.t.len() + self.apm_f.t.len()) * 2;
        tables + apms + self.len * (1 + std::mem::size_of::<Column>())
    }

    /// Transition model for byte `k` with left neighbour `left`.
    fn transition(&mut self, k: usize, left: u8, value: u32, io: &mut Io) -> (u32, u32) {
        let above = self.above[k] as u64;
        let above2 = self.cols[k].above2 as u64;
        let col = k as u64 + 1;
        // Context hashes, computed once per byte.
        let ca = h2(col, above + 1);
        let ctx = [col, ca, h2(ca, above2 + 7), h2(ca, left as u64 + 3)];
        let mut node = 1u32;
        let mut total = 0;
        for i in (0..8).rev() {
            let n = node as u64;
            let s = [
                self.t[0].slot(h2(ctx[0], n)),
                self.t[1].slot(h2(ctx[1], n)),
                self.t[2].slot(h2(ctx[2], n)),
                self.t[3].slot(h2(ctx[3], n)),
            ];
            let x = [
                stretch(self.t[0].t[s[0]].p12() as i32),
                stretch(self.t[1].t[s[1]].p12() as i32),
                stretch(self.t[2].t[s[2]].p12() as i32),
                stretch(self.t[3].t[s[3]].p12() as i32),
                256,
            ];
            let w = &mut self.w[(7 - i) as usize];
            let dot: i64 = x
                .iter()
                .zip(w.iter())
                .map(|(&a, &b)| a as i64 * b as i64)
                .sum();
            let p0 = squash(((dot >> 16) as i32).clamp(-2047, 2047)).clamp(1, 4095) as u32;
            let p = if self.v2 {
                // Context: column, bit position, and whether the bits so
                // far equal those of the byte above.
                let pm = node as u64 == (1 << (7 - i)) | (above >> (i + 1));
                let cx = (k * 8 + (7 - i) as usize) * 2 + pm as usize;
                let a = self.apm.pp(p0, cx);
                ((p0 + 3 * a) >> 2).clamp(1, 4095)
            } else {
                p0
            };
            let bit = io.bit(p, (value >> i) & 1);
            total += cost(p, bit);
            if self.learning {
                if self.v2 {
                    self.apm.update(bit);
                }
                let err = ((bit as i32) << 12) - p0 as i32;
                for (wk, xk) in w.iter_mut().zip(x) {
                    *wk += (xk * err) >> 10;
                }
                for (t, &sk) in self.t.iter_mut().zip(&s) {
                    t.t[sk].update(bit);
                }
            }
            node = (node << 1) | bit;
        }
        (node & 0xff, total)
    }

    /// Residual model: byte minus the byte above, zigzag, adaptive contexts.
    fn residual(&mut self, k: usize, value: u32, io: &mut Io) -> (u32, u32) {
        let above = self.above[k];
        let r = (value as u8).wrapping_sub(above) as i8 as i32;
        let z = ((r << 1) ^ (r >> 31)) as u32; // 0..=255
        let n = 32 - z.leading_zeros(); // 0..=8
        let col = k as u64 + 1;
        let ctx = self.cols[k].last_len as u64;
        let mut total = 0;
        let mut len = 0u32;
        loop {
            let s = self.res.slot(h2(h2(col, ctx * 16 + len as u64), 1));
            let p0 = self.res.t[s].p12();
            let p = if self.v2 {
                let a = self.apm_r.pp(p0, k * 16 + len as usize);
                ((p0 + 3 * a) >> 2).clamp(1, 4095)
            } else {
                p0
            };
            let bit = io.bit(p, (len < n) as u32);
            total += cost(p, bit);
            if self.learning {
                self.res.t[s].update(bit);
                if self.v2 {
                    self.apm_r.update(bit);
                }
            }
            if bit == 0 || len >= 8 {
                break;
            }
            len += 1;
        }
        let mut v: u32 = (len != 0) as u32;
        for i in (0..len.saturating_sub(1)).rev() {
            let s = self.res.slot(h2(h2(col, len as u64 * 64 + v as u64), 2));
            let p0 = self.res.t[s].p12();
            let p = if self.v2 {
                let a = self.apm_r.pp(p0, k * 16 + 9 + i as usize);
                ((p0 + 3 * a) >> 2).clamp(1, 4095)
            } else {
                p0
            };
            let bit = io.bit(p, (z >> i) & 1);
            total += cost(p, bit);
            if self.learning {
                self.res.t[s].update(bit);
                if self.v2 {
                    self.apm_r.update(bit);
                }
            }
            v = (v << 1) | bit;
        }
        let r = ((v >> 1) as i32) ^ -((v & 1) as i32);
        let out = above.wrapping_add(r as i8 as u8) as u32;
        if self.learning {
            self.cols[k].last_len = len as u8;
        }
        (out, total)
    }

    fn byte(&mut self, k: usize, left: u8, value: u32, io: &mut Io) -> u8 {
        if self.v2 {
            let above = self.above[k];
            let same = self.same_flag(k, (value == above as u32) as u32, io);
            let learning = self.learning;
            let c = &mut self.cols[k];
            if same == 1 {
                if learning {
                    c.run = c.run.saturating_add(1).min(31);
                    c.chg_last = false;
                }
                self.left_changed = false;
                return above;
            }
            if learning {
                c.run = 0;
                c.chg_last = true;
            }
            self.left_changed = true;
            self.nchanged += 1;
        }
        let c = self.cols[k];
        let use_t = c.cost_t <= c.cost_r;
        if self.v2 && self.count % 16 != 1 {
            // v2: compare the two models on one packet in four only.
            return if use_t {
                self.transition(k, left, value, io).0 as u8
            } else {
                self.residual(k, value, io).0 as u8
            };
        }
        let (v, ct, cr) = if use_t {
            let (v, ct) = self.transition(k, left, value, io);
            let (_, cr) = self.residual(k, v, &mut Io::Dry);
            (v, ct, cr)
        } else {
            let (v, cr) = self.residual(k, value, io);
            let (_, ct) = self.transition(k, left, v, &mut Io::Dry);
            (v, ct, cr)
        };
        if self.learning {
            let c = &mut self.cols[k];
            c.cost_t = c.cost_t - (c.cost_t >> 4) + ct;
            c.cost_r = c.cost_r - (c.cost_r >> 4) + cr;
        }
        v as u8
    }

    fn end_packet(&mut self, packet: &[u8]) {
        if !self.learning {
            return; // non-key packets leave no trace
        }
        for (k, &b) in packet.iter().enumerate() {
            self.cols[k].above2 = self.above[k];
            self.above[k] = b;
        }
    }

    /// Compress one packet (exactly `packet_len` bytes) and learn from it.
    ///
    /// # Panics
    /// If the packet has the wrong length.
    pub fn compress(&mut self, packet: &[u8]) -> Vec<u8> {
        assert_eq!(packet.len(), self.len, "packet length");
        self.maybe_restart();
        self.learning = self.is_key(self.count);
        self.count += 1;
        let mut enc = Encoder::new(self.len);
        self.left_changed = false;
        self.nchanged = 0;
        {
            let mut io = Io::Enc(&mut enc);
            let mut left = 0u8;
            for (k, &b) in packet.iter().enumerate() {
                self.byte(k, left, b as u32, &mut io);
                left = b;
            }
        }
        self.end_packet(packet);
        enc.finish_short()
    }

    /// Decompress the packet with sequence number `index` (0-based, counted
    /// by the sender; e.g. from the CCSDS packet sequence count). A gap that
    /// lost only non-key packets ([`PacketSession::with_key_interval`]) is
    /// harmless. After a lost key packet, packets cannot be decoded until
    /// the next epoch boundary and return [`Error::SessionOutOfSync`]; from
    /// there decoding resumes.
    pub fn decompress_indexed(&mut self, index: u64, payload: &[u8]) -> Result<Vec<u8>, Error> {
        if index < self.count {
            return Err(Error::SessionOutOfSync {
                expected: self.count,
                got: index,
            });
        }
        if index > self.count {
            // Packets self.count..index were lost.
            let mut from = self.count;
            if let Some(n) = index.checked_div(self.epoch) {
                let start = n * self.epoch;
                if start >= from {
                    // Both ends restarted at this epoch boundary: whatever
                    // was lost before it no longer matters.
                    self.restart_at(start);
                    self.desynced = false;
                    from = start;
                }
            }
            // Only a lost key packet changes the model; lost non-key
            // packets left no trace on either end.
            if from.div_ceil(self.key) * self.key < index {
                self.desynced = true;
            }
            self.count = index;
        }
        if self.desynced {
            let epoch_start = self.epoch > 0 && index % self.epoch == 0;
            if !epoch_start {
                self.count = index + 1;
                return Err(Error::SessionOutOfSync {
                    expected: self.count,
                    got: index,
                });
            }
            // An epoch starts: back to the origin, in sync again.
            self.restart_at(index);
            self.desynced = false;
        }
        self.decompress(payload)
    }

    /// Decompress the next packet (no gap) and learn from it.
    pub fn decompress(&mut self, payload: &[u8]) -> Result<Vec<u8>, Error> {
        self.maybe_restart();
        self.learning = self.is_key(self.count);
        self.count += 1;
        let mut dec = Decoder::new(payload);
        self.left_changed = false;
        self.nchanged = 0;
        let mut io = Io::Dec(&mut dec);
        let mut out = Vec::with_capacity(self.len);
        let mut left = 0u8;
        for k in 0..self.len {
            let b = self.byte(k, left, 0, &mut io);
            out.push(b);
            left = b;
        }
        self.end_packet(&out);
        Ok(out)
    }
}
