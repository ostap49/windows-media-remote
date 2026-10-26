"""FNP/1 framing shared with the Flipper app; see protocol/constants.json."""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

SERVICE = "8f9a1000-6d8a-4f1b-a6e6-3b4c5d6e7f80"
RX = "8f9a1001-6d8a-4f1b-a6e6-3b4c5d6e7f80"  # PC -> Flipper, write with response
TX = "8f9a1002-6d8a-4f1b-a6e6-3b4c5d6e7f80"  # Flipper -> PC, indications
ADVERTISED_NAMES = ("NPW", "NP")  # Win Media Remote, original Now Playing FAP

MAGIC = b"FNP1"
VERSION = 1
MAX_PAYLOAD = 768
MAX_FRAME = 788
CHUNK = 20
CHARACTERISTIC_MAX = 128
MAX_MEDIA_MS = 315_360_000_000

HELLO, HELLO_ACK = 0x01, 0x02
SNAPSHOT, STATE, SNAPSHOT_APPLIED, ARTWORK = 0x10, 0x11, 0x12, 0x13
COMMAND, COMMAND_RESULT = 0x20, 0x21
REQUEST_SNAPSHOT = 0x30
PING, PONG = 0x40, 0x41
ERROR, BYE = 0x7E, 0x7F

PLAY_PAUSE, PREVIOUS, NEXT, VOLUME_UP, VOLUME_DOWN = 1, 2, 3, 4, 5

NO_SESSION, STOPPED, PAUSED, PLAYING, BUFFERING = 0, 1, 2, 3, 4

DISPATCHED, NO_PLAYER, STALE_EPOCH, UNSUPPORTED = 0, 1, 2, 3
NOT_READY = 7


def crc(data: bytes) -> int:
    """CRC-32/ISO-HDLC, identical to zlib's CRC-32."""
    return zlib.crc32(data) & 0xFFFFFFFF


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


@dataclass(frozen=True)
class Frame:
    type: int
    session: int
    id: int
    payload: bytes = b""

    def encoded(self) -> bytes:
        if len(self.payload) > MAX_PAYLOAD or not self.session or not self.id:
            raise ValueError("invalid frame")
        header = MAGIC + struct.pack("<BBHII", VERSION, self.type, len(self.payload), self.session, self.id)
        body = header + self.payload
        return body + struct.pack("<I", crc(body[4:]))

    @staticmethod
    def decode(data: bytes) -> Frame | None:
        if len(data) < 20 or data[:4] != MAGIC or data[4] != VERSION:
            return None
        length = u16(data, 6)
        if length > MAX_PAYLOAD or len(data) != length + 20:
            return None
        if crc(data[4 : 16 + length]) != u32(data, 16 + length):
            return None
        return Frame(data[5], u32(data, 8), u32(data, 12), bytes(data[16 : 16 + length]))


class FrameStream:
    """Reassembles frames from indication chunks, resynchronising on garbage."""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def reset(self) -> None:
        self.buffer.clear()

    def feed(self, chunk: bytes) -> list[Frame]:
        if len(chunk) > CHARACTERISTIC_MAX:
            self.reset()
            return []
        self.buffer += chunk
        frames: list[Frame] = []
        while len(self.buffer) >= 4:
            if self.buffer[:4] != MAGIC:
                del self.buffer[0]
                continue
            if len(self.buffer) < 16:
                break
            length = u16(self.buffer, 6)
            if self.buffer[4] != VERSION or length > MAX_PAYLOAD:
                del self.buffer[0]
                continue
            if len(self.buffer) < length + 20:
                break
            frame = Frame.decode(bytes(self.buffer[: length + 20]))
            if frame:
                frames.append(frame)
                del self.buffer[: length + 20]
            else:
                del self.buffer[0]
        if len(self.buffer) > MAX_FRAME:
            self.reset()
        return frames


def chunks(frame: bytes) -> list[bytes]:
    return [frame[i : i + CHUNK] for i in range(0, len(frame), CHUNK)]
