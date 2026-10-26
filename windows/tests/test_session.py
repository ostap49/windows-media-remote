"""Drives a Session against a simulated Flipper that follows win_media_remote.c."""
import asyncio
import struct

from winmediaremote import protocol as fnp
from winmediaremote.playback import Playback, PlaybackStore
from winmediaremote.session import Session


class FakeController:
    def __init__(self):
        self.actions = []

    def command(self, action):
        self.actions.append(action)
        return True


class SimulatedFlipper:
    def __init__(self, flipper):
        self.c = flipper
        self.stream = fnp.FrameStream()
        self.session = None
        self.tx_id = 0
        self.received = []
        self.session_obj = None

    def send(self, kind, payload):
        self.tx_id += 1
        wire = self.c.encode(kind, self.session, self.tx_id, payload)
        for chunk in fnp.chunks(wire):
            self.session_obj.feed(chunk)

    async def write(self, chunk):
        assert len(chunk) <= 20
        for frame in self.stream.feed(chunk):
            decoded = self.c.decode(frame.encoded())
            assert decoded is not None, f"Flipper rejects frame type 0x{frame.type:02x}"
            self.received.append(frame)
            if frame.type == fnp.HELLO:
                self.session = frame.session
                self.send(fnp.HELLO_ACK, bytes([3, 0, 0, 3, 128, 0, 0, 0, 1, 0, 0, 0]))
            elif frame.type in (fnp.SNAPSHOT, fnp.STATE, fnp.ARTWORK):
                assert self.c.apply(decoded) == 1
                if frame.type == fnp.SNAPSHOT:
                    self.send(fnp.SNAPSHOT_APPLIED, struct.pack("<II", frame.id, fnp.u32(frame.payload, 8)))


def test_handshake_snapshot_artwork_and_commands(flipper):
    async def scenario():
        store = PlaybackStore(volume_available=lambda: True)
        store.update(Playback(source="Spotify", title="Song", artist="Artist", state=fnp.PLAYING,
                              position=1.0, duration=10.0, artwork=None))
        controller = FakeController()
        peer = SimulatedFlipper(flipper)
        session = Session(store, controller, peer.write)
        peer.session_obj = session
        runner = asyncio.create_task(session.run())
        for _ in range(50):
            await asyncio.sleep(0)
        assert session.stage == "ready" and flipper.model.title == b"Song"
        types = [f.type for f in peer.received]
        assert types == [fnp.HELLO, fnp.SNAPSHOT, fnp.ARTWORK]

        peer.send(fnp.COMMAND, struct.pack("<IIBBH", store.epoch, store.revision, fnp.NEXT, 0, 700))
        peer.send(fnp.COMMAND, struct.pack("<IIBBH", store.epoch + 1, store.revision, fnp.NEXT, 0, 700))
        peer.send(fnp.COMMAND, struct.pack("<IIBBH", store.epoch, store.revision, fnp.VOLUME_UP, 1, 300))
        store.update(Playback(source="Spotify", title="Other", state=fnp.PAUSED))
        for _ in range(50):
            await asyncio.sleep(0)
        results = [f.payload[4] for f in peer.received if f.type == fnp.COMMAND_RESULT]
        assert results == [fnp.DISPATCHED, fnp.STALE_EPOCH, fnp.DISPATCHED]
        assert controller.actions == [fnp.NEXT, fnp.VOLUME_UP]
        assert flipper.model.title == b"Other" and flipper.model.state == fnp.PAUSED

        peer.send(fnp.BYE, b"\x01")
        assert await asyncio.wait_for(runner, 1) == "peer closed or rejected protocol"
        assert store.changed is None

    asyncio.run(scenario())
