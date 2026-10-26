# Builds the Flipper app with uFBT against the latest official firmware release.
# Use -Firmware 1.4.3 (etc.) if your Flipper runs an older release; the SDK API
# must match the firmware (Settings -> About), otherwise it shows "App Too Old".
# -Unleashed builds against the latest Unleashed release; -SdkUrl takes any SDK zip.
# -Install also uploads it to a Flipper connected over USB and starts it
# (close qFlipper first so the serial port is free).
param(
    [string]$Firmware = "release",
    [switch]$Install,
    [switch]$Unleashed,
    [string]$SdkUrl
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".cache\venv"
if (-not (Test-Path $venv)) { python -m venv $venv }
$python = Join-Path $venv "Scripts\python.exe"
$ufbt = Join-Path $venv "Scripts\ufbt.exe"
& $python -m pip install --quiet --upgrade ufbt
if ($LASTEXITCODE) { exit $LASTEXITCODE }

# Keep the toolchain at uFBT's default ~\.ufbt: inside a deep project folder its
# files exceed Windows' 260-character path limit and extraction fails.
if (-not $env:UFBT_HOME) { $env:UFBT_HOME = Join-Path $HOME ".ufbt" }
if ($SdkUrl) {
    & $ufbt update --hw-target f7 --url $SdkUrl
} elseif ($Unleashed) {
    $Firmware = "unleashed"
    & $ufbt update --hw-target f7 --index-url https://up.unleashedflip.com/directory.json --channel release
} elseif ($Firmware -eq "release") {
    & $ufbt update --hw-target f7 --channel release
} else {
    & $ufbt update --hw-target f7 --url "https://update.flipperzero.one/builds/firmware/$Firmware/flipper-z-f7-sdk-$Firmware.zip"
}
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
