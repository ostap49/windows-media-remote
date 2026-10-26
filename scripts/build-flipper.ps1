# Builds the Flipper app with uFBT against the official firmware SDK (default 1.4.3).
# -Install also uploads it to a Flipper connected over USB and starts it
# (close qFlipper first so the serial port is free).
param(
    [string]$Firmware = "1.4.3",
    [switch]$Install
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".cache\venv"
if (-not (Test-Path $venv)) { python -m venv $venv }
$python = Join-Path $venv "Scripts\python.exe"
$ufbt = Join-Path $venv "Scripts\ufbt.exe"
& $python -m pip install --quiet --upgrade ufbt
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$env:UFBT_HOME = Join-Path $root ".cache\ufbt"
& $ufbt update --hw-target f7 --url "https://update.flipperzero.one/builds/firmware/$Firmware/flipper-z-f7-sdk-$Firmware.zip"
if ($LASTEXITCODE) { exit $LASTEXITCODE }

Push-Location (Join-Path $root "flipper\win_media_remote")
try {
    & $ufbt $(if ($Install) { "launch" } else { "build" })
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    $dist = Join-Path $root "dist"
    New-Item -ItemType Directory -Force $dist | Out-Null
    $fap = Join-Path $dist "win_media_remote-fw$Firmware.fap"
    Copy-Item "dist\win_media_remote.fap" $fap -Force
    $fap
} finally {
    Pop-Location
}
