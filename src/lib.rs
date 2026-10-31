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
pub mod train;

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

/// First byte of a session message: marker in the high bits, kind below.
const SESSION_MARK: u8 = 0xE0;
const SESSION_STORED: u8 = 0;
const SESSION_CM: u8 = 1;

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
    /// A saved [`PrimedModel`] is damaged or not a model file.
    BadModel,
    /// A session message arrived out of order (or one was lost).
    SessionOutOfSync { expected: u64, got: u64 },
    /// Not a session message.
    NotThisSession,
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
            Error::BadModel => write!(f, "not a valid primed-model (.sedgem) file"),
            Error::SessionOutOfSync { expected, got } => write!(
                f,
                "session message {got} (mod 65536) received, expected {expected}: \
                 a message was lost or reordered"
            ),
            Error::NotThisSession => write!(f, "not a message of this session"),
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
    compress_prior(data, Prior::None, opts)
}

/// Compress `data` given a dictionary: data that the decompressor will also
/// have. Before coding, the model reads the dictionary (in every block), so
/// it starts out already knowing its vocabulary, phrases and structure. The
/// cost of a message then approaches `H(data | dictionary)`, which for small
/// messages similar to the dictionary is far below `H(data)`.
///
/// Decompression requires exactly the same dictionary
/// ([`decompress_with_dictionary`]); the stream records its CRC-32 and
/// length. Priming costs time proportional to the dictionary size, per block;
/// to pay it only once, see [`PrimedModel`]. An empty dictionary is the same
/// as [`compress`].
///
/// # Panics
/// If `dictionary` plus one block reaches 4 GiB.
pub fn compress_with_dictionary(data: &[u8], dictionary: &[u8], opts: &Options) -> Vec<u8> {
    let prior = if dictionary.is_empty() {
        Prior::None
    } else {
        Prior::Dict(dictionary)
    };
    compress_prior(data, prior, opts)
}

/// Compress `data` with a model already primed on a dictionary. This
/// produces a normal dictionary stream (decodable with either the same
/// [`PrimedModel`] or the raw dictionary) but skips re-reading the
/// dictionary: each block starts from a copy of the primed state.
///
/// The memory level is the model's own ([`PrimedModel::mem_bits`]), so the
/// bytes can differ slightly from [`compress_with_dictionary`], which sizes
/// tables per block; both are valid.
pub fn compress_with_model(data: &[u8], model: &PrimedModel, opts: &Options) -> Vec<u8> {
    compress_prior(data, Prior::Model(model), opts)
}

/// What a block's model knows before it sees the block.
#[derive(Clone, Copy)]
enum Prior<'a> {
    None,
    Dict(&'a [u8]),
    Model(&'a PrimedModel),
}

impl Prior<'_> {
    fn dict(&self) -> &[u8] {
        match self {
            Prior::None => &[],
            Prior::Dict(d) => d,
            Prior::Model(m) => &m.dict,
        }
    }
}

