"""Windows system media session (GSMTC): what is playing, and transport commands.

This is the same source that feeds the Windows volume flyout and lock screen, so
any app or browser tab that shows up there appears on the Flipper.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from . import protocol as fnp
from .playback import Playback

log = logging.getLogger(__name__)

MAX_THUMBNAIL_BYTES = 4 * 1024 * 1024
THUMBNAIL_READS = 3  # Apps often publish the new cover a moment after the title.

_KNOWN_APPS = {
    "spotify.exe": "Spotify",
    "spotify": "Spotify",
    "chrome": "Chrome",
    "msedge": "Edge",
    "308046b0af4a39cb": "Firefox",
    "firefox.exe": "Firefox",
    "brave": "Brave",
    "opera": "Opera",
    "vlc.exe": "VLC",
    "foobar2000.exe": "foobar2000",
    "aimp.exe": "AIMP",
    "microsoft.zunemusic_8wekyb3d8bbwe!microsoft.zunemusic": "Media Player",
    "applemusic": "Apple Music",
    "ru.yandex.desktop.music": "Яндекс Музыка",
}


def source_name(app_id: str) -> str:
    known = _KNOWN_APPS.get(app_id.lower())
    if known:
        return known
    name = app_id.split("!")[-1].rsplit("\\", 1)[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    name = name.split(".")[-1] if "." in name else name
    return name or "PC"


def _state(status: int) -> int:
    # GlobalSystemMediaTransportControlsSessionPlaybackStatus:
    # CLOSED 0, OPENED 1, CHANGING 2, STOPPED 3, PLAYING 4, PAUSED 5
    return {2: fnp.BUFFERING, 3: fnp.STOPPED, 4: fnp.PLAYING}.get(int(status), fnp.PAUSED)


def timeline(position: float, start: float, end: float, updated: datetime | None,
             playing: bool, rate: float, now: datetime | None = None) -> tuple[float | None, float | None]:
    """Current (position, duration) in seconds from GSMTC timeline properties."""
    duration = end - start if end > start else None
    current: float | None = position - start
    if duration is None and current <= 0:
        return None, None
    if playing and updated is not None and updated.year > 2000:
        now = now or datetime.now(timezone.utc)
        elapsed = (now - updated).total_seconds()
        if 0 < elapsed < 24 * 3600:
            current += elapsed * rate
    current = max(0.0, current)
    if duration is not None:
        current = min(current, duration)
    return current, duration


class MediaSource:
    def __init__(self) -> None:
        self.manager = None
        self._thumbnail_key: tuple | None = None
        self._thumbnail: bytes | None = None
        self._thumbnail_reads = 0
        self._tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager,
        )
        self.manager = await Manager.request_async()

    def _session(self):
        if self.manager is None:
            return None
        session = self.manager.get_current_session()
        if session is not None:
            return session
        for candidate in self.manager.get_sessions():
            if int(candidate.get_playback_info().playback_status) == 4:
                return candidate
        return None

    async def snapshot(self) -> Playback | None:
        session = self._session()
        if session is None:
            return None
        properties = await session.try_get_media_properties_async()
        if properties is None or not properties.title:
            return None
        info = session.get_playback_info()
        state = _state(info.playback_status)
        rate = info.playback_rate or 1.0
        line = session.get_timeline_properties()
        position, duration = timeline(
            line.position.total_seconds(), line.start_time.total_seconds(), line.end_time.total_seconds(),
            line.last_updated_time, state == fnp.PLAYING, rate,
        )
        source = source_name(session.source_app_user_model_id or "")
        album = properties.album_title or ""
        key = (source, properties.title, properties.artist, album)
        if key != self._thumbnail_key:
            self._thumbnail_key, self._thumbnail, self._thumbnail_reads = key, None, 0
        if self._thumbnail_reads < THUMBNAIL_READS:
            self._thumbnail_reads += 1
            fresh = await self._read_thumbnail(properties.thumbnail)
            if fresh is not None:
                self._thumbnail = fresh
        return Playback(
            source=source, title=properties.title, artist=properties.artist or "", album=album,
            state=state, rate=rate, position=position, duration=duration,
            sampled=time.monotonic(), artwork=self._thumbnail,
        )

    @staticmethod
    async def _read_thumbnail(reference) -> bytes | None:
        if reference is None:
            return None
        try:
            from winrt.windows.storage.streams import DataReader

            stream = await reference.open_read_async()
            size = int(stream.size)
            if not 0 < size <= MAX_THUMBNAIL_BYTES:
                return None
            reader = DataReader(stream.get_input_stream_at(0))
            await reader.load_async(size)
            return bytes(reader.read_buffer(size))
        except Exception as error:
            log.debug("thumbnail unavailable: %s", error)
            return None

    def command(self, action: int) -> bool:
        session = self._session()
        if session is None:
            return False
        calls = {
            fnp.PLAY_PAUSE: session.try_toggle_play_pause_async,
            fnp.PREVIOUS: session.try_skip_previous_async,
            fnp.NEXT: session.try_skip_next_async,
        }
        call = calls.get(action)
        if call is None:
            return False

        async def dispatch() -> None:
            try:
                if not await call():
                    log.info("Media: player ignored command %d", action)
            except Exception as error:
                log.warning("Media: command %d failed: %s", action, error)

        task = asyncio.get_running_loop().create_task(dispatch())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True


async def poll(source: MediaSource, store, interval: float = 1.0) -> None:
    while True:
        try:
            store.update(await source.snapshot())
        except Exception as error:
            log.warning("Media: read failed: %s", error)
            store.update(None)
        await asyncio.sleep(interval)
