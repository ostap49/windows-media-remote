# One-command install of the latest Windows Media Remote:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/ostap49/windows-media-remote/claude/relaxed-lamport-d4gd0x/scripts/install.ps1)))
# Downloads the source, builds the companion, puts it in $HOME\FlipperRemote and
# creates a desktop shortcut. -Flipper also builds the Flipper app and installs it
# over USB (add -Unleashed for Unleashed firmware). -Startup starts it at sign-in.
param(
    [string]$Branch = "claude/relaxed-lamport-d4gd0x",
    [switch]$Flipper,
    [switch]$Unleashed,
    [switch]$Startup
)
$ErrorActionPreference = "Stop"

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py -or $py.Source -like "*WindowsApps*") {
    Write-Host "Python is not installed. Install it from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "(tick 'Add python.exe to PATH'), then open a NEW PowerShell window and run this again." -ForegroundColor Red
    return
}

$install = Join-Path $HOME "FlipperRemote"
$source = Join-Path $install "source"
$zip = Join-Path $install "source.zip"
New-Item -ItemType Directory -Force $install | Out-Null

Write-Host "Downloading the latest version..." -ForegroundColor Cyan
Invoke-WebRequest "https://github.com/ostap49/windows-media-remote/archive/refs/heads/$Branch.zip" -OutFile $zip
$unpacked = Join-Path $install "unpacked"
Remove-Item -Recurse -Force $unpacked -ErrorAction SilentlyContinue
Expand-Archive $zip -DestinationPath $unpacked -Force
# Keep the build cache (Python environment) between updates.
$cache = Join-Path $source ".cache"
$keep = Join-Path $install "cache"
if (Test-Path $cache) { Remove-Item -Recurse -Force $keep -ErrorAction SilentlyContinue; Move-Item $cache $keep }
Remove-Item -Recurse -Force $source -ErrorAction SilentlyContinue
Move-Item (Get-ChildItem $unpacked | Select-Object -First 1).FullName $source
if (Test-Path $keep) { Move-Item $keep $cache }
Remove-Item -Recurse -Force $unpacked, $zip

Get-Process windows-media-remote -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "Building the Windows companion (a few minutes the first time)..." -ForegroundColor Cyan
& powershell -ExecutionPolicy Bypass -File (Join-Path $source "scripts\build-windows.ps1")
if ($LASTEXITCODE) { Write-Host "Build failed." -ForegroundColor Red; return }
$exe = Join-Path $install "windows-media-remote.exe"
Copy-Item (Join-Path $source "dist\windows-media-remote.exe") $exe -Force

if ($Flipper) {
    Write-Host "Building the Flipper app and installing it over USB (close qFlipper)..." -ForegroundColor Cyan
    $flipperArgs = @("-ExecutionPolicy", "Bypass", "-File", (Join-Path $source "scripts\build-flipper.ps1"), "-Install")
    if ($Unleashed) { $flipperArgs += "-Unleashed" }
    & powershell @args
    if ($LASTEXITCODE) { Write-Host "Flipper app build failed." -ForegroundColor Red }
}

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Flipper Media Remote.lnk"))
$link.TargetPath = $exe
$link.WorkingDirectory = $install
$link.Save()
if ($Startup) { Copy-Item $link.FullName ([Environment]::GetFolderPath("Startup")) -Force }

Write-Host "Done: $exe" -ForegroundColor Green
Write-Host "Open Win Media Remote on the Flipper, then double-click 'Flipper Media Remote' on the desktop." -ForegroundColor Green
