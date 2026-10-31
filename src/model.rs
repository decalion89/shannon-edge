//! The predictor: a bitwise context-mixing model.
//!
//! For every bit of the input, several independent models each guess the
//! probability that the next bit is 1, each looking at a different "context"
//! (the previous byte, the previous few bytes, the current word, the longest
//! earlier repetition of what we just saw, ...). Small online neural networks
//! (the *mixers*) learn, while compressing, how much to trust each model in
//! each situation. Adaptive probability maps (SSE stages) then correct the
//! mixers' residual bias.
//!
//! Compression and decompression run this exact same code on the same history,
//! so they make identical predictions without ever transmitting the model.
//! Everything is integer arithmetic, so results are identical on every CPU.

use crate::math::{hash2, mix32, squash, stretch};

/// `RECIP[n] ≈ 65536 / (n + 1.5)`: adaptation rate after `n` observations.
static RECIP: [u32; 1024] = {
    let mut a = [0u32; 1024];
    let mut i = 0;
    while i < 1024 {
        a[i] = 131_072 / (2 * i as u32 + 3);
        i += 1;
    }
    a
};

/// Shared counter update for slots packing a 22-bit probability and a
/// 10-bit observation count. The learning rate decays as 1/n until it reaches
/// `1/limit`: precise on stationary data, still able to track drift.
#[inline]
fn update_slot(e: &mut u32, bit: u32, limit: u32) {
    let n = *e & 1023;
    let p = (*e >> 10) as i32;
    let target = if bit != 0 { (1 << 22) - 1 } else { 0 };
    let p = p + (((target - p) as i64 * RECIP[n as usize] as i64) >> 16) as i32;
    let n = if n < limit { n + 1 } else { n };
    *e = ((p as u32) << 10) | n;
}

#[inline]
fn slot_p(e: u32) -> i32 {
    ((e >> 20) as i32).clamp(1, 4095)
}

const FRESH: u32 = 1 << 31;

// ---------------------------------------------------------------------------
// Probability tables
// ---------------------------------------------------------------------------

/// Directly indexed adaptive probabilities.
struct DirectMap {
    t: Vec<u32>,
    limit: u32,
}

impl DirectMap {
    fn new(size: usize, limit: u32) -> Self {
        Self {
            t: vec![FRESH; size],
            limit,
        }
    }

    #[inline]
    fn p(&self, i: usize) -> i32 {
        slot_p(self.t[i])
    }

    #[inline]
    fn update(&mut self, i: usize, bit: u32) {
        update_slot(&mut self.t[i], bit, self.limit);
    }
}

/// One 64-byte cache line: a tag plus the 15 nodes of a binary tree over the
/// 4 bits of a nibble.
#[derive(Clone, Copy)]
#[repr(C, align(64))]
struct Bucket([u32; 16]);

/// Hashed adaptive probabilities, laid out so that coding one nibble of one
/// context touches a single cache line. A tag mismatch means the bucket
/// belongs to another context; it is then reset rather than letting two
/// contexts pollute each other's statistics.
struct HashedMap {
    t: Vec<Bucket>,
    shift: u32,
    limit: u32,
}

impl HashedMap {
    /// `bits` = log2 of the total number of slots (16 per bucket).
    fn new(bits: u32, limit: u32) -> Self {
        let mut b = Bucket([FRESH; 16]);
        b.0[0] = 0;
        Self {
            t: vec![b; 1usize << (bits - 4)],
            shift: 32 - (bits - 4),
            limit,
        }
    }

    /// Locate (and claim if needed) the bucket for hash `h`.
    #[inline]
    fn bucket(&mut self, h: u32) -> usize {
        let i = (h >> self.shift) as usize;
        let tag = (h & 0xffff) | 0x1_0000;
        let b = &mut self.t[i].0;
        if b[0] != tag {
            *b = [FRESH; 16];
            b[0] = tag;
        }
        i
    }

    #[inline]
    fn get(&self, b: usize, node: usize) -> u32 {
        self.t[b].0[node]
    }

    #[inline]
    fn update(&mut self, b: usize, node: usize, bit: u32) {
        update_slot(&mut self.t[b].0[node], bit, self.limit);
    }
}

// ---------------------------------------------------------------------------
// Mixers: online logistic regression (single-layer neural networks)
// ---------------------------------------------------------------------------

/// Inputs per mixer, padded to a multiple of 8 so the dot products vectorise.
const NI: usize = 24;