fn compress_prior(data: &[u8], prior: Prior, opts: &Options) -> Vec<u8> {
    assert!(
        (data.len() as u64) < u32::MAX as u64,
        "format v1 supports inputs below 4 GiB"
    );
    if opts.block_size == 0 || data.len() <= opts.block_size {
        return compress_single(data, opts.mem_bits, prior);
    }

    let blocks: Vec<&[u8]> = data.chunks(opts.block_size).collect();
    let streams = parallel_map(&blocks, opts.threads, |b| {
        compress_single(b, opts.mem_bits, prior)
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

/// A model in the state it reaches after reading `dict` at memory level
/// `bits`, plus the history buffer holding the dictionary. With a matching
/// [`PrimedModel`] this is a copy; otherwise the dictionary is read.
fn start_model(
    bits: u8,
    dict: &[u8],
    model: Option<&PrimedModel>,
    extra: usize,
) -> (Predictor, Vec<u8>) {
    let mut hist = Vec::with_capacity(dict.len() + extra);
    match model {
        Some(m) if m.bits == bits => {
            hist.extend_from_slice(&m.dict);
            (m.pred.clone(), hist)
        }
        _ => {
            let mut pred = Predictor::new(bits as u32);
            pred.start();
            prime(&mut pred, &mut hist, dict);
            (pred, hist)
        }
    }
}

/// Compress one block as a self-contained stored, CM or CM+dictionary stream.
fn compress_single(data: &[u8], mem_bits: u8, prior: Prior) -> Vec<u8> {
    let dict = prior.dict();
    assert!(
        ((dict.len() + data.len()) as u64) < u32::MAX as u64,
        "dictionary plus block must stay below 4 GiB"
    );
    let (bits, model) = match prior {
        Prior::Model(m) => (m.bits, Some(m)),
        _ => (effective_mem_bits(dict.len() + data.len(), mem_bits), None),
    };
    if data.is_empty() {
        return stored(data);
    }
    let (mut pred, mut hist) = start_model(bits, dict, model, data.len());
    let payload = encode_payload(&mut pred, &mut hist, data);
    let dict_id = (!dict.is_empty()).then(|| {
        let crc = match prior {
            Prior::Model(m) => m.dict_crc,
            _ => crc32::crc32(dict),
        };
        (crc, dict.len())
    });
    wrap_cm(data, bits, dict_id, payload)
}

/// Code `data` with `pred`, appending it to `hist`. `None` if the output
/// would not be smaller than the input (the caller then stores it).
fn encode_payload(pred: &mut Predictor, hist: &mut Vec<u8>, data: &[u8]) -> Option<Vec<u8>> {
    encode_payload_with(pred, hist, data, false)
}

/// Like [`encode_payload`]; `short` selects the minimal coder flush.
fn encode_payload_with(
    pred: &mut Predictor,
    hist: &mut Vec<u8>,
    data: &[u8],
    short: bool,
) -> Option<Vec<u8>> {
    let mut enc = Encoder::new(data.len() / 2 + 16);
    for &byte in data {
        for k in (0..8).rev() {
            let bit = ((byte >> k) & 1) as u32;
            enc.encode(bit, pred.p());
            pred.update(bit);
        }
        hist.push(byte);
        pred.byte_update(hist);
        if enc.bytes_written() >= data.len() {
            return None;
        }
    }
    Some(if short {
        enc.finish_short()
    } else {
        enc.finish()
    })
}

/// Wrap a CM payload in its container, or store `data` if that is smaller.
fn wrap_cm(data: &[u8], bits: u8, dict: Option<(u32, usize)>, payload: Option<Vec<u8>>) -> Vec<u8> {
    let Some(payload) = payload else {
        return stored(data);
    };
    let tag = if dict.is_some() { 8 } else { 0 };
    if payload.len() + tag >= data.len() {
        return stored(data);
    }
    let crc = crc32::crc32(data);
    let mut out = match dict {
        None => header(METHOD_CM, bits, data.len() as u64, crc),
        Some((dict_crc, dict_len)) => {
            let mut h = header(METHOD_CM_DICT, bits, data.len() as u64, crc);
            h.extend_from_slice(&dict_crc.to_le_bytes());
            h.extend_from_slice(&(dict_len as u32).to_le_bytes());
            h
        }
    };
    out.extend_from_slice(&payload);
    out
}

/// Decode `len` bytes from `payload` with `pred`, appending them to `hist`.
fn decode_payload(pred: &mut Predictor, hist: &mut Vec<u8>, payload: &[u8], len: usize) {
    let mut dec = Decoder::new(payload);
    let end = hist.len() + len;
    while hist.len() < end {
        loop {
            let bit = dec.decode(pred.p());
            if let Some(byte) = pred.update(bit) {
                hist.push(byte);
                break;
            }
        }
        pred.byte_update(hist);
    }
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
    decompress_prior(input, Prior::None, threads)
}

/// Decompress a stream that may have been compressed with a dictionary
/// ([`compress_with_dictionary`] or [`compress_with_model`]). Streams
/// compressed without one ignore it.
pub fn decompress_with_dictionary(
    input: &[u8],
    dictionary: &[u8],
    threads: usize,
) -> Result<Vec<u8>, Error> {
    let prior = if dictionary.is_empty() {
        Prior::None
    } else {
        Prior::Dict(dictionary)
    };
    decompress_prior(input, prior, threads)
}

/// Like [`decompress_with_dictionary`], but starts from a primed model
/// instead of re-reading the dictionary whenever the memory levels match.
pub fn decompress_with_model(
    input: &[u8],
    model: &PrimedModel,
    threads: usize,
) -> Result<Vec<u8>, Error> {
    decompress_prior(input, Prior::Model(model), threads)
}

fn decompress_prior(input: &[u8], prior: Prior, threads: usize) -> Result<Vec<u8>, Error> {
    let h = parse_header(input)?;
    if h.method != METHOD_BLOCKS {
        return decompress_single(input, prior);
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
    let parts = parallel_map(&streams, threads, |s| decompress_single(s, prior));
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
fn decompress_single(input: &[u8], prior: Prior) -> Result<Vec<u8>, Error> {
    let Header {
        method,
        bits,
        len,
        crc: expected,
    } = parse_header(input)?;
    let mut payload = &input[HEADER_LEN..];
    let mut dict: &[u8] = &[];
    let mut model = None;
    if method == METHOD_CM_DICT {
        let crc = read_u32(payload, 0)? as u32;
        let dlen = read_u32(payload, 4)?;
        payload = &payload[8..];
        let (have, have_crc) = match prior {
            Prior::None => return Err(Error::DictionaryRequired { crc, len: dlen }),
            Prior::Dict(d) => (d, crc32::crc32(d)),
            Prior::Model(m) => {
                model = Some(m);
                (&m.dict[..], m.dict_crc)
            }
        };
        if have.len() != dlen || have_crc != crc {
            return Err(Error::DictionaryMismatch { crc, len: dlen });
        }
        dict = have;
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
            let (mut pred, mut hist) = start_model(bits, dict, model, len);
            decode_payload(&mut pred, &mut hist, payload, len);
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

// ---------------------------------------------------------------------------
// Primed models: pay for a dictionary once
// ---------------------------------------------------------------------------

/// Magic bytes of a saved [`PrimedModel`] (`.sedgem` file).
pub const MODEL_MAGIC: [u8; 8] = *b"SEDGMODL";

/// A model that has already read a dictionary. Priming is the slow part of
/// dictionary compression (it runs at model speed); a `PrimedModel` does it
/// once, then every message or block starts from a copy of the primed state.
///
/// It can be kept in memory (e.g. by a server compressing many small
/// messages) or saved with [`PrimedModel::to_bytes`] and loaded later with
/// [`PrimedModel::from_bytes`]. Snapshots are a cache, not a new format:
/// streams made with a model decode with the raw dictionary and vice versa.
#[derive(Clone)]
pub struct PrimedModel {
    bits: u8,
    dict: Vec<u8>,
    dict_crc: u32,
    pred: Predictor,
}

impl PrimedModel {
    /// Prime a model on `dictionary`. Tables are sized for the dictionary
    /// plus messages of up to the same size, capped at `opts.mem_bits`.
    ///
    /// # Panics
    /// If the dictionary is empty or reaches 2 GiB.
    pub fn new(dictionary: &[u8], opts: &Options) -> Self {
        assert!(!dictionary.is_empty(), "a primed model needs a dictionary");
        assert!(
            dictionary.len() < (1 << 31),
            "dictionary must be below 2 GiB"
        );
        let bits = effective_mem_bits(dictionary.len() * 2, opts.mem_bits);
        let (pred, hist) = start_model(bits, dictionary, None, 0);
        Self {
            bits,
            dict_crc: crc32::crc32(&hist),
            dict: hist,
            pred,
        }
    }

    /// The dictionary this model has read.
    pub fn dictionary(&self) -> &[u8] {
        &self.dict
    }

    /// Memory level of the model's tables.
    pub fn mem_bits(&self) -> u8 {
        self.bits
    }

    /// Compress one message from the primed state, working on the model in
    /// place and then restoring it exactly (a journal records every change).
    /// Same bytes as [`compress_with_model`], but the cost is proportional to
    /// the message instead of copying the whole model, which makes it the
    /// fast path for many small messages. Inputs larger than one block fall
    /// back to [`compress_with_model`].
    pub fn compress_message(&mut self, data: &[u8], opts: &Options) -> Vec<u8> {
        if data.is_empty() || (opts.block_size != 0 && data.len() > opts.block_size) {
            return compress_with_model(data, self, opts);
        }
        assert!(
            ((self.dict.len() + data.len()) as u64) < u32::MAX as u64,
            "dictionary plus message must stay below 4 GiB"
        );
        let dict_len = self.dict.len();
        let guard = self.pred.begin_journal();
        let payload = encode_payload(&mut self.pred, &mut self.dict, data);
        self.pred.rollback(guard);
        self.dict.truncate(dict_len);
        wrap_cm(data, self.bits, Some((self.dict_crc, dict_len)), payload)
    }

    /// Decompress one message with the model in place (see
    /// [`PrimedModel::compress_message`]); any stream [`decompress_with_model`]
    /// accepts is accepted, using the fast path whenever it applies.
    pub fn decompress_message(&mut self, input: &[u8]) -> Result<Vec<u8>, Error> {
        let h = parse_header(input)?;
        if h.method != METHOD_CM_DICT || h.bits != self.bits {
            return decompress_with_model(input, self, 0);
        }
        let payload = &input[HEADER_LEN..];
        let crc = read_u32(payload, 0)? as u32;
        let dlen = read_u32(payload, 4)?;
        if dlen != self.dict.len() || crc != self.dict_crc {
            return Err(Error::DictionaryMismatch { crc, len: dlen });
        }
        let payload = &payload[8..];
        if payload.is_empty() && h.len > 0 {
            return Err(Error::Truncated);
        }
        let guard = self.pred.begin_journal();
        decode_payload(&mut self.pred, &mut self.dict, payload, h.len);
        self.pred.rollback(guard);
        let out = self.dict.split_off(dlen);
        let actual = crc32::crc32(&out);
        if actual != h.crc {
            return Err(Error::ChecksumMismatch {
                expected: h.crc,
                actual,
            });
        }
        Ok(out)
    }

    /// Serialise the model (dictionary included) so it can be loaded later
    /// without re-reading the dictionary. Size ≈ the model's memory use.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut w = model::Writer::default();
        w.0.extend_from_slice(&MODEL_MAGIC);
        w.0.push(FORMAT_VERSION);
        w.0.push(self.bits);
        w.0.extend_from_slice(&[0, 0]);
        w.0.extend_from_slice(&self.dict_crc.to_le_bytes());
        w.0.extend_from_slice(&(self.dict.len() as u32).to_le_bytes());
        w.0.extend_from_slice(&self.dict);
        self.pred.save(&mut w);
        let crc = crc32::crc32(&w.0);
        w.0.extend_from_slice(&crc.to_le_bytes());
        w.0
    }

    /// Load a model saved by [`PrimedModel::to_bytes`]. The whole file is
    /// checksummed and every field is range-checked.
    pub fn from_bytes(b: &[u8]) -> Result<Self, Error> {
        if b.len() < 24 || b[..8] != MODEL_MAGIC {
            return Err(Error::BadModel);
        }
        let (body, tail) = b.split_at(b.len() - 4);
        if crc32::crc32(body) != u32::from_le_bytes(tail.try_into().unwrap()) {
            return Err(Error::BadModel);
        }
        if body[8] != FORMAT_VERSION {
            return Err(Error::UnsupportedVersion(body[8]));
        }
        let bits = body[9];
        if !(MIN_MEM_BITS..=MAX_MEM_BITS).contains(&bits) {
            return Err(Error::BadMemBits(bits));
        }
        let dict_crc = read_u32(body, 12)? as u32;
        let dlen = read_u32(body, 16)?;
        let dict = body.get(20..20 + dlen).ok_or(Error::BadModel)?.to_vec();
        if dict.is_empty() || crc32::crc32(&dict) != dict_crc {
            return Err(Error::BadModel);
        }
        let mut r = model::Reader::new(&body[20 + dlen..]);
        let pred = Predictor::load(bits as u32, &mut r, dict.len()).ok_or(Error::BadModel)?;
        if !r.is_done() {
            return Err(Error::BadModel);
        }
        Ok(Self {
            bits,
            dict,
            dict_crc,
            pred,
        })
    }
}

// ---------------------------------------------------------------------------
// Sessions: both sides keep learning from every message
// ---------------------------------------------------------------------------

/// A compression session between one sender and one receiver. Unlike
/// [`PrimedModel::compress_message`], which starts every message from the
/// same frozen state, a session **keeps learning**: message *n* is coded
/// with everything learned from messages *0..n-1* (plus the dictionary the
/// session started from, if any). Both sides make the same updates in the
/// same order, so they stay in step without ever exchanging the model.
///
/// Session messages use a compact frame (typically 8 bytes of overhead
/// instead of the 20-byte file header), because they are meant for small
/// records:
///
/// | Size | Field |
/// |---:|---|
/// | 1 | `0xE0` + kind (`0` stored, `1` coded) |
/// | 1–5 | original length (LEB128) |
/// | 2 | sequence number, low 16 bits |
/// | 4 | CRC-32 of the original |
/// | … | payload (coded with a minimal flush, or stored) |
///
/// Messages must be decompressed in order. A lost or reordered message is
/// reported as [`Error::SessionOutOfSync`]; a corrupt one fails its CRC. In
/// both cases the receiver is left unchanged (its updates are journaled and
/// rolled back), so the session continues once the right message arrives.
///
/// Memory: the model is fixed-size, but the history the match model refers
/// to grows with the traffic (one byte per byte sent).
#[derive(Clone)]
pub struct Session {
    model: PrimedModel,
    seq: u64,
}

fn put_varint(out: &mut Vec<u8>, mut v: u64) {
    while v >= 0x80 {
        out.push((v as u8) | 0x80);
        v >>= 7;
    }
    out.push(v as u8);
}

fn get_varint(b: &[u8], pos: &mut usize) -> Result<u64, Error> {
    let mut v = 0u64;
    for shift in (0..35).step_by(7) {
        let byte = *b.get(*pos).ok_or(Error::Truncated)?;
        *pos += 1;
        v |= ((byte & 0x7f) as u64) << shift;
        if byte < 0x80 {
            return Ok(v);
        }
    }
    Err(Error::TooLarge(v))
}

impl Session {
    /// A session that starts from a primed model (shared knowledge). Both
    /// sides must start from the same dictionary and memory level.
    pub fn from_model(model: PrimedModel) -> Self {
        Self { model, seq: 0 }
    }

    /// A session that starts from an empty model at memory level
    /// `opts.mem_bits`.
    pub fn new(opts: &Options) -> Self {
        let bits = opts.mem_bits.clamp(MIN_MEM_BITS, MAX_MEM_BITS);
        let (pred, hist) = start_model(bits, &[], None, 0);
        Self {
            model: PrimedModel {
                bits,
                dict: hist,
                dict_crc: 0,
                pred,
            },
            seq: 0,
        }
    }

    /// Number of messages processed so far.
    pub fn messages(&self) -> u64 {
        self.seq
    }

    fn frame(&self, kind: u8, data: &[u8]) -> Vec<u8> {
        let mut out = Vec::with_capacity(12 + data.len() / 2);
        out.push(SESSION_MARK | kind);
        put_varint(&mut out, data.len() as u64);
        out.extend_from_slice(&(self.seq as u16).to_le_bytes());
        out.extend_from_slice(&crc32::crc32(data).to_le_bytes());
        out
    }

    /// Compress the next message and learn from it.
    pub fn compress(&mut self, data: &[u8]) -> Vec<u8> {
        assert!(
            ((self.model.dict.len() + data.len()) as u64) < u32::MAX as u64,
            "session history must stay below 4 GiB"
        );
        let hist_len = self.model.dict.len();
        let guard = self.model.pred.begin_journal();
        let payload = encode_payload_with(&mut self.model.pred, &mut self.model.dict, data, true);
        let out = match payload {
            Some(p) if p.len() < data.len() => {
                self.model.pred.commit(guard);
                let mut out = self.frame(SESSION_CM, data);
                out.extend_from_slice(&p);
                out
            }
            _ => {
                // Incompressible: send it stored and do not learn from it
                // (the receiver does the same).
                self.model.pred.rollback(guard);
                self.model.dict.truncate(hist_len);
                let mut out = self.frame(SESSION_STORED, data);
                out.extend_from_slice(data);
                out
            }
        };
        self.seq += 1;
        out
    }

    /// Decompress the next message and learn from it. On any error the
    /// session is left exactly as it was.
    pub fn decompress(&mut self, input: &[u8]) -> Result<Vec<u8>, Error> {
        let first = *input.first().ok_or(Error::Truncated)?;
        if first & !1 != SESSION_MARK {
            return Err(Error::NotThisSession);
        }
        let mut pos = 1;
        let len = get_varint(input, &mut pos)?;
        if len >= u32::MAX as u64 {
            return Err(Error::TooLarge(len));
        }
        let len = len as usize;
        let seq = read_u16(input, pos)?;
        let crc = read_u32(input, pos + 2)? as u32;
        let payload = &input[pos + 6..];
        if seq != self.seq as u16 {
            return Err(Error::SessionOutOfSync {
                expected: self.seq,
                got: seq as u64,
            });
        }
        let out = if first & 1 == SESSION_STORED {
            let out = payload.get(..len).ok_or(Error::Truncated)?.to_vec();
            let actual = crc32::crc32(&out);
            if actual != crc {
                return Err(Error::ChecksumMismatch {
                    expected: crc,
                    actual,
                });
            }
            out
        } else {
            if payload.is_empty() && len > 0 {
                return Err(Error::Truncated);
            }
            let hist_len = self.model.dict.len();
            let guard = self.model.pred.begin_journal();
            decode_payload(&mut self.model.pred, &mut self.model.dict, payload, len);
            let out = self.model.dict[hist_len..].to_vec();
            let actual = crc32::crc32(&out);
            if actual != crc {
                self.model.pred.rollback(guard);
                self.model.dict.truncate(hist_len);
                return Err(Error::ChecksumMismatch {
                    expected: crc,
                    actual,
                });
            }
            self.model.pred.commit(guard);
            out
        };
        self.seq += 1;
        Ok(out)
    }
}

fn read_u16(b: &[u8], at: usize) -> Result<u16, Error> {
    b.get(at..at + 2)
        .map(|s| u16::from_le_bytes(s.try_into().unwrap()))
        .ok_or(Error::Truncated)
}

impl fmt::Debug for PrimedModel {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("PrimedModel")
            .field("mem_bits", &self.bits)
            .field("dictionary_len", &self.dict.len())
            .field("dictionary_crc", &format_args!("{:08x}", self.dict_crc))
            .finish()
    }
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
