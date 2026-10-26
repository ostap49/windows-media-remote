"""Smoke tests against the real Windows APIs; skipped elsewhere."""
import asyncio
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_media_session_api():
    from winmediaremote.media import MediaSource

    async def read():
        source = MediaSource()
        try:
            await source.start()
        except OSError as error:  # Server SKUs may lack the media session broker.
            pytest.skip(f"GSMTC unavailable: {error}")
        return await source.snapshot()

    result = asyncio.run(read())
    assert result is None or result.title


def test_volume_api_does_not_raise():
    from winmediaremote import volume

    assert volume.available() in (True, False)


def test_winrt_pairing_types_import():
    from winrt.windows.devices.bluetooth import BluetoothLEDevice  # noqa: F401
    from winrt.windows.devices.enumeration import DevicePairingKinds

    assert DevicePairingKinds.CONFIRM_PIN_MATCH
