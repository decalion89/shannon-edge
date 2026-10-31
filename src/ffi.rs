//! C ABI, so any language with a C FFI (Python, Go, Java, C#, Node, ...) can
//! use shannon-edge. See `include/shannon_edge.h` for the C declarations and
//! `python/shannon_edge.py` for a ready-made Python binding.
//!
//! Conventions:
//! * Every function that can fail returns `0` on success or a negative
//!   `SEDGE_E_*` code; `sedge_error_message` describes a code.
//! * Output buffers are allocated by the library and returned through
//!   `out` / `out_len`; release them with `sedge_free`.
//! * Objects (`SedgeModel`, `SedgeSession`) are opaque pointers released
//!   with their `*_free` function. They are not thread-safe: use one per
//!   thread, or lock around them.
//! * Invalid input never aborts the process: sizes and pointers are checked
//!   and reported as error codes.

use crate::{
    compress_with_dictionary, decompress_with_dictionary, Error, Options, PrimedModel, Session,
    MAX_MEM_BITS, MIN_MEM_BITS,
};
use std::ffi::c_char;
use std::slice;

pub const SEDGE_OK: i32 = 0;
pub const SEDGE_E_ARGUMENT: i32 = -1;
pub const SEDGE_E_TRUNCATED: i32 = -2;
pub const SEDGE_E_BAD_MAGIC: i32 = -3;
pub const SEDGE_E_VERSION: i32 = -4;
pub const SEDGE_E_METHOD: i32 = -5;
pub const SEDGE_E_MEM_BITS: i32 = -6;
pub const SEDGE_E_TOO_LARGE: i32 = -7;
pub const SEDGE_E_CHECKSUM: i32 = -8;
pub const SEDGE_E_BLOCK_TABLE: i32 = -9;
pub const SEDGE_E_DICT_REQUIRED: i32 = -10;
pub const SEDGE_E_DICT_MISMATCH: i32 = -11;
pub const SEDGE_E_BAD_MODEL: i32 = -12;
pub const SEDGE_E_OUT_OF_SYNC: i32 = -13;
pub const SEDGE_E_NOT_SESSION: i32 = -14;

/// Largest input the format accepts (below 4 GiB, including any dictionary).
const LIMIT: usize = u32::MAX as usize - 1;

fn code(e: &Error) -> i32 {
    match e {
        Error::Truncated => SEDGE_E_TRUNCATED,
        Error::BadMagic => SEDGE_E_BAD_MAGIC,
        Error::UnsupportedVersion(_) => SEDGE_E_VERSION,
        Error::UnknownMethod(_) => SEDGE_E_METHOD,
        Error::BadMemBits(_) => SEDGE_E_MEM_BITS,
        Error::TooLarge(_) => SEDGE_E_TOO_LARGE,
        Error::ChecksumMismatch { .. } => SEDGE_E_CHECKSUM,
        Error::BadBlockTable => SEDGE_E_BLOCK_TABLE,
        Error::DictionaryRequired { .. } => SEDGE_E_DICT_REQUIRED,
        Error::DictionaryMismatch { .. } => SEDGE_E_DICT_MISMATCH,
        Error::BadModel => SEDGE_E_BAD_MODEL,
        Error::SessionOutOfSync { .. } => SEDGE_E_OUT_OF_SYNC,
        Error::NotThisSession => SEDGE_E_NOT_SESSION,
    }
}

/// Human-readable description of an error code (static, never freed).
#[no_mangle]
pub extern "C" fn sedge_error_message(code: i32) -> *const c_char {
    let s: &'static [u8] = match code {
        SEDGE_OK => b"ok\0",
        SEDGE_E_ARGUMENT => {
            b"invalid argument (null pointer, bad memory level or input too large)\0"
        }
        SEDGE_E_TRUNCATED => b"input is truncated\0",
        SEDGE_E_BAD_MAGIC => b"not a shannon-edge stream\0",
        SEDGE_E_VERSION => b"unsupported format version\0",
        SEDGE_E_METHOD => b"unknown compression method\0",
        SEDGE_E_MEM_BITS => b"invalid memory level in stream\0",
        SEDGE_E_TOO_LARGE => b"declared size too large\0",
        SEDGE_E_CHECKSUM => b"checksum mismatch: data is corrupt\0",
        SEDGE_E_BLOCK_TABLE => b"inconsistent block table: data is corrupt\0",
        SEDGE_E_DICT_REQUIRED => b"stream needs a dictionary\0",
        SEDGE_E_DICT_MISMATCH => b"wrong dictionary for this stream\0",
        SEDGE_E_BAD_MODEL => b"not a valid primed model\0",
        SEDGE_E_OUT_OF_SYNC => b"session message lost or out of order\0",
        SEDGE_E_NOT_SESSION => b"not a session message\0",
        _ => b"unknown error code\0",
    };
    s.as_ptr() as *const c_char
}

