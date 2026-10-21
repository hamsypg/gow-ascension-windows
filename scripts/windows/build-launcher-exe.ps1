# Packages the launcher as AscensionLauncher.exe (PyInstaller), a double-
# clickable alternative to scripts\windows\launcher.ps1 that needs no Python
# install on the machine that runs it. Builds only the .exe: the game itself
# still needs build.ps1 / build-gpu.ps1.
#
#   .\scripts\windows\build-launcher-exe.ps1
#
# The first run installs pyinstaller and pillow into a venv at
# launcher\.launcher-build-venv (kept between runs, so later builds are
# faster); delete that folder to start clean. The result,
# packaging\windows\dist\AscensionLauncher.exe, is also copied to the
# repository root -- that is where it is meant to live and run from (next to
# build\, mods\, docs\ and launcher\; see the FROZEN branch in
# launcher\app\config.py), not inside packaging\windows\dist\.

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Launcher = Join-Path $Root "launcher"
$Venv = Join-Path $Launcher ".launcher-build-venv"
$Spec = Join-Path $Root "packaging\windows\AscensionLauncher.spec"
$DistDir = Join-Path $Root "packaging\windows\dist"
$BuildDir = Join-Path $Root "packaging\windows\build"

if (-not (Test-Path $Venv)) {
    Write-Host "Setting up $Venv (first run only)…"
    python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$Py = Join-Path $Venv "Scripts\python.exe"
& $Py -m pip install --quiet --upgrade pip pyinstaller pillow
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Building AscensionLauncher.exe…"
& $Py -m PyInstaller $Spec --noconfirm --distpath $DistDir --workpath $BuildDir
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Built = Join-Path $DistDir "AscensionLauncher.exe"
$Target = Join-Path $Root "AscensionLauncher.exe"
Copy-Item $Built $Target -Force
Write-Host "Done: $Target"
Write-Host "Run it from the repository root, same as launcher.ps1 -- it reads and writes launcher\, build\, mods\ and gamedata\ beside it."