/// Weights are 16-bit fixed point with 1.0 = 8192, inputs are stretched
/// probabilities in -2047..=2047. Each `MixerBank` owns several weight sets
/// and selects one per bit from a small context.
struct MixerBank {
    w: Vec<[i16; NI]>,
    sel: usize,
    pr: i32,
    lr: i32,
}

impl MixerBank {
    fn new(sets: usize, lr: i32, init: i16) -> Self {
        Self {
            w: vec![[init; NI]; sets],
            sel: 0,
            pr: 2048,
            lr,
        }
    }

    /// Returns the stretched output for weight set `sel`.
    #[inline]
    fn mix(&mut self, x: &[i16; NI], sel: usize) -> i32 {
        self.sel = sel;
        let w = &self.w[sel];
        let mut dot = 0i32;
        for i in 0..NI {
            dot += x[i] as i32 * w[i] as i32;
        }
        let s = (dot >> 13).clamp(-2047, 2047);
        self.pr = squash(s);
        s
    }

    /// Gradient step on coding cost (cross-entropy).
    #[inline]
    fn update(&mut self, x: &[i16; NI], bit: u32) {
        let err = (((bit as i32) << 12) - self.pr) * self.lr;
        let w = &mut self.w[self.sel];
        for i in 0..NI {
            let d = (((x[i] as i32 * err) >> 15) + 1) >> 1;
            w[i] = (w[i] as i32 + d).clamp(-32768, 32767) as i16;
        }
    }
}

/// Final 2-layer combiner (few inputs, 32-bit weights, 1.0 = 65536).
struct FinalMixer {
    w: [i32; 3],
    x: [i32; 3],
    pr: i32,
}

impl FinalMixer {
    fn new() -> Self {
        Self {
            w: [65536 / 3; 3],
            x: [0; 3],
            pr: 2048,
        }
    }

    #[inline]
    fn mix(&mut self, x: [i32; 3]) -> i32 {
        self.x = x;
        let dot: i64 = (0..3).map(|i| x[i] as i64 * self.w[i] as i64).sum();
        let s = ((dot >> 16) as i32).clamp(-2047, 2047);
        self.pr = squash(s);
        s
    }

    #[inline]
    fn update(&mut self, bit: u32) {
        let err = (((bit as i32) << 12) - self.pr) * 2;
        for i in 0..3 {
            self.w[i] = (self.w[i] + ((self.x[i] * err) >> 14)).clamp(-(1 << 20), 1 << 20);
        }
    }
}

// ---------------------------------------------------------------------------
// APM / SSE: secondary estimation, refines a probability given a context
// ---------------------------------------------------------------------------

struct Apm {
    t: Vec<u16>,
    idx: usize,
    rate: i32,
}

impl Apm {
    fn new(contexts: usize, rate: i32) -> Self {
        let row: Vec<u16> = (0..33)
            .map(|j| (squash((j - 16) * 128) * 16) as u16)
            .collect();
        let mut t = Vec::with_capacity(contexts * 33);
        for _ in 0..contexts {
            t.extend_from_slice(&row);
        }
        Self { t, idx: 0, rate }
    }

    #[inline]
    fn pp(&mut self, pr: i32, cx: usize) -> i32 {
        let s = stretch(pr) + 2048;
        let lo = (s >> 7) as usize;
        let w = s & 127;
        let base = cx * 33 + lo;
        self.idx = base + ((w >> 6) as usize);
        let p = (self.t[base] as i32 * (128 - w) + self.t[base + 1] as i32 * w) >> 11;
        p.clamp(1, 4095)
    }

    #[inline]
    fn update(&mut self, bit: u32) {
        let g = ((bit as i32) << 16) + ((bit as i32) << self.rate) - 2 * bit as i32;
        let v = self.t[self.idx] as i32;
        self.t[self.idx] = (v + ((g - v) >> self.rate)) as u16;
    }
}

// ---------------------------------------------------------------------------
// Match model: predicts that history repeats itself
// ---------------------------------------------------------------------------

const MATCH_MIN: usize = 6;
const MATCH_MAX: usize = 65_535;

struct MatchModel {
    table: Vec<u32>,
    shift: u32,
    ptr: usize,
    len: usize,
    expected: u32,
    active: bool,
    sm: DirectMap,
    ctx: usize,
}

impl MatchModel {
    fn new(bits: u32) -> Self {
        Self {
            table: vec![0; 1usize << bits],
            shift: 32 - bits,
            ptr: 0,
            len: 0,
            expected: 0,
            active: false,
            sm: DirectMap::new(64, 1023),
            ctx: 0,
        }
    }

    /// Quantised match length, 0..=31.
    #[inline]
    fn len_bucket(&self) -> usize {
        match self.len {
            l if l < 16 => l,
            l => (16 + ((l - 16) >> 3)).min(31),
        }
    }