/// Library version, e.g. "0.1.0" (static, never freed).
#[no_mangle]
pub extern "C" fn sedge_version() -> *const c_char {
    concat!(env!("CARGO_PKG_VERSION"), "\0").as_ptr() as *const c_char
}

/// # Safety
/// `p` must point to `n` readable bytes (or be anything when `n == 0`).
unsafe fn input<'a>(p: *const u8, n: usize) -> Option<&'a [u8]> {
    if n == 0 {
        Some(&[])
    } else if p.is_null() || n > LIMIT {
        None
    } else {
        Some(slice::from_raw_parts(p, n))
    }
}

/// # Safety
/// `out` and `out_len` must be valid for writes.
unsafe fn give(v: Vec<u8>, out: *mut *mut u8, out_len: *mut usize) -> i32 {
    let b = v.into_boxed_slice();
    *out_len = b.len();
    *out = Box::into_raw(b) as *mut u8;
    SEDGE_OK
}

fn options(mem_bits: i32) -> Option<Options> {
    let mut o = Options::default();
    if mem_bits != 0 {
        if !(MIN_MEM_BITS as i32..=MAX_MEM_BITS as i32).contains(&mem_bits) {
            return None;
        }
        o.mem_bits = mem_bits as u8;
    }
    Some(o)
}

/// Release a buffer returned by this library.
///
/// # Safety
/// `p`/`n` must come from a `sedge_*` output, freed at most once.
#[no_mangle]
pub unsafe extern "C" fn sedge_free(p: *mut u8, n: usize) {
    if !p.is_null() {
        drop(Box::from_raw(std::ptr::slice_from_raw_parts_mut(p, n)));
    }
}

/// Compress `data` (with an optional dictionary; pass `NULL, 0` for none).
/// `mem_bits` = 0 for the default memory level, else 16..=24.
///
/// # Safety
/// Input pointers must be valid for their lengths; `out`/`out_len` writable.
#[no_mangle]
pub unsafe extern "C" fn sedge_compress(
    data: *const u8,
    len: usize,
    dict: *const u8,
    dict_len: usize,
    mem_bits: i32,
    out: *mut *mut u8,
    out_len: *mut usize,
) -> i32 {
    let (Some(d), Some(k), Some(o)) = (input(data, len), input(dict, dict_len), options(mem_bits))
    else {
        return SEDGE_E_ARGUMENT;
    };
    if out.is_null() || out_len.is_null() || d.len() + k.len() > LIMIT {
        return SEDGE_E_ARGUMENT;
    }
    give(compress_with_dictionary(d, k, &o), out, out_len)
}

/// Decompress a stream (with the dictionary it was compressed with, if any).
///
/// # Safety
/// Input pointers must be valid for their lengths; `out`/`out_len` writable.
#[no_mangle]
pub unsafe extern "C" fn sedge_decompress(
    data: *const u8,
    len: usize,
    dict: *const u8,
    dict_len: usize,
    out: *mut *mut u8,
    out_len: *mut usize,
) -> i32 {
    let (Some(d), Some(k)) = (input(data, len), input(dict, dict_len)) else {
        return SEDGE_E_ARGUMENT;
    };
    if out.is_null() || out_len.is_null() {
        return SEDGE_E_ARGUMENT;
    }
    match decompress_with_dictionary(d, k, 0) {
        Ok(v) => give(v, out, out_len),
        Err(e) => code(&e),
    }
}

/// Opaque primed model.
pub struct SedgeModel(PrimedModel);
/// Opaque session.
pub struct SedgeSession(Session);

/// Prime a model on a (non-empty) dictionary. Returns NULL on bad input.
///
/// # Safety
/// `dict` must be valid for `dict_len` bytes.
#[no_mangle]
pub unsafe extern "C" fn sedge_model_new(
    dict: *const u8,
    dict_len: usize,
    mem_bits: i32,
) -> *mut SedgeModel {
    match (input(dict, dict_len), options(mem_bits)) {
        (Some(k), Some(o)) if !k.is_empty() && k.len() < (1 << 31) => {
            Box::into_raw(Box::new(SedgeModel(PrimedModel::new(k, &o))))
        }
        _ => std::ptr::null_mut(),
    }
}

/// Load a model saved with `sedge_model_save` (or `sedge prime`). On error
/// returns NULL and stores the code in `*err` (if `err` is not NULL).
///
/// # Safety
/// `data` must be valid for `len` bytes; `err` NULL or writable.
#[no_mangle]
pub unsafe extern "C" fn sedge_model_load(
    data: *const u8,
    len: usize,
    err: *mut i32,
) -> *mut SedgeModel {
    let result = match input(data, len) {
        Some(b) => PrimedModel::from_bytes(b).map_err(|e| code(&e)),
        None => Err(SEDGE_E_ARGUMENT),
    };
    match result {
        Ok(m) => Box::into_raw(Box::new(SedgeModel(m))),
        Err(c) => {
            if !err.is_null() {
                *err = c;
            }
            std::ptr::null_mut()
        }
    }
}

