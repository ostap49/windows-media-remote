# Windows Media Remote

A port of [Mac Media Remote](https://github.com/Vchekryzhov/mac-media-remote) to Windows.

The Flipper Zero shows what's playing on a Windows PC, received over Bluetooth Low Energy: track title, artist, album, playback progress, and cover art as a high-contrast poster. The Flipper's buttons control playback and the system volume. It works with any app or browser tab that appears in the Windows media flyout (the overlay next to the volume indicator), such as Spotify, YouTube in Chrome/Edge/Firefox, Windows Media Player, Apple Music, and VLC. Audio stays on the PC. USB is only needed to install the Flipper app.

## Requirements

- Flipper Zero on official firmware 1.4.3 (API 87.1) or later, with Bluetooth on and a microSD card.
- Windows 10 (1809 or later) or Windows 11 with Bluetooth 4.0+ LE.
- To run from source: Python 3.10 or later. The prebuilt `.exe` needs nothing else.

## Setup

### 1. Flipper app

Download `win_media_remote.fap` from the CI artifacts, or build it:

```sh
sh scripts/build-flipper.sh   # uses uFBT and the firmware 1.4.3 SDK
```

Copy it to `/ext/apps/Bluetooth/` with qFlipper, then open **Apps → Bluetooth → Win Media Remote**.

The companion also works with the original **Now Playing** app from the Flipper Apps Catalog. The protocol is the same; that app just says "Mac" on its screens.

### 2. Windows companion

Build a single executable:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1
dist\windows-media-remote.exe
```

Or run from source:

```powershell
pip install .\windows
windows-media-remote
```

### 3. Pairing

The first time the companion connects, the Flipper shows a six-digit code. Check it against the code printed in the companion's console, then press **OK** on the Flipper. The bond is saved on both sides, and later connections happen automatically.

If automatic pairing fails, pair manually: with the Flipper app open, go to **Settings → Bluetooth & devices → Add device → Bluetooth** on Windows, choose **NPW**, and confirm the code on both devices. Then start the companion.

To start the companion at sign-in, put a shortcut to `windows-media-remote.exe` in `shell:startup`.

## Controls

- **OK**: play or pause.
- **Left / Right**: previous or next track.
- **Up / Down**: system volume ±5%. Hold to repeat. Volume up also unmutes.
- **Hold Back**: exit the app.

Media is read from the session Windows considers current. Playback position comes from the player's timeline. Some browsers and players don't report one, and then the Flipper shows `--:--`. If Bluetooth drops, the Flipper marks the last track `Reconnecting` and the companion reconnects on its own.

## Troubleshooting

- **The Flipper stays on `Waiting for PC`.** Make sure the companion is running and look for a pairing code on the Flipper. Run `windows-media-remote -v` for detailed logs.
- **Pairing keeps failing after reinstalling the Flipper app.** Windows still holds the old bond. Remove **NPW** under **Bluetooth & devices**, then try again.
- **Nothing shows up for an app.** That app doesn't publish to Windows media controls. Check whether it appears in the volume flyout.

## How it works

```
Windows media session (GSMTC) ──► companion (Python, bleak) ══BLE══► Flipper app
Core Audio endpoint volume    ◄── commands from Flipper buttons ◄═══
```

- `windows/src/winmediaremote/media.py` reads Windows media sessions through `GlobalSystemMediaTransportControlsSessionManager`, and sends play/pause and track changes back to the player.
- `volume.py` changes the default output device's master volume through Core Audio (pycaw).
- `ble.py` scans for the Flipper's service UUID and pairs using numeric comparison through the WinRT pairing API. It then runs a session.
- `session.py` and `protocol.py` implement the FNP/1 protocol (`protocol/constants.json`). They match the Mac companion byte for byte.
- `flipper/win_media_remote` is the Flipper app. It is the Mac project's app with PC wording, its own app ID, and a separate BLE address and bond store.

Tests (`python -m pytest windows`) compile the Flipper's C protocol and model code. Every frame the companion produces is checked with the same validator the Flipper runs. A simulated Flipper then goes through the handshake, snapshots, artwork, and commands.

## License

GPL-3.0. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