    /// Called once per byte with the complete history so far.
    fn byte_update(&mut self, hist: &[u8]) {
        let pos = hist.len();
        let last = hist[pos - 1];
        if self.len > 0 && self.ptr < pos && hist[self.ptr] == last {
            self.len = (self.len + 1).min(MATCH_MAX);
            self.ptr += 1;
        } else {
            self.len = 0;
        }
        if pos >= MATCH_MIN {
            let mut h: u32 = 0;
            for &b in &hist[pos - MATCH_MIN..pos] {
                h = (h ^ b as u32).wrapping_mul(0x0100_0193);
            }
            let slot = (mix32(h) >> self.shift) as usize;
            if self.len == 0 {
                let cand = self.table[slot] as usize;
                if cand > 0 && cand < pos {
                    let mut k = 0;
                    while k < 1024 && k < cand && hist[cand - 1 - k] == hist[pos - 1 - k] {
                        k += 1;
                    }
                    if k >= MATCH_MIN {
                        self.len = k;
                        self.ptr = cand;
                    }
                }
            }
            self.table[slot] = pos as u32;
        }
        self.active = self.len > 0 && self.ptr < pos;
        if self.active {
            self.expected = hist[self.ptr] as u32 | 0x100;
        }
    }

    /// Stretched prediction for the next bit, given the partial byte `c0`
    /// (leading 1 + `known` bits).
    #[inline]
    fn predict(&mut self, c0: u32, known: u32) -> i32 {
        if self.active && (self.expected >> (8 - known)) == c0 {
            let ebit = (self.expected >> (7 - known)) & 1;
            self.ctx = self.len_bucket() * 2 + ebit as usize;
            stretch(self.sm.p(self.ctx))
        } else {
            self.active = false;
            0
        }
    }

    #[inline]
    fn update(&mut self, bit: u32, known: u32) {
        if self.active {
            self.sm.update(self.ctx, bit);
            if (self.expected >> (7 - known)) & 1 != bit {
                self.active = false;
                self.len = 0;
            }
        }
    }
}

// ---------------------------------------------------------------------------
// The full predictor
// ---------------------------------------------------------------------------

/// Number of hashed context models.
const N_HASHED: usize = 7;

pub struct Predictor {
    o0: DirectMap,
    o1: DirectMap,
    hashed: Vec<HashedMap>,
    ctx: [u32; N_HASHED],
    buckets: [usize; N_HASHED],
    node: usize,
    mm: MatchModel,
    x: [i16; NI],
    m_byte: MixerBank,
    m_match: MixerBank,
    m_last: MixerBank,
    m_final: FinalMixer,
    a1: Apm,
    a2: Apm,
    a3: Apm,
    pr: i32,
    // history state
    c0: u32,
    known: u32,
    c4: u32,
    c8: u32,
    word: u32,
    prev_word: u32,
}

impl Predictor {
    /// `bits` is log2 of the slot count of each hashed table (16..=24).
    pub fn new(bits: u32) -> Self {
        let hashed = (0..N_HASHED).map(|_| HashedMap::new(bits, 40)).collect();
        let lr = 8;
        let init = 2048; // 0.25
        Self {
            o0: DirectMap::new(256, 1023),
            o1: DirectMap::new(1 << 16, 1023),
            hashed,
            ctx: [0; N_HASHED],
            buckets: [0; N_HASHED],
            node: 1,
            mm: MatchModel::new(bits.min(22)),
            x: [0; NI],
            m_byte: MixerBank::new(256, lr, init),
            m_match: MixerBank::new(32 * 4, lr, init),
            m_last: MixerBank::new(256, lr, init),
            m_final: FinalMixer::new(),
            a1: Apm::new(256, 7),
            a2: Apm::new(1 << 16, 7),
            a3: Apm::new(1 << 16, 7),
            pr: 2048,
            c0: 1,
            known: 0,
            c4: 0,
            c8: 0,
            word: 0,
            prev_word: 0,
        }
    }

    /// Probability (12-bit) that the next bit is 1.
    #[inline]
    pub fn p(&self) -> u32 {
        self.pr as u32
    }

