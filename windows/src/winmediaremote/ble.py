"""Bluetooth LE central: find the Flipper, pair, and run FNP sessions forever."""
from __future__ import annotations

import asyncio
import logging

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from . import protocol as fnp
from .playback import PlaybackStore
from .session import Controller, Session

log = logging.getLogger(__name__)

SCAN_TIMEOUT_S = 10.0
CONNECT_TIMEOUT_S = 30.0
WRITE_TIMEOUT_S = 30.0  # Covers the first write while pairing is confirmed on the Flipper.
RETRY_S = 2.0


def is_flipper(device: BLEDevice, advertisement: AdvertisementData, address: str | None = None) -> bool:
    if address:
        return device.address.upper() == address.upper()
    uuids = [uuid.lower() for uuid in advertisement.service_uuids]
    name = advertisement.local_name or device.name or ""
    return fnp.SERVICE in uuids or name in fnp.ADVERTISED_NAMES


async def pair(address: str) -> None:
    """Pair with numeric comparison: the Flipper shows a code and asks to confirm it.

    bleak's own pair() only offers Windows the "confirm only" ceremony, which
    Windows rejects for the Flipper's authenticated (MITM-protected) pairing.
    """
    from winrt.windows.devices.bluetooth import BluetoothLEDevice
    from winrt.windows.devices.enumeration import (
        DeviceInformation,
        DevicePairingKinds,
        DevicePairingProtectionLevel,
        DevicePairingResultStatus,
    )

    device = await BluetoothLEDevice.from_bluetooth_address_async(int(address.replace(":", ""), 16))
    if device is None:
        raise RuntimeError("device not found for pairing")
    try:
        info = await DeviceInformation.create_from_id_async(device.device_id)
        if info.pairing.is_paired:
            return
        custom = info.pairing.custom

        def requested(_sender, args) -> None:
            if args.pairing_kind == DevicePairingKinds.CONFIRM_PIN_MATCH:
                log.info("Pairing: check that the Flipper shows %s and press OK on it", args.pin)
            args.accept()

        token = custom.add_pairing_requested(requested)
        try:
            log.info("Pairing: confirm on the Flipper")
            result = await custom.pair_async(
                DevicePairingKinds.CONFIRM_ONLY | DevicePairingKinds.CONFIRM_PIN_MATCH,
                DevicePairingProtectionLevel.ENCRYPTION_AND_AUTHENTICATION,
            )
        finally:
            custom.remove_pairing_requested(token)
        if result.status not in (DevicePairingResultStatus.PAIRED, DevicePairingResultStatus.ALREADY_PAIRED):
            raise RuntimeError(f"pairing failed ({result.status.name})")
        log.info("Pairing: done")
    finally:
        device.close()


async def _connect_once(device: BLEDevice, store: PlaybackStore, controller: Controller) -> str:
    disconnected = asyncio.Event()
    await pair(device.address)
    async with BleakClient(
        device,
        disconnected_callback=lambda _client: disconnected.set(),
        timeout=CONNECT_TIMEOUT_S,
        winrt={"use_cached_services": False},
    ) as client:
        async def write(chunk: bytes) -> None:
            await asyncio.wait_for(client.write_gatt_char(fnp.RX, chunk, response=True), WRITE_TIMEOUT_S)

        session = Session(store, controller, write)
        log.info("Bluetooth: subscribing")
        await client.start_notify(fnp.TX, lambda _char, data: session.feed(bytes(data)))
        log.info("Bluetooth: handshaking")
        run = asyncio.create_task(session.run())
        lost = asyncio.create_task(disconnected.wait())
        try:
            done, _ = await asyncio.wait({run, lost}, return_when=asyncio.FIRST_COMPLETED)
            return run.result() if run in done else "disconnected"
        finally:
            session.fail("closing")
            for task in (run, lost):
                task.cancel()
            await asyncio.gather(run, lost, return_exceptions=True)


async def run(store: PlaybackStore, controller: Controller, address: str | None = None) -> None:
    while True:
        log.info("Bluetooth: scanning for the Flipper app")
        device = await BleakScanner.find_device_by_filter(
            lambda d, adv: is_flipper(d, adv, address), timeout=SCAN_TIMEOUT_S
        )
        if device is None:
            continue
        log.info("Bluetooth: connecting to %s (%s)", device.name or "Flipper", device.address)
        try:
            reason = await _connect_once(device, store, controller)
            log.info("Bluetooth: session ended: %s", reason)
        except Exception as error:
            log.warning("Bluetooth: %s", error or type(error).__name__)
        store.reset_connection()
        await asyncio.sleep(RETRY_S)
