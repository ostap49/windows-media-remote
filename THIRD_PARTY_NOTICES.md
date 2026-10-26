# Third-party notices

- This project ports [Vchekryzhov/mac-media-remote](https://github.com/Vchekryzhov/mac-media-remote) (GPL-3.0) to Windows. `flipper/win_media_remote` and `protocol/constants.json` come from that project. The Windows companion is a Python reimplementation of its Swift Mac companion.
- `flipper/win_media_remote` in turn adapts [villenull/flipper-now-playing](https://github.com/villenull/flipper-now-playing), licensed under GPL-3.0. The original copyright belongs to its contributors.
- `flipper/win_media_remote/ui/np_cyrillic_font.c` embeds the public-domain `u8g2_font_6x12_t_cyrillic` font from official Flipper Zero firmware 1.4.3 (`lib/u8g2/u8g2_fonts.c`).
- The Flipper build uses the official [flipperdevices/flipperzero-firmware](https://github.com/flipperdevices/flipperzero-firmware) SDK under GPL-3.0. The SDK is a build dependency and is not part of this repository.
- The Windows companion depends on [bleak](https://github.com/hbldh/bleak) (MIT), [pywinrt](https://github.com/pywinrt/pywinrt) (MIT), [pycaw](https://github.com/AndreMiras/pycaw) (MIT), and [Pillow](https://python-pillow.org) (MIT-CMU). They are installed separately. A PyInstaller build bundles them.

This repository is distributed under GPL-3.0; see [LICENSE](LICENSE).
