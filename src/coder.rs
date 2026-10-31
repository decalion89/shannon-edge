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
        // Trailing zero bytes are implied by the decoder's zero padding.
        while self.out.last() == Some(&0) {
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

    #[inline]
    fn next_byte(&mut self) -> u32 {
        let b = self.input.get(self.pos).copied().unwrap_or(0);
        self.pos += 1;
        b as u32
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