    fn predict(&mut self) {
        let c0 = self.c0;
        let c1 = self.c4 & 0xff;
        let x = &mut self.x;

        x[0] = stretch(self.o0.p(c0 as usize)) as i16;
        x[1] = stretch(self.o1.p(((c1 << 8) | c0) as usize)) as i16;

        // A new nibble starts: find each context's cache line for it.
        if self.known == 0 || self.known == 4 {
            let salt = c0.wrapping_mul(0x2545_f491);
            for i in 0..N_HASHED {
                let h = mix32(self.ctx[i].wrapping_add(salt));
                self.buckets[i] = self.hashed[i].bucket(h);
            }
        }
        // Node of the nibble tree: 1, 1b, 1bb, 1bbb (1..=15).
        let k = self.known & 3;
        self.node = ((c0 & ((1 << k) - 1)) | (1 << k)) as usize;
        for i in 0..N_HASHED {
            let e = self.hashed[i].get(self.buckets[i], self.node);
            let st = stretch(slot_p(e));
            // Second input: the same opinion scaled by how often this exact
            // context has been seen, so the mixer can distrust fresh slots.
            let conf = match e & 1023 {
                0 => 0,
                1 => st / 4,
                2..=3 => st / 2,
                _ => st,
            };
            x[2 + 2 * i] = st as i16;
            x[3 + 2 * i] = conf as i16;
        }
        x[2 + 2 * N_HASHED] = self.mm.predict(c0, self.known) as i16;
        x[3 + 2 * N_HASHED] = 256; // bias

        let match_sel = self.mm.len_bucket() * 4 + (self.known as usize >> 1);
        let s1 = self.m_byte.mix(x, c0 as usize);
        let s2 = self.m_match.mix(x, match_sel);
        let s3 = self.m_last.mix(x, c1 as usize);
        let pr_mix = squash(self.m_final.mix([s1, s2, s3]));

        let pa1 = self.a1.pp(pr_mix, c0 as usize);
        let pa2 = self.a2.pp(pr_mix, ((c1 << 8) | c0) as usize);
        let h2 = mix32(self.c4 & 0xffff) >> 24;
        let pa3 = self.a3.pp(pr_mix, ((h2 << 8) | c0) as usize);
        let p = (2 * pr_mix + pa1 + 3 * pa2 + 2 * pa3 + 4) >> 3;
        self.pr = p.clamp(1, 4095);
    }

    /// Learn from the actual bit and prepare the next prediction.
    /// Returns `Some(byte)` when a byte has just been completed; the caller
    /// must then append it to the history and call [`Self::byte_update`].
    #[inline]
    pub fn update(&mut self, bit: u32) -> Option<u8> {
        let c0 = self.c0;
        let c1 = self.c4 & 0xff;
        self.o0.update(c0 as usize, bit);
        self.o1.update(((c1 << 8) | c0) as usize, bit);
        for i in 0..N_HASHED {
            self.hashed[i].update(self.buckets[i], self.node, bit);
        }
        self.mm.update(bit, self.known);
        self.m_byte.update(&self.x, bit);
        self.m_match.update(&self.x, bit);
        self.m_last.update(&self.x, bit);
        self.m_final.update(bit);
        self.a1.update(bit);
        self.a2.update(bit);
        self.a3.update(bit);

        self.c0 = (c0 << 1) | bit;
        self.known += 1;
        if self.known == 8 {
            let byte = (self.c0 & 0xff) as u8;
            self.c0 = 1;
            self.known = 0;
            Some(byte)
        } else {
            self.predict();
            None
        }
    }

    /// Recompute the per-byte contexts. `hist` is the full history including
    /// the byte just completed.
    pub fn byte_update(&mut self, hist: &[u8]) {
        let b = *hist.last().expect("history is non-empty");
        self.c8 = (self.c8 << 8) | (self.c4 >> 24);
        self.c4 = (self.c4 << 8) | b as u32;

        if b.is_ascii_alphabetic() || b >= 128 {
            self.word = hash2(self.word, b.to_ascii_lowercase() as u32);
        } else if self.word != 0 {
            self.prev_word = self.word;
            self.word = 0;
        }

        let c4 = self.c4;
        self.ctx = [
            hash2(1, c4 & 0xffff),
            hash2(2, c4 & 0x00ff_ffff),
            hash2(3, c4),
            hash2(hash2(4, c4), self.c8 & 0xffff),
            hash2(
                hash2(5, self.word),
                if self.word == 0 { c4 & 0xff } else { 0 },
            ),
            hash2(hash2(6, self.word), self.prev_word),
            hash2(7, (c4 >> 8) & 0xffff),
        ];
        self.mm.byte_update(hist);
        self.predict();
    }

    /// Prime the first prediction (before any byte has been seen).
    pub fn start(&mut self) {
        for (i, c) in self.ctx.iter_mut().enumerate() {
            *c = hash2(i as u32 + 1, 0);
        }
        self.predict();
    }
}
