//! # shannon-edge
//!
//! Lossless compression by prediction. A bitwise context-mixing model guesses
//! every next bit; an arithmetic coder spends `-log2(p)` bits on what actually
//! happens. The better the prediction, the closer the output gets to the
//! Shannon entropy of the data — and no lossless method can go below that.
//!
//! ```
//! let data = b"to be or not to be, that is the question".repeat(20);
//! let packed = shannon_edge::compress(&data, &shannon_edge::Options::default());
//! assert!(packed.len() < data.len() / 5);
//! assert_eq!(shannon_edge::decompress(&packed).unwrap(), data);
//! ```
//!
//! See `docs/FORMAT.md` for the container format and `docs/THEORY.md` for why
//! the limits are what they are.

pub mod coder;
mod crc32;
mod math;
mod model;

use coder::{Decoder, Encoder};
use model::Predictor;
use std::fmt;

/// Magic bytes at the start of every `.sedge` file.
pub const MAGIC: [u8; 4] = *b"SEDG";
/// Container format version written by this build.
pub const FORMAT_VERSION: u8 = 1;
/// Size of the fixed header in bytes.
pub const HEADER_LEN: usize = 20;

/// Smallest and largest supported memory levels (log2 slots per table).
pub const MIN_MEM_BITS: u8 = 16;
pub const MAX_MEM_BITS: u8 = 24;

const METHOD_STORED: u8 = 0;
const METHOD_CM: u8 = 1;

/// Compression options.
#[derive(Clone, Debug)]
pub struct Options {
    /// log2 of the number of slots in each hashed context table. Model
    /// memory is roughly `32 * 2^mem_bits` bytes plus ~9 MiB of fixed tables
    /// (≈140 MiB at the default 22, ≈480 MiB at 24), plus the input itself.
    /// Small inputs automatically use smaller tables. The decoder uses
    /// exactly the level recorded in the stream.
    pub mem_bits: u8,
}

impl Default for Options {
    fn default() -> Self {
        Self { mem_bits: 22 }
    }
}

/// Errors returned by [`decompress`].
#[derive(Debug, PartialEq, Eq)]
pub enum Error {
    /// Input is shorter than the header or the declared payload.
    Truncated,
    /// Input does not start with [`MAGIC`].
    BadMagic,
    /// Written by a newer, incompatible version.
    UnsupportedVersion(u8),
    /// Unknown compression method id.
    UnknownMethod(u8),
    /// Memory level outside the supported range.
    BadMemBits(u8),
    /// Declared size does not fit in memory on this platform.
    TooLarge(u64),
    /// Decoded data does not match the stored CRC-32: the file is corrupt.
    ChecksumMismatch { expected: u32, actual: u32 },
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Truncated => write!(f, "input is truncated"),
            Error::BadMagic => write!(f, "not a shannon-edge (.sedge) stream"),
            Error::UnsupportedVersion(v) => write!(f, "unsupported format version {v}"),
            Error::UnknownMethod(m) => write!(f, "unknown compression method {m}"),
            Error::BadMemBits(b) => write!(f, "invalid memory level {b}"),
            Error::TooLarge(n) => write!(f, "declared size {n} is too large"),
            Error::ChecksumMismatch { expected, actual } => write!(
                f,
                "checksum mismatch (expected {expected:08x}, got {actual:08x}): data is corrupt"
            ),
        }
    }
}

impl std::error::Error for Error {}

/// Pick the table size: no point allocating more slots than the input can
/// ever touch (8 bit-contexts per byte).
fn effective_mem_bits(len: usize, requested: u8) -> u8 {
    let requested = requested.clamp(MIN_MEM_BITS, MAX_MEM_BITS);
    let needed = (len.max(1) as u64 * 8).next_power_of_two().trailing_zeros() as u8;
    requested.min(needed.max(MIN_MEM_BITS))
}

fn header(method: u8, mem_bits: u8, len: u64, crc: u32) -> Vec<u8> {
    let mut h = Vec::with_capacity(HEADER_LEN);
    h.extend_from_slice(&MAGIC);
    h.push(FORMAT_VERSION);
    h.push(method);
    h.push(mem_bits);
    h.push(0); // reserved
    h.extend_from_slice(&len.to_le_bytes());
    h.extend_from_slice(&crc.to_le_bytes());
    debug_assert_eq!(h.len(), HEADER_LEN);
    h
}

