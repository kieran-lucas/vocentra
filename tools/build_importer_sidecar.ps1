<#
.SYNOPSIS
Builds the standalone vocabulary importer that ships inside the Windows app.

The installed app must import JSON with no Python, no uv and no source checkout,
so the same importer core is frozen into one executable and placed where Tauri's
externalBin picks it up. FFmpeg and FFprobe travel with it, because the audio
pipeline must not depend on the user's PATH.

Fails loudly rather than producing a half-working installer.
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [string]$Target = 'x86_64-pc-windows-msvc'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$binaries = Join-Path $repo 'src-tauri/binaries'
$ffmpegStage = Join-Path $repo 'src-tauri/ffmpeg'
$vendor = Join-Path $repo 'tools/vendor/ffmpeg'
$work = Join-Path $repo 'src-tauri/target/sidecar'
$sidecar = Join-Path $binaries "lexium-import-$Target.exe"

function Resolve-FfmpegSource {
    param([string]$Name)
    $vendored = Join-Path $vendor "$Name.exe"
    if (Test-Path $vendored) { return (Resolve-Path $vendored).Path }
    $onPath = Get-Command $Name -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    $winget = Join-Path $env:LOCALAPPDATA 'Microsoft/WinGet/Packages'
    if (Test-Path $winget) {
        $found = Get-ChildItem -Path $winget -Filter "$Name.exe" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    throw "$Name.exe was not found. Put a slim build in tools/vendor/ffmpeg/ (recommended) or install FFmpeg."
}

# --- inputs -----------------------------------------------------------------
$entry = Join-Path $repo 'tools/ingest/import_external_vocabulary.py'
$schema = Join-Path $repo 'tools/schemas/external_vocabulary_import.v1.schema.json'
foreach ($required in @($entry, $schema)) {
    if (-not (Test-Path $required)) { throw "Missing input: $required" }
}
$ffmpeg = Resolve-FfmpegSource -Name 'ffmpeg'
$ffprobe = Resolve-FfmpegSource -Name 'ffprobe'
Write-Host "ffmpeg  : $ffmpeg"
Write-Host "ffprobe : $ffprobe"

# --- skip when already current ---------------------------------------------
$sources = Get-ChildItem -Path (Join-Path $repo 'tools/ingest') -Filter '*.py' -File
$stampInputs = @($sources.FullName) + @($schema, $ffmpeg, $ffprobe)
$stampValue = ($stampInputs | ForEach-Object { (Get-FileHash $_ -Algorithm SHA256).Hash }) -join ''
$stamp = Join-Path $work 'inputs.sha256'
if (-not $Force -and (Test-Path $sidecar) -and (Test-Path $stamp) -and
    ((Get-Content $stamp -Raw).Trim() -eq $stampValue)) {
    Write-Host "Sidecar is current: $sidecar"
    exit 0
}

# --- build ------------------------------------------------------------------
New-Item -ItemType Directory -Force $binaries, $work | Out-Null
Write-Host 'Freezing the importer with PyInstaller...'
$pyArgs = @(
    'run', '--quiet',
    '--with', 'pyinstaller',
    '--with', 'edge-tts==7.2.7',
    '--with', 'jsonschema>=4,<5',
    'pyinstaller', '--noconfirm', '--clean', '--onefile', '--console',
    '--name', 'lexium-import',
    '--distpath', (Join-Path $work 'dist'),
    '--workpath', (Join-Path $work 'build'),
    '--specpath', $work,
    '--paths', $repo,
    '--add-data', "$schema;tools/schemas",
    '--collect-all', 'edge_tts',
    '--collect-all', 'jsonschema',
    '--collect-all', 'jsonschema_specifications',
    '--collect-all', 'certifi',
    '--hidden-import', 'tools.ingest.audio_encode',
    '--hidden-import', 'tools.ingest.audio_microsoft',
    '--hidden-import', 'tools.ingest.audio_profile',
    '--hidden-import', 'tools.ingest.audio_service',
    '--hidden-import', 'tools.ingest.db',
    '--hidden-import', 'tools.ingest.external_schema',
    $entry
)
& uv @pyArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$built = Join-Path $work 'dist/lexium-import.exe'
if (-not (Test-Path $built)) { throw "PyInstaller reported success but $built does not exist" }

# --- smoke test the frozen binary before shipping it ------------------------
Write-Host 'Smoke-testing the frozen importer...'
$fixture = Join-Path $repo 'tools/ingest/tests/fixtures/external/canonical_batch.json'
& $built $fixture --validate-only | Out-Null
if ($LASTEXITCODE -ne 0) { throw "The frozen importer failed --validate-only on the canonical fixture" }

# --- publish where Tauri's externalBin expects it ---------------------------
# externalBin matches <name>-<target triple>.exe and installs it beside the app
# executable as <name>.exe.
Copy-Item $built $sidecar -Force

# FFmpeg travels as a bundled resource folder next to the executable, which is
# the first place tools/ingest/audio_encode.py looks.
New-Item -ItemType Directory -Force $ffmpegStage | Out-Null
Get-ChildItem $ffmpegStage -File -ErrorAction SilentlyContinue | Remove-Item -Force
Copy-Item $ffmpeg (Join-Path $ffmpegStage 'ffmpeg.exe') -Force
Copy-Item $ffprobe (Join-Path $ffmpegStage 'ffprobe.exe') -Force
$support = Get-ChildItem -Path (Split-Path -Parent $ffmpeg) -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in '.dll', '.txt' }
foreach ($item in $support) { Copy-Item $item.FullName (Join-Path $ffmpegStage $item.Name) -Force }
$stagedMb = [math]::Round((Get-ChildItem $ffmpegStage -File | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "Staged FFmpeg ($($support.Count) support file(s), $stagedMb MB) in $ffmpegStage"
Set-Content -Path $stamp -Value $stampValue -Encoding utf8

$size = [math]::Round((Get-Item $sidecar).Length / 1MB, 1)
Write-Host "Sidecar ready: $sidecar ($size MB)"
Write-Host "Release layout: <app>/lexium-import.exe and <app>/ffmpeg/"
