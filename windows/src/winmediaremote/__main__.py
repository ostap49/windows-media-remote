"""Windows Media Remote companion: Windows Now Playing -> Flipper Zero over BLE."""
from __future__ import annotations

import sys

if not hasattr(sys, "coinit_flags"):
    sys.coinit_flags = 0  # COINIT_MULTITHREADED, before anything imports comtypes.

import argparse
import asyncio
import logging

from . import __version__, protocol as fnp, volume
from .playback import PlaybackStore


class Controller:
    def __init__(self, media) -> None:
        self.media = media

    def command(self, action: int) -> bool:
        if action in (fnp.VOLUME_UP, fnp.VOLUME_DOWN):
            return volume.change(0.05 if action == fnp.VOLUME_UP else -0.05)
        return self.media.command(action)


async def main(address: str | None) -> None:
    from . import ble, media

    source = media.MediaSource()
    await source.start()
    store = PlaybackStore(volume_available=volume.available)
    poller = asyncio.create_task(media.poll(source, store))
    try:
        await ble.run(store, Controller(source), address)
    finally:
        poller.cancel()


def cli() -> None:
    parser = argparse.ArgumentParser(prog="windows-media-remote", description=__doc__)
    parser.add_argument("--address", help="connect only to this Bluetooth address (AA:BB:CC:DD:EE:FF)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(message)s", datefmt="%H:%M:%S",
    )
    if not args.verbose:
        logging.getLogger("bleak").setLevel(logging.WARNING)
    if sys.platform != "win32":
        parser.exit(1, "windows-media-remote runs on Windows 10 or 11.\n")
    try:
        asyncio.run(main(args.address))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
