//! Binary arithmetic coder (32-bit, carry-less).
//!
//! Each call codes one bit with probability `p1 = P(bit = 1)` given as a
//! 12-bit integer. The cost of coding a bit is `-log2(P(bit))`, so the better
//! the model predicts, the fewer bits are written — this is where the Shannon
//! limit becomes concrete.

/// Encodes bits into a byte vector.
pub struct Encoder {
    x1: u32,
    x2: u32,
    out: Vec<u8>,
}

impl Encoder {
    pub fn new(capacity: usize) -> Self {
        Self {
            x1: 0,
            x2: u32::MAX,
            out: Vec::with_capacity(capacity),
        }
    }

    /// Encode `bit` (0 or 1) with 12-bit probability `p1` that it is 1.
    #[inline]
    pub fn encode(&mut self, bit: u32, p1: u32) {
        debug_assert!((1..4096).contains(&p1));
        let xmid = self.x1 + ((self.x2 - self.x1) >> 12) * p1;
        if bit != 0 {
            self.x2 = xmid;
        } else {
            self.x1 = xmid + 1;
        }
        while (self.x1 ^ self.x2) & 0xff00_0000 == 0 {
            self.out.push((self.x2 >> 24) as u8);
            self.x1 <<= 8;
            self.x2 = (self.x2 << 8) | 0xff;
        }
    }

    /// Encode a symbol occupying `[cum, cum + freq)` of `total` (multi-symbol
    /// coding on the same interval; `total` at most 2^16). Returns `false`,
    /// coding nothing, if the current interval is narrower than `total`:
    /// both ends see the same interval, so the caller then codes the symbol
    /// another way (e.g. bit by bit).
    #[inline]
    pub fn encode_freq(&mut self, cum: u32, freq: u32, total: u32) -> bool {
        // One 32-bit division per symbol (hardware on 32-bit flight CPUs);
        // the top `range mod total` values of the interval go unused.
        let r = (self.x2 - self.x1) / total;
        if r == 0 {
            return false;
        }
        self.x1 += r * cum;
        self.x2 = self.x1 + r * freq - 1;
        while (self.x1 ^ self.x2) & 0xff00_0000 == 0 {
            self.out.push((self.x2 >> 24) as u8);
            self.x1 <<= 8;
            self.x2 = (self.x2 << 8) | 0xff;
        }
        true
    }

    /// Flush the final state and return the encoded bytes.
    pub fn finish(mut self) -> Vec<u8> {
        // Any value in [x1, x2] identifies the stream; emit x1 in full.
        self.out.extend_from_slice(&self.x1.to_be_bytes());
        self.out
    }

    /// Flush with as few bytes as possible: the shortest byte string that,
    /// padded with zeros (as [`Decoder`] does), still lies in `[x1, x2]`.
    /// Saves 2-3 bytes per stream, which matters for tiny messages.
    pub fn finish_short(mut self) -> Vec<u8> {
        for k in 1..=4u32 {
            let shift = 32 - 8 * k;
            let unit: u64 = 1 << shift;
            // Round x1 up to the next multiple of 2^shift.
            let v = (self.x1 as u64).div_ceil(unit) * unit;
            if v <= self.x2 as u64 {
                let v = v as u32;
                for i in 0..k {
                    self.out.push((v >> (24 - 8 * i)) as u8);
                }
                break;
            }
        }
        // Trailing zero bytes are implied by the decoder's zero padding. At
        // most MAX_IMPLIED_ZEROS are dropped, so a decoder can tell a valid
        // stream (it reads at most MAX_OVERRUN bytes past the end) from
        // garbage that keeps it decoding past the data it was given.
        for _ in 0..MAX_IMPLIED_ZEROS {
            if self.out.last() != Some(&0) {
                break;
            }
            self.out.pop();
        }
        self.out
    }

    /// Bytes written so far (used to abandon hopeless inputs early).
    #[inline]
    pub fn bytes_written(&self) -> usize {
        self.out.len()
    }
}

/// Most trailing zero bytes [`Encoder::finish_short`] drops.
pub const MAX_IMPLIED_ZEROS: usize = 4;

/// Most bytes a [`Decoder`] reads past the end of a valid stream: its 4-byte
/// look-ahead, minus the at least 1 flush byte, plus the implied zeros.
/// Reading further proves the stream is truncated or corrupt.
pub const MAX_OVERRUN: usize = 3 + MAX_IMPLIED_ZEROS;

/// Decodes bits from a byte slice. Reads past the end as zeros, so a
/// truncated or corrupted stream never panics; it just decodes garbage that
/// the container checksum then rejects.
pub struct Decoder<'a> {
    x1: u32,
    x2: u32,
    x: u32,
    input: &'a [u8],
    pos: usize,
}

impl<'a> Decoder<'a> {
    pub fn new(input: &'a [u8]) -> Self {
        let mut d = Self {
            x1: 0,
            x2: u32::MAX,
            x: 0,
            input,
            pos: 0,
        };
        for _ in 0..4 {
            d.x = (d.x << 8) | d.next_byte();
        }
        d
    }

    /// Bytes read past the end of the input (as implied zeros) so far.
    #[inline]
    pub fn overrun(&self) -> usize {
        self.pos.saturating_sub(self.input.len())
    }

    #[inline]
    fn next_byte(&mut self) -> u32 {
        let b = self.input.get(self.pos).copied().unwrap_or(0);
        self.pos += 1;
        b as u32
    }

    /// Multi-symbol decoding, step 1: the cumulative count the next symbol
    /// covers (`cum <= v < cum + freq`), or `None` if the interval is
    /// narrower than `total` (see [`Encoder::encode_freq`]).
    #[inline]
    pub fn decode_target(&self, total: u32) -> Option<u32> {
        let r = (self.x2 - self.x1) / total;
        if r == 0 {
            return None;
        }
        Some((self.x.wrapping_sub(self.x1) / r).min(total - 1))
    }

    /// Multi-symbol decoding, step 2: consume the symbol found for the
    /// target (same arguments as the encoder's `encode_freq`).
    #[inline]
    pub fn decode_freq(&mut self, cum: u32, freq: u32, total: u32) {
        let r = (self.x2 - self.x1) / total;
        self.x1 += r * cum;
        self.x2 = self.x1 + r * freq - 1;
        while (self.x1 ^ self.x2) & 0xff00_0000 == 0 {
            self.x1 <<= 8;
            self.x2 = (self.x2 << 8) | 0xff;
            self.x = (self.x << 8) | self.next_byte();
        }
    }

    /// Decode one bit given the same 12-bit probability the encoder used.
    #[inline]
    pub fn decode(&mut self, p1: u32) -> u32 {
        let xmid = self.x1 + ((self.x2 - self.x1) >> 12) * p1;
        let bit = if self.x <= xmid {
            self.x2 = xmid;
            1
        } else {
            self.x1 = xmid + 1;
            0
        };
        while (self.x1 ^ self.x2) & 0xff00_0000 == 0 {
            self.x1 <<= 8;
            self.x2 = (self.x2 << 8) | 0xff;
            self.x = (self.x << 8) | self.next_byte();
        }
        bit
    }
}
