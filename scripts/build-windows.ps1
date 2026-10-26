# Builds dist\windows-media-remote.exe (single file, no Python needed to run it).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".cache\venv"
if (-not (Test-Path $venv)) { python -m venv $venv }
$python = Join-Path $venv "Scripts\python.exe"
& $python -m pip install --upgrade pip | Out-Null
& $python -m pip install (Join-Path $root "windows") "pyinstaller>=6"
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $python -m PyInstaller --noconfirm --clean --onefile `
    --name windows-media-remote `
    --distpath (Join-Path $root "dist") `
    --workpath (Join-Path $root ".cache\pyinstaller") `
    --specpath (Join-Path $root ".cache\pyinstaller") `
    --collect-submodules winrt --collect-submodules bleak --collect-submodules pycaw `
    (Join-Path $root "windows\src\winmediaremote\__main__.py")
if ($LASTEXITCODE) { exit $LASTEXITCODE }
Join-Path $root "dist\windows-media-remote.exe"
