"""Python binding for shannon-edge (sedge), with no dependencies beyond ctypes.

Build the library first (`cargo build --release`). It is found via the
SEDGE_LIB environment variable, or in ../target/release next to this file.

    import shannon_edge as se

    packed = se.compress(data)                    # whole buffer
    assert se.decompress(packed) == data

    packed = se.compress(msg, dictionary=samples)  # shared knowledge
    assert se.decompress(packed, dictionary=samples) == msg

    model = se.PrimedModel(samples)                # read the dictionary once
    frame = model.compress(msg)                    # fast path for many messages
    assert model.decompress(frame) == msg

    tx, rx = se.Session(), se.Session()            # both sides keep learning
    for record in records:
        assert rx.decompress(tx.compress(record)) == record
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

__all__ = ["SedgeError", "compress", "decompress", "PrimedModel", "Session", "FlightSession", "version"]


def _find_library() -> str:
    env = os.environ.get("SEDGE_LIB")
    if env:
        return env
    name = {"darwin": "libshannon_edge.dylib", "win32": "shannon_edge.dll"}.get(sys.platform, "libshannon_edge.so")
    path = Path(__file__).resolve().parent.parent / "target" / "release" / name
    if not path.exists():
        raise OSError(f"{path} not found: run `cargo build --release` or set SEDGE_LIB")
    return str(path)


_lib = ctypes.CDLL(_find_library())
_u8p = ctypes.POINTER(ctypes.c_uint8)
_size = ctypes.c_size_t


def _sig(name, restype, *argtypes):
    f = getattr(_lib, name)
    f.restype = restype
    f.argtypes = list(argtypes)
    return f


_version = _sig("sedge_version", ctypes.c_char_p)
_error_message = _sig("sedge_error_message", ctypes.c_char_p, ctypes.c_int32)
_free = _sig("sedge_free", None, _u8p, _size)
_out = [ctypes.POINTER(_u8p), ctypes.POINTER(_size)]
_compress = _sig("sedge_compress", ctypes.c_int32, ctypes.c_char_p, _size, ctypes.c_char_p, _size, ctypes.c_int32, *_out)
_decompress = _sig("sedge_decompress", ctypes.c_int32, ctypes.c_char_p, _size, ctypes.c_char_p, _size, *_out)
_model_new = _sig("sedge_model_new", ctypes.c_void_p, ctypes.c_char_p, _size, ctypes.c_int32)
_model_load = _sig("sedge_model_load", ctypes.c_void_p, ctypes.c_char_p, _size, ctypes.POINTER(ctypes.c_int32))
_model_save = _sig("sedge_model_save", ctypes.c_int32, ctypes.c_void_p, *_out)
_model_compress = _sig("sedge_model_compress", ctypes.c_int32, ctypes.c_void_p, ctypes.c_char_p, _size, *_out)
_model_decompress = _sig("sedge_model_decompress", ctypes.c_int32, ctypes.c_void_p, ctypes.c_char_p, _size, *_out)
_model_free = _sig("sedge_model_free", None, ctypes.c_void_p)
_session_new = _sig("sedge_session_new", ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32)
_session_compress = _sig("sedge_session_compress", ctypes.c_int32, ctypes.c_void_p, ctypes.c_char_p, _size, *_out)
_session_decompress = _sig("sedge_session_decompress", ctypes.c_int32, ctypes.c_void_p, ctypes.c_char_p, _size, *_out)
_session_free = _sig("sedge_session_free", None, ctypes.c_void_p)
_u16p = ctypes.POINTER(ctypes.c_uint16)
_flight_new = _sig("sedge_flight_new", ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32)
_flight_compress = _sig("sedge_flight_compress", ctypes.c_int32, ctypes.c_void_p, _u16p, _size, *_out)
_flight_decompress = _sig("sedge_flight_decompress", ctypes.c_int32, ctypes.c_void_p, ctypes.c_char_p, _size,
                          ctypes.POINTER(_u16p), ctypes.POINTER(_size))
_free_samples = _sig("sedge_free_samples", None, _u16p, _size)
_flight_free = _sig("sedge_flight_free", None, ctypes.c_void_p)


class SedgeError(Exception):
    """A shannon-edge error; `code` is the negative SEDGE_E_* value."""

    def __init__(self, code: int):
        self.code = code
        super().__init__(f"{_error_message(code).decode()} (code {code})")


def version() -> str:
    return _version().decode()


def _call(fn, *args) -> bytes:
    out, out_len = _u8p(), _size()
    rc = fn(*args, ctypes.byref(out), ctypes.byref(out_len))
    if rc != 0:
        raise SedgeError(rc)
    try:
        return ctypes.string_at(out, out_len.value)
    finally:
        _free(out, out_len)


def _buf(b: bytes | bytearray | memoryview | None) -> bytes:
    return b"" if b is None else bytes(b)


def compress(data: bytes, dictionary: bytes | None = None, mem_bits: int = 0) -> bytes:
    """Compress a whole buffer (optionally with a shared dictionary)."""
    d, k = _buf(data), _buf(dictionary)
    return _call(_compress, d, len(d), k, len(k), mem_bits)


def decompress(data: bytes, dictionary: bytes | None = None) -> bytes:
    """Decompress a buffer made by `compress` (same dictionary, if any)."""
    d, k = _buf(data), _buf(dictionary)
    return _call(_decompress, d, len(d), k, len(k))


class PrimedModel:
    """A model that has read a dictionary once; compresses many messages
    from that state. Its streams also decode with `decompress(..., dictionary)`."""

    def __init__(self, dictionary: bytes | None = None, mem_bits: int = 0, *, _handle=None):
        if _handle is None:
            k = _buf(dictionary)
            _handle = _model_new(k, len(k), mem_bits)
            if not _handle:
                raise SedgeError(-1)
        self._h = _handle

    @classmethod
    def load(cls, data: bytes) -> "PrimedModel":
        """Load a model saved with `save()` or `sedge prime`."""
        err = ctypes.c_int32(0)
        b = _buf(data)
        h = _model_load(b, len(b), ctypes.byref(err))
        if not h:
            raise SedgeError(err.value)
        return cls(_handle=h)

    def save(self) -> bytes:
        return _call(_model_save, self._h)

    def compress(self, message: bytes) -> bytes:
        m = _buf(message)
        return _call(_model_compress, self._h, m, len(m))

    def decompress(self, data: bytes) -> bytes:
        d = _buf(data)
        return _call(_model_decompress, self._h, d, len(d))

    def close(self) -> None:
        if getattr(self, "_h", None):
            _model_free(self._h)
            self._h = None

    __del__ = close

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Session:
    """One side of a learning session: records must be decompressed in the
    order they were compressed. Start both sides the same way: empty at the
    same `mem_bits`, or from the same `PrimedModel`, with the same `lean`.

    `lean=True` drops the per-record sequence number and CRC (2-3 bytes of
    framing instead of ~8). Use it only on links that already guarantee
    integrity and order: corruption or loss is then not detected."""

    def __init__(self, model: PrimedModel | None = None, mem_bits: int = 0, lean: bool = False):
        self._h = _session_new(model._h if model is not None else None, mem_bits, 1 if lean else 0)
        if not self._h:
            raise SedgeError(-1)

    def compress(self, record: bytes) -> bytes:
        r = _buf(record)
        return _call(_session_compress, self._h, r, len(r))

    def decompress(self, frame: bytes) -> bytes:
        f = _buf(frame)
        return _call(_session_decompress, self._h, f, len(f))

    def close(self) -> None:
        if getattr(self, "_h", None):
            _session_free(self._h)
            self._h = None

    __del__ = close

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FlightSession:
    """One end of a telemetry link using the flight profile: packets of
    integer samples (each < 2**bits), both ends learning from every packet.
    No checksum: the link layer must guarantee integrity and order. Create
    both ends with the same `bits` and `table_bits`."""

    def __init__(self, bits: int, table_bits: int = 14):
        self._h = _flight_new(bits, table_bits)
        if not self._h:
            raise SedgeError(-1)

    def compress(self, samples) -> bytes:
        arr = (ctypes.c_uint16 * len(samples))(*samples)
        return _call(_flight_compress, self._h, arr, len(samples))

    def decompress(self, frame: bytes) -> list:
        f = _buf(frame)
        out, n = _u16p(), _size()
        rc = _flight_decompress(self._h, f, len(f), ctypes.byref(out), ctypes.byref(n))
        if rc != 0:
            raise SedgeError(rc)
        try:
            return out[: n.value]
        finally:
            _free_samples(out, n)

    def close(self) -> None:
        if getattr(self, "_h", None):
            _flight_free(self._h)
            self._h = None

    __del__ = close

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
