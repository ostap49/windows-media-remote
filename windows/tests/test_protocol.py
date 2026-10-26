import io
import struct

from PIL import Image

from winmediaremote import artwork
from winmediaremote import protocol as fnp
from winmediaremote.playback import Playback, PlaybackStore, display_text


def test_crc_check_value():
    assert fnp.crc(b"123456789") == 0xCBF43926


def test_frame_roundtrip_and_stream_resync():
    frame = fnp.Frame(fnp.PING, 7, 9, b"\x01\x02\x03\x04")
    encoded = frame.encoded()
    assert fnp.Frame.decode(encoded) == frame
    stream = fnp.FrameStream()
    received = []
    for chunk in [b"junk"] + fnp.chunks(encoded + encoded):
        received += stream.feed(chunk)
    assert received == [frame, frame]


def test_display_text():
    assert display_text("Привет — мир", 192, unicode=True) == ("Привет   мир".encode(), True)
    assert display_text("Привет — мир", 192, unicode=False) == (b"Privet - mir", True)
    assert display_text("Café", 192, unicode=False) == (b"Cafe", True)
    data, changed = display_text("Я" * 200, 192, unicode=True)
    assert len(data) <= 192 and data.endswith(b"...") and changed
    data.decode()  # Truncation never splits a UTF-8 sequence.


def _playing(**overrides) -> Playback:
    values = dict(source="Spotify", title="Song", artist="Artist", album="Album",
                  state=fnp.PLAYING, position=10.0, duration=200.0, sampled=0.0)
    values.update(overrides)
    return Playback(**values)


def test_flipper_accepts_snapshots_and_states(flipper):
    store = PlaybackStore(volume_available=lambda: True)
    cases = [
        None,
        _playing(),
        _playing(title="Кино — Группа крови", artist="Кино", album="Ёлка"),
        _playing(title="x" * 500, state=fnp.PAUSED, position=None, duration=None),
        _playing(state=fnp.STOPPED, position=0.0, duration=None),
        _playing(state=fnp.BUFFERING, position=999.0),
        _playing(rate=2.0, position=300.0),
    ]
    for unicode in (True, False):
        for item in cases:
            store.update(item, now=0.0)
            for snapshot, kind in ((True, fnp.SNAPSHOT), (False, fnp.STATE)):
                payload = store.payload(snapshot=snapshot, unicode=unicode, now=5.0)
                wire = fnp.Frame(kind, 1, 1, payload).encoded()
                assert flipper.decode(wire) is not None, (item, unicode, snapshot)


def test_snapshot_reaches_flipper_model(flipper):
    store = PlaybackStore()
    store.update(_playing(title="Кино", artist="Artist"), now=0.0)
    frame = flipper.decode(fnp.Frame(fnp.SNAPSHOT, 1, 1, store.payload(True, True, now=2.0)).encoded())
    assert flipper.apply(frame) == 1
    model = flipper.model
    assert model.title.decode() == "Кино" and model.app == b"Spotify"
    assert model.state == fnp.PLAYING and model.position == 12_000 and model.duration == 200_000
    assert model.caps == 0b111  # No volume control available.


def _cover() -> bytes:
    image = Image.new("RGB", (300, 200), "white")
    for x in range(100, 200):
        for y in range(50, 150):
            image.putpixel((x, y), (10, 10, 10))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def test_artwork_is_accepted_and_rendered(flipper):
    store = PlaybackStore()
    store.update(_playing(), now=0.0)
    snapshot = flipper.decode(fnp.Frame(fnp.SNAPSHOT, 1, 1, store.payload(True, True)).encoded())
    assert flipper.apply(snapshot) == 1
    payload = artwork.payload(_cover(), store.epoch, store.revision)
    assert len(payload) == 282
    frame = flipper.decode(fnp.Frame(fnp.ARTWORK, 1, 2, payload).encoded())
    assert frame is not None and flipper.apply(frame) == 1 and flipper.model.has_artwork
    bits = bytes(flipper.model.artwork)
    black = lambda x, y: bool(bits[y * 6 + x // 8] & (1 << (x % 8)))
    assert black(22, 22) and not black(2, 22)
    empty = flipper.decode(fnp.Frame(fnp.ARTWORK, 1, 3, artwork.payload(None, store.epoch, store.revision)).encoded())
    assert empty is not None and flipper.apply(empty) == 1 and not flipper.model.has_artwork
    assert artwork.payload(b"not an image", 1, 1) == struct.pack("<II", 1, 1) + bytes(4)


def test_store_ignores_position_jitter_but_reports_seeks():
    events = []
    store = PlaybackStore()
    store.changed = lambda metadata, art: events.append((metadata, art))
    store.update(_playing(sampled=0.0), now=0.0)
    store.update(_playing(position=15.3, sampled=5.0), now=5.0)  # 0.3 s drift
    store.update(_playing(position=100.0, sampled=6.0), now=6.0)  # seek
    store.update(_playing(state=fnp.PAUSED, position=100.0, sampled=7.0), now=7.0)
    store.update(_playing(title="Next", sampled=8.0), now=8.0)
    assert events == [(True, False), (False, False), (False, False), (True, False)]
