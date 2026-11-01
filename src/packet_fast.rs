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
    /// Number of symbols: 255 (deltas 1..=255) or 256 (deltas 0..=255).
    syms: u16,
    f: [u16; 256],
    /// Fenwick tree; partial sums never exceed `LIMIT`, so 16 bits suffice.
    tree: [u16; 257],
    total: u32,
}

impl Freq {
    fn new(syms: usize) -> Self {
        let mut s = Self {
            syms: syms as u16,
            f: [0; 256],
            tree: [0; 257],
            total: 0,
        };
        for f in &mut s.f[..syms] {
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
                self.tree[j] += self.f[i];
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
            c += self.tree[j] as u32;
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
            if next <= 256 && (self.tree[next] as u32) <= v {
                pos = next;
                v -= self.tree[next] as u32;
                cum += self.tree[next] as u32;
            }
            mask >>= 1;
        }
        (pos.min(self.syms as usize - 1), cum)
    }

    #[inline]
    fn update(&mut self, s: usize) {
        if self.total + INC > LIMIT {
            for f in &mut self.f[..self.syms as usize] {
                *f = (*f >> 1).max(1);
            }
            self.rebuild();
        }
        self.f[s] += INC as u16;
        self.total += INC;
        let mut j = s + 1;
        while j <= 256 {
            self.tree[j] += INC as u16;
            j += j & j.wrapping_neg();
        }
    }
}

/// Code one symbol with an adaptive frequency table: `sym` is the symbol
/// when encoding (`None` when decoding). Returns the symbol and updates the
/// table.
#[inline]
fn code_symbol(f: &mut Freq, sym: Option<usize>, io: &mut Io) -> usize {
    let s = match io {
        Io::Enc(e) => {
            let s = sym.expect("encoder knows the symbol");
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
                s.min(f.syms as usize - 1)
            }
        },
    };
    f.update(s);
    s
}

/// Per-column state.
#[derive(Clone, Copy, Default)]
struct Column {
    /// Packets since the column last changed (capped at 15).
    run: u8,
    changed_last: bool,
    /// Delta of the column's last change (0 before the first).
    last_delta: u8,
    /// Context recipe and the index of its first frequency table.
    recipe: u8,
    base: u32,
    /// Coding class (see [`class`]).
    class: u8,
}

/// Column coding classes, chosen by the ground from the history
/// ([`FastPacketSession::learn_classes`]) like the recipes: they decide how
/// much work each byte costs, not only how many bits.
pub mod class {
    /// "Same as above?" decision, then the delta if it changed (default).
    pub const NORMAL: u8 = 0;
    /// Rarely changes: all static columns share one "any changed?" decision
    /// per packet and cost nothing else when none changed.
    pub const STATIC: u8 = 1;
    /// Nearly always changes: the delta is coded directly, 0 included, with
    /// no separate decision.
    pub const ALWAYS: u8 = 2;
    /// Number of classes.
    pub const COUNT: u8 = 3;
}

/// Context recipes for a column's delta tables. The ground, which holds the
/// history, can choose one per column ([`FastPacketSession::learn_recipes`])
/// and uplink the choice (one byte per column); the encoder only follows it.
pub mod recipe {
    /// Did the left neighbour change in this packet? (2 tables; default)
    pub const LEFT_CHANGED: u8 = 0;
    /// Size and sign of the left neighbour's delta (10 tables).
    pub const LEFT_DELTA: u8 = 1;
    /// Size and sign of this column's last delta (10 tables).
    pub const LAST_DELTA: u8 = 2;
    /// High nibble of the byte above (16 tables).
    pub const ABOVE_HIGH: u8 = 3;
    /// Left neighbour changed × last delta (20 tables).
    pub const LEFT_CHANGED_LAST_DELTA: u8 = 4;
    /// Number of recipes.
    pub const COUNT: u8 = 5;

    pub(crate) fn tables(r: u8) -> usize {
        [2, 10, 10, 16, 20][r as usize]
    }
}

/// Size and sign class of a delta: 0 (none), 1, 2..3, 4..15, 16+; x2 sign.
#[inline]
fn delta_class(d: u8) -> usize {
    let s = d as i8;
    let a = s.unsigned_abs();
    let b = match a {
        0 => 0,
        1 => 1,
        2..=3 => 2,
        4..=15 => 3,
        _ => 4,
    };
    b * 2 + (s < 0) as usize
}

