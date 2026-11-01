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
}

/// One end of a link carrying fixed-length packets. Both ends must use the
/// same `packet_len` and `table_bits` and process the same packets in order.
pub struct PacketSession {
    len: usize,
    above: Vec<u8>,
    cols: Vec<Column>,
    t: [Table; 4],
    res: Table,
    /// Mixer weights per bit depth (1.0 = 65536): 4 inputs + bias.
    w: [[i32; 5]; 8],
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
        }
    }

    /// Packet length this session was created with.
    pub fn packet_len(&self) -> usize {
        self.len
    }

    /// Transition model for byte `k` with left neighbour `left`.
    fn transition(&mut self, k: usize, left: u8, value: u32, io: &mut Io) -> (u32, u32) {
        let above = self.above[k] as u64;
        let above2 = self.cols[k].above2 as u64;
        let col = k as u64 + 1;
        let mut node = 1u32;
        let mut total = 0;
        for i in (0..8).rev() {
            let n = node as u64;
            let s = [
                self.t[0].slot(h2(col, n)),
                self.t[1].slot(h2(h2(col, above + 1), n)),
                self.t[2].slot(h2(h2(h2(col, above + 1), above2 + 7), n)),
                self.t[3].slot(h2(h2(h2(col, above + 1), left as u64 + 3), n)),
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
            let p = squash(((dot >> 16) as i32).clamp(-2047, 2047)).clamp(1, 4095) as u32;
            let bit = io.bit(p, (value >> i) & 1);
            total += cost(p, bit);
            let err = ((bit as i32) << 12) - p as i32;
            for (wk, xk) in w.iter_mut().zip(x) {
                *wk += (xk * err) >> 10;
            }
            for (t, &sk) in self.t.iter_mut().zip(&s) {
                t.t[sk].update(bit);
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
            let c = &mut self.res.t[s];
            let p = c.p12();
            let bit = io.bit(p, (len < n) as u32);
            total += cost(p, bit);
            c.update(bit);
            if bit == 0 || len >= 8 {
                break;
            }
            len += 1;
        }
        let mut v: u32 = (len != 0) as u32;
        for i in (0..len.saturating_sub(1)).rev() {
            let s = self.res.slot(h2(h2(col, len as u64 * 64 + v as u64), 2));
            let c = &mut self.res.t[s];
            let p = c.p12();
            let bit = io.bit(p, (z >> i) & 1);
            total += cost(p, bit);
            c.update(bit);
            v = (v << 1) | bit;
        }
        let r = ((v >> 1) as i32) ^ -((v & 1) as i32);
        let out = above.wrapping_add(r as i8 as u8) as u32;
        self.cols[k].last_len = len as u8;
        (out, total)
    }

    fn byte(&mut self, k: usize, left: u8, value: u32, io: &mut Io) -> u8 {
        let c = self.cols[k];
        let use_t = c.cost_t <= c.cost_r;
        let (v, ct, cr) = if use_t {
            let (v, ct) = self.transition(k, left, value, io);
            let (_, cr) = self.residual(k, v, &mut Io::Dry);
            (v, ct, cr)
        } else {
            let (v, cr) = self.residual(k, value, io);
            let (_, ct) = self.transition(k, left, v, &mut Io::Dry);
            (v, ct, cr)
        };
        let c = &mut self.cols[k];
        c.cost_t = c.cost_t - (c.cost_t >> 4) + ct;
        c.cost_r = c.cost_r - (c.cost_r >> 4) + cr;
        v as u8
    }

    fn end_packet(&mut self, packet: &[u8]) {
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
        let mut enc = Encoder::new(self.len);
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

    /// Decompress one packet and learn from it.
    pub fn decompress(&mut self, payload: &[u8]) -> Result<Vec<u8>, Error> {
        let mut dec = Decoder::new(payload);
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
