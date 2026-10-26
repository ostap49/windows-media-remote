#!/bin/sh
# Builds the Flipper app against official firmware SDK (default 1.4.3) with uFBT.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tag=${FLIPPER_FIRMWARE_TAG:-1.4.3}
export UFBT_HOME=${UFBT_HOME:-"$root/.cache/ufbt"}
command -v ufbt >/dev/null 2>&1 || python3 -m pip install --user ufbt
ufbt update --hw-target f7 --url "https://update.flipperzero.one/builds/firmware/$tag/flipper-z-f7-sdk-$tag.zip"
cd "$root/flipper/win_media_remote"
ufbt
mkdir -p "$root/dist"
cp dist/win_media_remote.fap "$root/dist/win_media_remote-fw$tag.fap"
printf '%s\n' "$root/dist/win_media_remote-fw$tag.fap"