#[inline]
fn recipe_context(r: u8, left_changed: bool, left_delta: u8, last_delta: u8, above: u8) -> usize {
    match r {
        recipe::LEFT_CHANGED => left_changed as usize,
        recipe::LEFT_DELTA => delta_class(left_delta),
        recipe::LAST_DELTA => delta_class(last_delta),
        recipe::ABOVE_HIGH => (above >> 4) as usize,
        _ => left_changed as usize * 10 + delta_class(last_delta),
    }
}

/// One end of a link carrying fixed-length packets (fast profile).
#[derive(Clone)]
pub struct FastPacketSession {
    len: usize,
    above: Vec<u8>,
    cols: Vec<Column>,
    /// "Same" probabilities (16-bit), 64 contexts per column.
    same: Vec<u16>,
    /// Delta frequencies: per column, the tables of its recipe.
    freq: Vec<Freq>,
    /// Epoch length in packets (0 = none) and the state to restart from.
    epoch: u64,
    origin: Option<Box<FastPacketSession>>,
    /// Packets processed (both ends) and, receiver only, lost sync.
    count: u64,
    desynced: bool,
    /// Whether any column is static; the group decision's probabilities
    /// (by whether the group changed in the previous packet).
    has_static: bool,
    group: [u16; 2],
    group_last: bool,
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
        Self::with_recipes(&vec![recipe::LEFT_CHANGED; packet_len])
    }

    /// A session whose column `k` uses context recipe `recipes[k]` (see
    /// [`recipe`]); the packet length is `recipes.len()`. Both ends must use
    /// the same recipes.
    ///
    /// # Panics
    /// If the length is out of range or a recipe is unknown.
    pub fn with_recipes(recipes: &[u8]) -> Self {
        Self::with_layout(recipes, &vec![class::NORMAL; recipes.len()])
    }

    /// A session with a context recipe ([`recipe`]) and a coding class
    /// ([`class`]) per column; the packet length is `recipes.len()`. Both
    /// ends must use the same layout.
    ///
    /// # Panics
    /// If the length is out of range, the slices differ in length, or a
    /// recipe or class is unknown.
    pub fn with_layout(recipes: &[u8], classes: &[u8]) -> Self {
        let packet_len = recipes.len();
        assert!((1..=65536).contains(&packet_len), "packet_len in 1..=65536");
        assert_eq!(classes.len(), packet_len, "one class per column");
        assert!(recipes.iter().all(|&r| r < recipe::COUNT), "unknown recipe");
        assert!(classes.iter().all(|&c| c < class::COUNT), "unknown class");
        let mut cols = vec![Column::default(); packet_len];
        let mut freq = Vec::new();
        for ((c, &r), &cl) in cols.iter_mut().zip(recipes).zip(classes) {
            c.recipe = r;
            c.class = cl;
            c.base = freq.len() as u32;
            let syms = if cl == class::ALWAYS { 256 } else { SYMS };
            freq.extend((0..recipe::tables(r)).map(|_| Freq::new(syms)));
        }
        Self {
            len: packet_len,
            above: vec![0; packet_len],
            cols,
            same: vec![1 << 15; packet_len * 64],
            freq,
            epoch: 0,
            origin: None,
            count: 0,
            desynced: false,
            has_static: classes.contains(&class::STATIC),
            group: [1 << 15; 2],
            group_last: false,
        }
    }

    /// Ground side: choose each column's coding class from historical
    /// packets by how often it changed: below 1 in `1 / static_max`
    /// packets → [`class::STATIC`], above `always_min` →
    /// [`class::ALWAYS`]. Typical: `learn_classes(len, history, 0.01, 0.9)`.
    ///
    /// # Panics
    /// If a packet has another length.
    pub fn learn_classes(
        packet_len: usize,
        history: &[&[u8]],
        static_max: f64,
        always_min: f64,
    ) -> Vec<u8> {
        let mut changes = vec![0usize; packet_len];
        for w in history.windows(2) {
            assert!(
                w[0].len() == packet_len && w[1].len() == packet_len,
                "packet length"
            );
            for (k, c) in changes.iter_mut().enumerate() {
                *c += (w[0][k] != w[1][k]) as usize;
            }
        }
        let n = history.len().saturating_sub(1).max(1) as f64;
        changes
            .iter()
            .map(|&c| {
                let r = c as f64 / n;
                if r < static_max {
                    class::STATIC
                } else if r > always_min {
                    class::ALWAYS
                } else {
                    class::NORMAL
                }
            })
            .collect()
    }

    /// Ground side: choose each column's context recipe from historical
    /// packets, by the ideal cost of its changed bytes under every recipe.
    /// The result (one byte per column) is what both ends pass to
    /// [`FastPacketSession::with_recipes`].
    ///
    /// # Panics
    /// If `packet_len` is out of range or a packet has another length.
    pub fn learn_recipes(packet_len: usize, history: &[&[u8]]) -> Vec<u8> {
        assert!((1..=65536).contains(&packet_len), "packet_len in 1..=65536");
        let mut cost = vec![[0f64; recipe::COUNT as usize]; packet_len];
        for r in 0..recipe::COUNT {
            let n = recipe::tables(r);
            let mut freq = vec![Freq::new(SYMS); packet_len * n];
            let mut above = vec![0u8; packet_len];
            let mut last = vec![0u8; packet_len];
            for p in history {
                assert_eq!(p.len(), packet_len, "packet length");
                let (mut lc, mut ld) = (false, 0u8);
                for k in 0..packet_len {
                    let d = p[k].wrapping_sub(above[k]);
                    if d == 0 {
                        lc = false;
                        ld = 0;
                        continue;
                    }
                    let f = &mut freq[k * n + recipe_context(r, lc, ld, last[k], above[k])];
                    let s = d as usize - 1;
                    cost[k][r as usize] += (f.total as f64 / f.f[s] as f64).log2();
                    f.update(s);
                    lc = true;
                    ld = d;
                    last[k] = d;
                }
                above.copy_from_slice(p);
            }
        }
        cost.iter()
            .map(|c| {
                (0..recipe::COUNT)
                    .min_by(|&a, &b| c[a as usize].total_cmp(&c[b as usize]))
                    .unwrap_or(0)
            })
            .collect()
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
        // 0. Did any static column change? One decision for all of them.
        let mut group_changed = true;
        if self.has_static {
            let g = self.group_last as usize;
            let p16 = self.group[g] as u32;
            let p1 = (p16 >> 4).clamp(1, 4095);
            let bit = match io {
                Io::Enc(e) => {
                    let changed = (0..self.len)
                        .any(|k| self.cols[k].class == class::STATIC && packet[k] != self.above[k]);
                    e.encode(changed as u32, p1);
                    changed as u32
                }
                Io::Dec(d) => d.decode(p1),
            };
            let target = (bit << 16) as i32;
            self.group[g] = (p16 as i32 + ((target - p16 as i32) >> 4)).clamp(0, 65535) as u16;
            group_changed = bit == 1;
            self.group_last = group_changed;
        }
        let mut left_changed = false;
        let mut left_delta = 0u8;
        for k in 0..self.len {
            let above = self.above[k];
            let c = self.cols[k];
            if c.class == class::STATIC && !group_changed {
                left_changed = false;
                left_delta = 0;
                out.push(above);
                continue;
            }
            if c.class == class::ALWAYS {
                // The delta directly, 0 included.
                let cx = recipe_context(c.recipe, left_changed, left_delta, c.last_delta, above);
                let f = &mut self.freq[c.base as usize + cx];
                let d = code_symbol(
                    f,
                    packet.get(k).map(|&b| b.wrapping_sub(above) as usize),
                    io,
                ) as u8;
                left_changed = d != 0;
                left_delta = d;
                if d != 0 {
                    self.cols[k].last_delta = d;
                }
                out.push(above.wrapping_add(d));
                continue;
            }
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
                left_delta = 0;
                above
            } else {
                col.run = 0;
                col.changed_last = true;
                // 2. The delta from above, one symbol.
                let cx =
                    recipe_context(col.recipe, left_changed, left_delta, col.last_delta, above);
                let f = &mut self.freq[col.base as usize + cx];
                let s = code_symbol(
                    f,
                    packet.get(k).map(|&b| b.wrapping_sub(above) as usize - 1),
                    io,
                );
                left_changed = true;
                left_delta = s as u8 + 1;
                col.last_delta = left_delta;
                above.wrapping_add(left_delta)
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
