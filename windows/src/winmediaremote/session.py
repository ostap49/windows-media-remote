"""One FNP session with a connected Flipper, independent of the BLE stack.

Mirrors the Mac companion: HELLO -> HELLO_ACK -> SNAPSHOT -> SNAPSHOT_APPLIED,
then STATE/ARTWORK updates, PING heartbeats, and COMMAND handling.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import struct
import time
from typing import Awaitable, Callable, Protocol

from . import artwork
from . import protocol as fnp
from .playback import PlaybackStore

log = logging.getLogger(__name__)

HEARTBEAT_S = 15.0
PEER_STALE_S = 35.0


class Controller(Protocol):
    def command(self, action: int) -> bool:
        """Dispatch a media command; False if unsupported."""


class SessionError(Exception):
    pass


class Session:
    def __init__(self, store: PlaybackStore, controller: Controller,
                 write: Callable[[bytes], Awaitable[None]]) -> None:
        self.store = store
        self.controller = controller
        self._write = write
        self.session_id = secrets.randbelow(0xFFFFFFFF) + 1
        self.next_id = 0
        self.last_peer_id = 0
        self.stage = "handshaking"
        self.ready = False
        self.unicode = False
        self.artwork = False
        self.latest_snapshot = (0, 0)
        self.command_results: dict[int, tuple[bytes, bytes]] = {}
        self.parser = fnp.FrameStream()
        self.last_peer = time.monotonic()
        self.outgoing: asyncio.Queue[bytes] = asyncio.Queue()
        self.failed: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    # Lifecycle -------------------------------------------------------------

    async def run(self) -> str:
        """Run until the session fails; returns the reason."""
        self.store.changed = self.publish
        writer = asyncio.create_task(self._writer())
        beat = asyncio.create_task(self._heartbeat())
        try:
            self._send(fnp.HELLO, struct.pack("<BBHHHI", 1, 3, fnp.MAX_PAYLOAD, fnp.CHARACTERISTIC_MAX, 0, 1))
            return await self.failed
        finally:
            self.store.changed = None
            writer.cancel()
            beat.cancel()
            await asyncio.gather(writer, beat, return_exceptions=True)

    def fail(self, reason: str) -> None:
        if not self.failed.done():
            log.info("Bluetooth: %s", reason)
            self.failed.set_result(reason)

    async def _writer(self) -> None:
        try:
            while True:
                frame = await self.outgoing.get()
                for chunk in fnp.chunks(frame):
                    await self._write(chunk)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # BLE write failures end the session.
            self.fail(f"write failed: {error}")

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            if self.stage != "ready":
                continue
            if time.monotonic() - self.last_peer > PEER_STALE_S:
                self.fail("peer timeout")
                return
            self._send(fnp.PING, secrets.token_bytes(4))
            self._send(fnp.STATE, self.store.payload(snapshot=False, unicode=self.unicode))

    # Outgoing --------------------------------------------------------------

    def _send(self, kind: int, payload: bytes) -> None:
        if self.failed.done():
            return
        if self.next_id == 0xFFFFFFFF:
            self.fail("counter exhausted")
            return
        self.next_id += 1
        if kind == fnp.SNAPSHOT:
            self.latest_snapshot = (self.next_id, fnp.u32(payload, 8))
        self.outgoing.put_nowait(fnp.Frame(kind, self.session_id, self.next_id, payload).encoded())

    def _snapshot(self) -> None:
        if self.stage not in ("syncing", "ready"):
            return
        self.ready = False
        self._send(fnp.SNAPSHOT, self.store.payload(snapshot=True, unicode=self.unicode))

    def _send_artwork(self) -> None:
        item = self.store.current
        if self.artwork and item is not None:
            self._send(fnp.ARTWORK, artwork.payload(item.artwork, self.store.epoch, self.store.revision))

    def publish(self, metadata_changed: bool, artwork_changed: bool) -> None:
        if self.stage != "ready":
            return
        if metadata_changed:
            self._snapshot()  # ARTWORK follows SNAPSHOT_APPLIED.
        else:
            self._send(fnp.STATE, self.store.payload(snapshot=False, unicode=self.unicode))
            if artwork_changed:
                self._send_artwork()

    # Incoming --------------------------------------------------------------

    def feed(self, chunk: bytes) -> None:
        for frame in self.parser.feed(bytes(chunk)):
            if self.failed.done():
                return
            self._receive(frame)

    def _receive(self, frame: fnp.Frame) -> None:
        if frame.session != self.session_id or frame.id == 0:
            self.fail("session mismatch")
            return
        if frame.type == fnp.COMMAND and frame.id in self.command_results:
            request, response = self.command_results[frame.id]
            if request == frame.payload:
                self._send(fnp.COMMAND_RESULT, response)
            else:
                self.fail("command ID reused")
            return
        if frame.id <= self.last_peer_id:
            self.fail("out of order frame")
            return
        self.last_peer_id = frame.id
        self.last_peer = time.monotonic()
        p = frame.payload
        if frame.type == fnp.HELLO_ACK:
            if self.stage != "handshaking" or len(p) != 12 or not 1 <= p[0] <= 3 or p[1] != 0:
                self.fail("HELLO rejected")
                return
            self.unicode = p[0] == 3
            self.artwork = p[0] >= 2
            self.stage = "syncing"
            log.info("Bluetooth: syncing (protocol v%d)", p[0])
            self._snapshot()
        elif frame.type == fnp.SNAPSHOT_APPLIED:
            if len(p) != 8:
                self.fail("bad snapshot ACK")
                return
            if (fnp.u32(p, 0), fnp.u32(p, 4)) == self.latest_snapshot:
                if self.stage != "ready":
                    log.info("Bluetooth: ready")
                self.stage = "ready"
                self.ready = True
                self._send_artwork()
        elif frame.type == fnp.COMMAND:
            self._command(frame)
        elif frame.type == fnp.REQUEST_SNAPSHOT:
            self._snapshot()
        elif frame.type == fnp.PONG:
            pass
        elif frame.type in (fnp.ERROR, fnp.BYE):
            self.fail("peer closed or rejected protocol")
        else:
            self.fail(f"unexpected frame 0x{frame.type:02x}")

    def _command(self, frame: fnp.Frame) -> None:
        p = frame.payload
        if len(p) != 12:
            self.fail("bad command")
            return
        target, action = fnp.u32(p, 0), p[8]
        current = self.store.current
        if not self.ready:
            status = fnp.NOT_READY
        elif current is None:
            status = fnp.NO_PLAYER
        elif target != self.store.epoch:
            status = fnp.STALE_EPOCH
        elif not 1 <= action <= 5:
            status = fnp.UNSUPPORTED
        else:
            status = fnp.DISPATCHED if self.controller.command(action) else fnp.UNSUPPORTED
        response = struct.pack("<IBBHI", frame.id, status, 0, 0, 0 if current is None else self.store.epoch)
        self.command_results[frame.id] = (p, response)
        if len(self.command_results) > 32:
            del self.command_results[min(self.command_results)]
        self._send(fnp.COMMAND_RESULT, response)