/// Serialise a model (to store it, or ship it to the other side).
///
/// # Safety
/// `model` from `sedge_model_new`/`_load`; `out`/`out_len` writable.
#[no_mangle]
pub unsafe extern "C" fn sedge_model_save(
    model: *const SedgeModel,
    out: *mut *mut u8,
    out_len: *mut usize,
) -> i32 {
    if model.is_null() || out.is_null() || out_len.is_null() {
        return SEDGE_E_ARGUMENT;
    }
    give((*model).0.to_bytes(), out, out_len)
}

/// Compress one message from the model's primed state (the model is
/// restored afterwards). The stream also decodes with the raw dictionary.
///
/// # Safety
/// `model` valid; input valid for `len`; `out`/`out_len` writable.
#[no_mangle]
pub unsafe extern "C" fn sedge_model_compress(
    model: *mut SedgeModel,
    data: *const u8,
    len: usize,
    out: *mut *mut u8,
    out_len: *mut usize,
) -> i32 {
    let Some(d) = input(data, len) else {
        return SEDGE_E_ARGUMENT;
    };
    if model.is_null() || out.is_null() || out_len.is_null() {
        return SEDGE_E_ARGUMENT;
    }
    let m = &mut (*model).0;
    if m.dictionary().len() + d.len() > LIMIT {
        return SEDGE_E_ARGUMENT;
    }
    give(m.compress_message(d, &Options::default()), out, out_len)
}

/// Decompress one message with the model (see `sedge_model_compress`).
///
/// # Safety
/// `model` valid; input valid for `len`; `out`/`out_len` writable.
#[no_mangle]
pub unsafe extern "C" fn sedge_model_decompress(
    model: *mut SedgeModel,
    data: *const u8,
    len: usize,
    out: *mut *mut u8,
    out_len: *mut usize,
) -> i32 {
    let Some(d) = input(data, len) else {
        return SEDGE_E_ARGUMENT;
    };
    if model.is_null() || out.is_null() || out_len.is_null() {
        return SEDGE_E_ARGUMENT;
    }
    match (*model).0.decompress_message(d) {
        Ok(v) => give(v, out, out_len),
        Err(e) => code(&e),
    }
}

/// Release a model.
///
/// # Safety
/// `model` from this library, freed at most once (NULL is allowed).
#[no_mangle]
pub unsafe extern "C" fn sedge_model_free(model: *mut SedgeModel) {
    if !model.is_null() {
        drop(Box::from_raw(model));
    }
}

/// Start a session. With `model` NULL it starts empty at `mem_bits`
/// (0 = default); otherwise it starts from a copy of the primed model.
/// Returns NULL on bad input.
///
/// # Safety
/// `model` NULL or valid.
#[no_mangle]
pub unsafe extern "C" fn sedge_session_new(
    model: *const SedgeModel,
    mem_bits: i32,
) -> *mut SedgeSession {
    let s = if model.is_null() {
        match options(mem_bits) {
            Some(o) => Session::new(&o),
            None => return std::ptr::null_mut(),
        }
    } else {
        Session::from_model((*model).0.clone())
    };
    Box::into_raw(Box::new(SedgeSession(s)))
}

/// Compress the next record of a session (and learn from it).
///
/// # Safety
/// `session` valid; input valid for `len`; `out`/`out_len` writable.
#[no_mangle]
pub unsafe extern "C" fn sedge_session_compress(
    session: *mut SedgeSession,
    data: *const u8,
    len: usize,
    out: *mut *mut u8,
    out_len: *mut usize,
) -> i32 {
    let Some(d) = input(data, len) else {
        return SEDGE_E_ARGUMENT;
    };
    if session.is_null() || out.is_null() || out_len.is_null() {
        return SEDGE_E_ARGUMENT;
    }
    let s = &mut (*session).0;
    if s.history_len() + d.len() > LIMIT {
        return SEDGE_E_TOO_LARGE;
    }
    give(s.compress(d), out, out_len)
}

/// Decompress the next record of a session (and learn from it). On error
/// the session is unchanged.
///
/// # Safety
/// `session` valid; input valid for `len`; `out`/`out_len` writable.
#[no_mangle]
pub unsafe extern "C" fn sedge_session_decompress(
    session: *mut SedgeSession,
    data: *const u8,
    len: usize,
    out: *mut *mut u8,
    out_len: *mut usize,
) -> i32 {
    let Some(d) = input(data, len) else {
        return SEDGE_E_ARGUMENT;
    };
    if session.is_null() || out.is_null() || out_len.is_null() {
        return SEDGE_E_ARGUMENT;
    }
    match (*session).0.decompress(d) {
        Ok(v) => give(v, out, out_len),
        Err(e) => code(&e),
    }
}

/// Release a session.
///
/// # Safety
/// `session` from this library, freed at most once (NULL is allowed).
#[no_mangle]
pub unsafe extern "C" fn sedge_session_free(session: *mut SedgeSession) {
    if !session.is_null() {
        drop(Box::from_raw(session));
    }
}
