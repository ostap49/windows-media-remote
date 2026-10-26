"""Media state model and the SNAPSHOT/STATE payloads sent to the Flipper."""
from __future__ import annotations

import logging
import struct
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

from . import protocol as fnp

log = logging.getLogger(__name__)

FIELD_MAX = (192, 128, 192, 48)  # title, artist, album, app
POSITION_DRIFT_S = 1.5


@dataclass(frozen=True)
class Playback:
    source: str = "PC"
    title: str = ""
    artist: str = ""
    album: str = ""
    state: int = fnp.PAUSED  # protocol playback state: STOPPED, PAUSED, PLAYING or BUFFERING
    rate: float = 1.0
    position: float | None = None  # seconds at `sampled`
    duration: float | None = None
    sampled: float = field(default_factory=time.monotonic, compare=False)
    artwork: bytes | None = field(default=None, compare=False)

    @property
    def playing(self) -> bool:
        return self.state == fnp.PLAYING

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (self.source, self.title, self.artist, self.album)

    def position_at(self, now: float) -> float | None:
        if self.position is None:
            return None
        position = self.position + ((now - self.sampled) * self.rate if self.playing else 0.0)
        if self.duration is not None:
            position = min(position, self.duration)
        return max(0.0, position)


_CYRILLIC_TO_LATIN = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюяіїєґ",
    "a b v g d e e zh z i y k l m n o p r s t u f kh ts ch sh shch _ y _ e yu ya i yi ye g".split(),
))
_PUNCTUATION = {"—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "..."}


def _to_latin(text: str) -> str:
    out = []
    for char in text:
        lower = char.lower()
        if lower in _CYRILLIC_TO_LATIN:
            latin = _CYRILLIC_TO_LATIN[lower].replace("_", "")
            out.append(latin.capitalize() if char != lower else latin)
        else:
            out.append(_PUNCTUATION.get(char, char))
    decomposed = unicodedata.normalize("NFKD", "".join(out))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def display_text(text: str, max_bytes: int, unicode: bool) -> tuple[bytes, bool]:
    """Encode text the Flipper can render; returns (bytes, changed).

    Protocol v3 accepts printable ASCII plus UTF-8 Cyrillic U+0400..U+047F.
    Older peers receive transliterated ASCII.
    """
    if not unicode:
        text_in = _to_latin(text)
    else:
        text_in = text
    chars = []
    for char in text_in:
        code = ord(char)
        if 32 <= code <= 126 or (unicode and 0x400 <= code <= 0x47F):
            chars.append(char)
        else:
            chars.append(" ")
    cleaned = " ".join("".join(chars).split()) if not unicode else "".join(chars)
    encoded = cleaned.encode()
    if len(encoded) > max_bytes:
        limit = max(0, max_bytes - 3)
        cut = encoded[:limit].decode("utf-8", errors="ignore")
        encoded = cut.encode() + b"..."
    return encoded, encoded.decode() != text


class PlaybackStore:
    """Holds the current media item and the counters the Flipper validates."""

    def __init__(self, volume_available: Callable[[], bool] = lambda: False) -> None:
        self.current: Playback | None = None
        self.epoch = 1
        self.revision = 1
        self.sequence = 0
        self.volume_available = volume_available
        self.changed: Callable[[bool, bool], None] | None = None

    def update(self, nxt: Playback | None, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        cur = self.current
        metadata_changed = (cur.identity if cur else None) != (nxt.identity if nxt else None)
        artwork_changed = (cur.artwork if cur else None) != (nxt.artwork if nxt else None)
        state_changed = metadata_changed or artwork_changed or self._state_changed(cur, nxt, now)
        if metadata_changed:
            self.revision = 1 if self.revision == 0xFFFFFFFF else self.revision + 1
            if nxt:
                log.info("Media: [%s] %s - %s", nxt.source, nxt.artist, nxt.title)
            else:
                log.info("Media: inactive")
        if state_changed:  # Otherwise keep the old timeline anchor; it still extrapolates correctly.
            self.current = nxt
        if state_changed and self.changed:
            self.changed(metadata_changed, artwork_changed)

    @staticmethod
    def _state_changed(cur: Playback | None, nxt: Playback | None, now: float) -> bool:
        if cur is None or nxt is None:
            return cur is not nxt
        if (cur.state, cur.rate, cur.duration, cur.position is None) != (
            nxt.state, nxt.rate, nxt.duration, nxt.position is None
        ):
            return True
        predicted, actual = cur.position_at(now), nxt.position_at(now)
        return predicted is not None and actual is not None and abs(predicted - actual) > POSITION_DRIFT_S

    def reset_connection(self) -> None:
        self.epoch = 1 if self.epoch == 0xFFFFFFFF else self.epoch + 1
        self.sequence = 0

    def payload(self, snapshot: bool, unicode: bool, now: float | None = None) -> bytes:
        now = time.monotonic() if now is None else now
        self.sequence = 1 if self.sequence == 0xFFFFFFFF else self.sequence + 1
        item = self.current
        texts = (item.title, item.artist, item.album, item.source) if item else ("", "", "", "PC")
        fields = [display_text(t, m, unicode) for t, m in zip(texts, FIELD_MAX)]
        if item is None:
            body = struct.pack("<IIIBBhQQHBB", 0, 0, self.sequence, fnp.NO_SESSION, 0, 0, 0, 0, 0, 0, 0)
        else:
            raw_position = item.position_at(now)
            position = None
            if raw_position is not None:
                position = int(min(raw_position * 1000, fnp.MAX_MEDIA_MS))
            duration = None
            if item.duration is not None and item.duration > 0:
                duration = int(min(item.duration * 1000, fnp.MAX_MEDIA_MS))
            if position is not None and duration is not None:
                position = min(position, duration)
            flags = (1 if position is not None else 0) | (2 if duration is not None else 0)
            flags |= 4 if any(changed for _, changed in fields) else 0
            speed = int(max(-8000, min(8000, round(item.rate * 1000)))) if item.playing else 0
            caps = 0b11111 if self.volume_available() else 0b00111
            body = struct.pack(
                "<IIIBBhQQHBB",
                self.epoch, self.revision, self.sequence,
                item.state,
                flags, speed, position or 0, duration or 0, caps, 0, 0,
            )
        if snapshot:
            body += struct.pack("<4H", *(len(data) for data, _ in fields))
            body += b"".join(data for data, _ in fields)
        return body
