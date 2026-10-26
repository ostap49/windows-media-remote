"""Default playback device master volume through Core Audio (IAudioEndpointVolume)."""
from __future__ import annotations

import logging
import sys
import time

log = logging.getLogger(__name__)

# comtypes initialises COM when first imported. WinRT (bleak, media session)
# needs a multithreaded apartment, so request MTA before pycaw loads comtypes.
if not hasattr(sys, "coinit_flags"):
    sys.coinit_flags = 0  # COINIT_MULTITHREADED

_CACHE_S = 5.0
_cached: tuple[float, bool] = (-_CACHE_S, False)


def _endpoint():
    from pycaw.pycaw import AudioUtilities

    return AudioUtilities.GetSpeakers().EndpointVolume


def available() -> bool:
    global _cached
    now = time.monotonic()
    if now - _cached[0] >= _CACHE_S:
        try:
            _endpoint().GetMasterVolumeLevelScalar()
            _cached = (now, True)
        except Exception:
            _cached = (now, False)
    return _cached[1]


def change(step: float) -> bool:
    try:
        endpoint = _endpoint()
        level = min(1.0, max(0.0, endpoint.GetMasterVolumeLevelScalar() + step))
        endpoint.SetMasterVolumeLevelScalar(level, None)
        if step > 0 and endpoint.GetMute():
            endpoint.SetMute(0, None)
        return True
    except Exception as error:
        log.warning("Volume: %s", error)
        return False
