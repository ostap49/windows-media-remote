"""Builds the Flipper app's protocol/model C code so tests can check that frames
produced by the companion pass the exact validation the Flipper performs."""
from __future__ import annotations

import ctypes
import shutil
import subprocess
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[2] / "flipper" / "win_media_remote" / "core"


class NpFrame(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint8),
        ("session", ctypes.c_uint32),
        ("id", ctypes.c_uint32),
        ("length", ctypes.c_uint16),
        ("payload", ctypes.c_uint8 * 768),
    ]


class NpModel(ctypes.Structure):
    _fields_ = [
        ("epoch", ctypes.c_uint32), ("revision", ctypes.c_uint32), ("seq", ctypes.c_uint32),
        ("anchor", ctypes.c_uint32), ("scroll_anchor", ctypes.c_uint32),
        ("state", ctypes.c_uint8), ("flags", ctypes.c_uint8), ("mode", ctypes.c_uint8),
        ("speed", ctypes.c_int16), ("caps", ctypes.c_uint16),
        ("position", ctypes.c_uint64), ("duration", ctypes.c_uint64),
        ("title", ctypes.c_char * 193), ("artist", ctypes.c_char * 129),
        ("album", ctypes.c_char * 193), ("app", ctypes.c_char * 49),
        ("artwork", ctypes.c_uint8 * 270),
        ("has_artwork", ctypes.c_bool), ("synced", ctypes.c_bool), ("fresh", ctypes.c_bool),
    ]


class Flipper:
    """Thin ctypes wrapper over np_protocol.c / np_model.c."""

    def __init__(self, lib: ctypes.CDLL) -> None:
        self.lib = lib
        lib.np_decode.restype = ctypes.c_bool
        lib.np_decode.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(NpFrame)]
        lib.np_encode.restype = ctypes.c_size_t
        lib.np_encode.argtypes = [ctypes.POINTER(NpFrame), ctypes.c_char_p]
        lib.np_model_apply.argtypes = [ctypes.POINTER(NpModel), ctypes.POINTER(NpFrame), ctypes.c_uint32]
        lib.np_artwork_apply.argtypes = [ctypes.POINTER(NpModel), ctypes.POINTER(NpFrame)]
        self.model = NpModel()

    def decode(self, data: bytes) -> NpFrame | None:
        frame = NpFrame()
        return frame if self.lib.np_decode(data, len(data), ctypes.byref(frame)) else None

    def encode(self, kind: int, session: int, ident: int, payload: bytes) -> bytes:
        frame = NpFrame(type=kind, session=session, id=ident, length=len(payload))
        ctypes.memmove(frame.payload, payload, len(payload))
        out = ctypes.create_string_buffer(788)
        size = self.lib.np_encode(ctypes.byref(frame), out)
        assert size, "Flipper refused to encode frame"
        return out.raw[:size]

    def apply(self, frame: NpFrame, now: int = 1000) -> int:
        if frame.type == 0x13:
            return self.lib.np_artwork_apply(ctypes.byref(self.model), ctypes.byref(frame))
        return self.lib.np_model_apply(ctypes.byref(self.model), ctypes.byref(frame), now)


@pytest.fixture(scope="session")
def flipper_lib(tmp_path_factory) -> ctypes.CDLL:
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        pytest.skip("C compiler unavailable")
    out = tmp_path_factory.mktemp("np") / "libnp.so"
    subprocess.run(
        [compiler, "-shared", "-fPIC", "-O1", "-o", str(out), str(CORE / "np_protocol.c"), str(CORE / "np_model.c")],
        check=True,
    )
    return ctypes.CDLL(str(out))


@pytest.fixture
def flipper(flipper_lib) -> Flipper:
    return Flipper(flipper_lib)
