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
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

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
const METHOD_BLOCKS: u8 = 2;
const METHOD_CM_DICT: u8 = 3;

/// Default block size for parallel compression.
pub const DEFAULT_BLOCK_SIZE: usize = 8 << 20;

/// Compression options.
#[derive(Clone, Debug)]
pub struct Options {
    /// log2 of the number of slots in each hashed context table. Model
    /// memory is roughly `32 * 2^mem_bits` bytes plus ~9 MiB of fixed tables
    /// (≈140 MiB at the default 22, ≈480 MiB at 24), plus the input itself.
    /// Small inputs automatically use smaller tables. The decoder uses
    /// exactly the level recorded in the stream.
    pub mem_bits: u8,
    /// Inputs larger than this are split into independent blocks that are
    /// compressed and decompressed in parallel. Smaller blocks = more
    /// parallelism but a slightly worse ratio (each block starts with an
    /// empty model). `0` disables splitting. The compressed bytes depend on
    /// this value, never on the number of threads.
    pub block_size: usize,
    /// Worker threads (`0` = all available cores). Each thread holds its own
    /// model, so peak memory grows with the thread count.
    pub threads: usize,
}

impl Default for Options {
    fn default() -> Self {
        Self {
            mem_bits: 22,
            block_size: DEFAULT_BLOCK_SIZE,
            threads: 0,
        }
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
    /// The block table of a multi-block stream is inconsistent.
    BadBlockTable,
    /// The stream was compressed with a dictionary; pass the same one to
    /// [`decompress_with_dictionary`].
    DictionaryRequired { crc: u32, len: usize },
    /// The dictionary given is not the one the stream was compressed with.
    DictionaryMismatch { crc: u32, len: usize },
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
            Error::BadBlockTable => write!(f, "inconsistent block table: data is corrupt"),
            Error::DictionaryRequired { crc, len } => write!(
                f,
                "compressed with a dictionary ({len} bytes, crc {crc:08x}); pass it with -D"
            ),
            Error::DictionaryMismatch { crc, len } => write!(
                f,
                "wrong dictionary: stream needs {len} bytes with crc {crc:08x}"
            ),
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

/// Run `f` over `items` on up to `threads` worker threads, keeping order.
fn parallel_map<T: Sync, R: Send>(
    items: &[T],
    threads: usize,
    f: impl Fn(&T) -> R + Sync,
) -> Vec<R> {
    let threads = match threads {
        0 => std::thread::available_parallelism().map_or(1, |n| n.get()),
        n => n,
    }
    .min(items.len())
    .max(1);
    if threads == 1 {
        return items.iter().map(f).collect();
    }
    let next = AtomicUsize::new(0);
    let results: Vec<Mutex<Option<R>>> = items.iter().map(|_| Mutex::new(None)).collect();
    std::thread::scope(|scope| {
        for _ in 0..threads {
            scope.spawn(|| loop {
                let i = next.fetch_add(1, Ordering::Relaxed);
                if i >= items.len() {
                    break;
                }
                let r = f(&items[i]);
                *results[i].lock().unwrap() = Some(r);
            });
        }
    });
    results
        .into_iter()
        .map(|m| m.into_inner().unwrap().expect("every item was processed"))
        .collect()
}

/// Compress `data`. Never expands the input by more than [`HEADER_LEN`]
/// bytes: if modelling does not help (e.g. random or already-compressed
/// data), the input is stored verbatim.
///
/// Inputs larger than [`Options::block_size`] are split into independent
/// blocks compressed on [`Options::threads`] threads. The output depends
/// only on the data, `mem_bits` and `block_size` — never on the thread count.
///
/// # Panics
/// Inputs of 4 GiB or more are not supported by format version 1.
pub fn compress(data: &[u8], opts: &Options) -> Vec<u8> {
    compress_with_dictionary(data, &[], opts)
}

/// Compress `data` given a dictionary: data that the decompressor will also
/// have. Before coding, the model reads the dictionary (in every block), so
/// it starts out already knowing its vocabulary, phrases and structure. The
/// cost of a message then approaches `H(data | dictionary)`, which for small
/// messages similar to the dictionary is far below `H(data)`.
///
/// Decompression requires exactly the same dictionary
/// ([`decompress_with_dictionary`]); the stream records its CRC-32 and
/// length. Priming costs time proportional to the dictionary size, per block.
/// An empty dictionary is the same as [`compress`].
///
/// # Panics
/// If `dictionary` plus one block reaches 4 GiB.
pub fn compress_with_dictionary(data: &[u8], dictionary: &[u8], opts: &Options) -> Vec<u8> {
    assert!(
        (data.len() as u64) < u32::MAX as u64,
        "format v1 supports inputs below 4 GiB"
    );
    if opts.block_size == 0 || data.len() <= opts.block_size {
        return compress_single(data, opts.mem_bits, dictionary);
    }

    let blocks: Vec<&[u8]> = data.chunks(opts.block_size).collect();
    let streams = parallel_map(&blocks, opts.threads, |b| {
        compress_single(b, opts.mem_bits, dictionary)
    });

    let total: usize = streams.iter().map(Vec::len).sum();
    let table_len = 8 + 4 * streams.len();
    if total + table_len >= data.len() {
        return stored(data);
    }
    let mut out = header(METHOD_BLOCKS, 0, data.len() as u64, crc32::crc32(data));
    out.extend_from_slice(&(opts.block_size as u32).to_le_bytes());
    out.extend_from_slice(&(streams.len() as u32).to_le_bytes());
    for st in &streams {
        out.extend_from_slice(&(st.len() as u32).to_le_bytes());
    }
    for st in &streams {
        out.extend_from_slice(st);
    }
    out
}

fn stored(data: &[u8]) -> Vec<u8> {
    let mut out = header(METHOD_STORED, 0, data.len() as u64, crc32::crc32(data));
    out.extend_from_slice(data);
    out
}

/// Feed `dict` through the model without coding anything, leaving `hist`
/// holding it. Encoder and decoder run this identically.
fn prime(pred: &mut Predictor, hist: &mut Vec<u8>, dict: &[u8]) {
    for &byte in dict {
        for k in (0..8).rev() {
            pred.update(((byte >> k) & 1) as u32);
        }
        hist.push(byte);
        pred.byte_update(hist);
    }
}

/// Compress one block as a self-contained stored, CM or CM+dictionary stream.
fn compress_single(data: &[u8], mem_bits: u8, dict: &[u8]) -> Vec<u8> {
    assert!(
        ((dict.len() + data.len()) as u64) < u32::MAX as u64,
        "dictionary plus block must stay below 4 GiB"
    );
    let bits = effective_mem_bits(dict.len() + data.len(), mem_bits);
    if !data.is_empty() {
        let mut enc = Encoder::new(data.len() / 2 + 16);
        let mut pred = Predictor::new(bits as u32);
        pred.start();
        let mut hist = Vec::with_capacity(dict.len() + data.len());
        prime(&mut pred, &mut hist, dict);
        let limit = data.len();
        let mut gave_up = false;
        for &byte in data {
            for k in (0..8).rev() {
                let bit = ((byte >> k) & 1) as u32;
                enc.encode(bit, pred.p());
                pred.update(bit);
            }
            hist.push(byte);
            pred.byte_update(&hist);
            if enc.bytes_written() >= limit {
                gave_up = true;
                break;
            }
        }
        if !gave_up {
            let payload = enc.finish();
            let dict_tag = if dict.is_empty() { 0 } else { 8 };
            if payload.len() + dict_tag < data.len() {
                let crc = crc32::crc32(data);
                let mut out = if dict.is_empty() {
                    header(METHOD_CM, bits, data.len() as u64, crc)
                } else {
                    let mut h = header(METHOD_CM_DICT, bits, data.len() as u64, crc);
                    h.extend_from_slice(&crc32::crc32(dict).to_le_bytes());
                    h.extend_from_slice(&(dict.len() as u32).to_le_bytes());
                    h
                };
                out.extend_from_slice(&payload);
                return out;
            }
        }
    }
    stored(data)
}

struct Header {
    method: u8,
    bits: u8,
    len: usize,
    crc: u32,
}

fn parse_header(input: &[u8]) -> Result<Header, Error> {
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
    let len = u64::from_le_bytes(input[8..16].try_into().unwrap());
    if len >= u32::MAX as u64 || len > usize::MAX as u64 {
        return Err(Error::TooLarge(len));
    }
    Ok(Header {
        method: input[5],
        bits: input[6],
        len: len as usize,
        crc: u32::from_le_bytes(input[16..20].try_into().unwrap()),
    })
}

fn read_u32(b: &[u8], at: usize) -> Result<usize, Error> {
    b.get(at..at + 4)
        .map(|s| u32::from_le_bytes(s.try_into().unwrap()) as usize)
        .ok_or(Error::Truncated)
}

/// Decompress a stream produced by [`compress`], verifying its CRC-32.
/// Multi-block streams are decoded on all available cores.
pub fn decompress(input: &[u8]) -> Result<Vec<u8>, Error> {
    decompress_with_threads(input, 0)
}

/// Like [`decompress`], with an explicit worker-thread count (`0` = all cores).
pub fn decompress_with_threads(input: &[u8], threads: usize) -> Result<Vec<u8>, Error> {
    decompress_with_dictionary(input, &[], threads)
}

/// Decompress a stream that may have been compressed with a dictionary
/// ([`compress_with_dictionary`]). Streams compressed without one ignore it.
pub fn decompress_with_dictionary(
    input: &[u8],
    dictionary: &[u8],
    threads: usize,
) -> Result<Vec<u8>, Error> {
    let h = parse_header(input)?;
    if h.method != METHOD_BLOCKS {
        return decompress_single(input, dictionary);
    }
    let p = &input[HEADER_LEN..];
    let _block_size = read_u32(p, 0)?;
    let n = read_u32(p, 4)?;
    if n == 0 || n > p.len() / 4 {
        return Err(Error::BadBlockTable);
    }
    let mut streams = Vec::with_capacity(n);
    let mut at = 8 + 4 * n;
    for i in 0..n {
        let sl = read_u32(p, 8 + 4 * i)?;
        let s = p.get(at..at + sl).ok_or(Error::Truncated)?;
        // Blocks are plain streams: forbid nesting.
        if parse_header(s)?.method == METHOD_BLOCKS {
            return Err(Error::BadBlockTable);
        }
        streams.push(s);
        at += sl;
    }
    let declared: usize = streams
        .iter()
        .map(|s| parse_header(s).map(|h| h.len))
        .sum::<Result<usize, Error>>()?;
    if declared != h.len {
        return Err(Error::BadBlockTable);
    }
    let parts = parallel_map(&streams, threads, |s| decompress_single(s, dictionary));
    let mut out = Vec::with_capacity(h.len);
    for part in parts {
        out.extend_from_slice(&part?);
    }
    let actual = crc32::crc32(&out);
    if actual != h.crc {
        return Err(Error::ChecksumMismatch {
            expected: h.crc,
            actual,
        });
    }
    Ok(out)
}

/// Decode a single stored, CM or CM+dictionary stream.
fn decompress_single(input: &[u8], dictionary: &[u8]) -> Result<Vec<u8>, Error> {
    let Header {
        method,
        bits,
        len,
        crc: expected,
    } = parse_header(input)?;
    let mut payload = &input[HEADER_LEN..];
    let mut dict: &[u8] = &[];
    if method == METHOD_CM_DICT {
        let crc = read_u32(payload, 0)? as u32;
        let dlen = read_u32(payload, 4)?;
        payload = &payload[8..];
        if dictionary.is_empty() {
            return Err(Error::DictionaryRequired { crc, len: dlen });
        }
        if dictionary.len() != dlen || crc32::crc32(dictionary) != crc {
            return Err(Error::DictionaryMismatch { crc, len: dlen });
        }
        dict = dictionary;
    }

    let out = match method {
        METHOD_STORED => {
            if payload.len() < len {
                return Err(Error::Truncated);
            }
            payload[..len].to_vec()
        }
        METHOD_CM | METHOD_CM_DICT => {
            if !(MIN_MEM_BITS..=MAX_MEM_BITS).contains(&bits) {
                return Err(Error::BadMemBits(bits));
            }
            // A CM payload is always shorter than the original, so a
            // plausible stream needs at least a little payload.
            if payload.is_empty() && len > 0 {
                return Err(Error::Truncated);
            }
            let mut hist = Vec::with_capacity(dict.len() + len);
            let mut pred = Predictor::new(bits as u32);
            pred.start();
            prime(&mut pred, &mut hist, dict);
            let mut dec = Decoder::new(payload);
            let end = dict.len() + len;
            while hist.len() < end {
                loop {
                    let bit = dec.decode(pred.p());
                    if let Some(byte) = pred.update(bit) {
                        hist.push(byte);
                        break;
                    }
                }
                pred.byte_update(&hist);
            }
            hist.drain(..dict.len());
            hist
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