/// Compress `data`. Never expands the input by more than [`HEADER_LEN`]
/// bytes: if modelling does not help (e.g. random or already-compressed
/// data), the input is stored verbatim.
///
/// # Panics
/// Inputs of 4 GiB or more are not supported by format version 1.
pub fn compress(data: &[u8], opts: &Options) -> Vec<u8> {
    assert!(
        (data.len() as u64) < u32::MAX as u64,
        "format v1 supports inputs below 4 GiB"
    );
    let crc = crc32::crc32(data);
    let bits = effective_mem_bits(data.len(), opts.mem_bits);

    if !data.is_empty() {
        let mut enc = Encoder::new(data.len() / 2 + 16);
        let mut pred = Predictor::new(bits as u32);
        pred.start();
        let limit = data.len();
        let mut gave_up = false;
        for (i, &byte) in data.iter().enumerate() {
            for k in (0..8).rev() {
                let bit = ((byte >> k) & 1) as u32;
                enc.encode(bit, pred.p());
                pred.update(bit);
            }
            pred.byte_update(&data[..=i]);
            if enc.bytes_written() >= limit {
                gave_up = true;
                break;
            }
        }
        if !gave_up {
            let payload = enc.finish();
            if payload.len() < data.len() {
                let mut out = header(METHOD_CM, bits, data.len() as u64, crc);
                out.extend_from_slice(&payload);
                return out;
            }
        }
    }

    let mut out = header(METHOD_STORED, 0, data.len() as u64, crc);
    out.extend_from_slice(data);
    out
}

/// Decompress a stream produced by [`compress`], verifying its CRC-32.
pub fn decompress(input: &[u8]) -> Result<Vec<u8>, Error> {
    if input.len() < HEADER_LEN {
        return Err(if input.len() >= 4 && input[..4] != MAGIC {
            Error::BadMagic
        } else {
            Error::Truncated
        });
    }
    if input[..4] != MAGIC {
        return Err(Error::BadMagic);
    }
    let version = input[4];
    if version != FORMAT_VERSION {
        return Err(Error::UnsupportedVersion(version));
    }
    let method = input[5];
    let bits = input[6];
    let len = u64::from_le_bytes(input[8..16].try_into().unwrap());
    let expected = u32::from_le_bytes(input[16..20].try_into().unwrap());
    let payload = &input[HEADER_LEN..];
    if len >= u32::MAX as u64 || len > usize::MAX as u64 {
        return Err(Error::TooLarge(len));
    }
    let len = len as usize;

    let out = match method {
        METHOD_STORED => {
            if payload.len() < len {
                return Err(Error::Truncated);
            }
            payload[..len].to_vec()
        }
        METHOD_CM => {
            if !(MIN_MEM_BITS..=MAX_MEM_BITS).contains(&bits) {
                return Err(Error::BadMemBits(bits));
            }
            // A CM payload is always shorter than the original, so a
            // plausible stream needs at least a little payload.
            if payload.is_empty() && len > 0 {
                return Err(Error::Truncated);
            }
            let mut out = Vec::with_capacity(len);
            let mut dec = Decoder::new(payload);
            let mut pred = Predictor::new(bits as u32);
            pred.start();
            while out.len() < len {
                loop {
                    let bit = dec.decode(pred.p());
                    if let Some(byte) = pred.update(bit) {
                        out.push(byte);
                        break;
                    }
                }
                pred.byte_update(&out);
            }
            out
        }
        m => return Err(Error::UnknownMethod(m)),
    };

    let actual = crc32::crc32(&out);
    if actual != expected {
        return Err(Error::ChecksumMismatch { expected, actual });
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mem_bits_shrink_for_small_inputs() {
        assert_eq!(effective_mem_bits(0, 22), 16);
        assert_eq!(effective_mem_bits(10_000, 22), 17);
        assert_eq!(effective_mem_bits(100_000_000, 22), 22);
        assert_eq!(effective_mem_bits(100_000_000, 30), 24);
    }
}
