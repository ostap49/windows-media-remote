from datetime import datetime, timedelta, timezone

from winmediaremote.media import source_name, timeline


def test_source_names():
    assert source_name("Spotify.exe") == "Spotify"
    assert source_name("308046B0AF4A39CB") == "Firefox"
    assert source_name("Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic") == "Media Player"
    assert source_name(r"C:\Program Files\Foo\Player.exe") == "Player"
    assert source_name("") == "PC"


def test_timeline_extrapolates_only_while_playing():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    updated = now - timedelta(seconds=4)
    assert timeline(30, 0, 200, updated, True, 1.0, now) == (34, 200)
    assert timeline(30, 0, 200, updated, False, 1.0, now) == (30, 200)
    assert timeline(199, 0, 200, updated, True, 1.0, now) == (200, 200)


def test_timeline_without_data():
    never = datetime(1601, 1, 1, tzinfo=timezone.utc)
    assert timeline(0, 0, 0, never, True, 1.0) == (None, None)
    assert timeline(12, 0, 0, never, True, 1.0) == (12, None)
