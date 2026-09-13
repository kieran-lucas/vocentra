[CmdletBinding()]
param([switch]$VerifyOnly)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$version = (Get-Content (Join-Path $repo 'src-tauri/tauri.conf.json') -Raw | ConvertFrom-Json).version
$installer = Join-Path $repo "src-tauri/target/release/bundle/nsis/Lexium_${version}_x64-setup.exe"
$built = Join-Path $repo 'src-tauri/target/release/lexium.exe'
$installDirectory = Join-Path $env:LOCALAPPDATA 'Lexium'
$installed = Join-Path $installDirectory 'lexium.exe'
if (!(Test-Path -LiteralPath $installer) -or !(Test-Path -LiteralPath $built)) { throw 'Build the release installer first.' }
if ((Get-Item -LiteralPath $built).VersionInfo.ProductVersion -ne $version) { throw 'Release executable version does not match the installer.' }

if (!$VerifyOnly) {
$running = Get-Process -Name lexium -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $installed }
foreach ($process in $running) {
    [void]$process.CloseMainWindow()
    if (!$process.WaitForExit(15000)) { throw 'Lexium did not close. Finish the active operation before upgrading.' }
}

# NSIS update mode replaces binaries in place and preserves application data.
$setup = Start-Process -FilePath $installer -ArgumentList @('/S', '/UPDATE', "/D=$installDirectory") -WindowStyle Hidden -PassThru -Wait
if ($setup.ExitCode -ne 0) { throw "Installer failed with exit code $($setup.ExitCode)" }
}
# Tauri temporarily replaces UNK with NSS while packaging NSIS, then restores
# the raw release exe. Compare all bytes with precisely that marker applied.
$expectedBytes = [IO.File]::ReadAllBytes($built)
$marker = '__TAURI_BUNDLE_TYPE_VAR_UNK'
$binaryText = [Text.Encoding]::ASCII.GetString($expectedBytes)
$markerOffset = $binaryText.IndexOf($marker, [StringComparison]::Ordinal)
if ($markerOffset -lt 0 -or $binaryText.LastIndexOf($marker, [StringComparison]::Ordinal) -ne $markerOffset) { throw 'Expected one unpatched Tauri bundle marker.' }
$nsisMarker = [Text.Encoding]::ASCII.GetBytes('__TAURI_BUNDLE_TYPE_VAR_NSS')
[Array]::Copy($nsisMarker, 0, $expectedBytes, $markerOffset, $nsisMarker.Length)
$hasher = [Security.Cryptography.SHA256]::Create()
try { $expectedHash = [BitConverter]::ToString($hasher.ComputeHash($expectedBytes)).Replace('-', '') } finally { $hasher.Dispose() }
if ($expectedHash -ne (Get-FileHash -LiteralPath $installed).Hash) { throw 'Installed executable differs from the NSIS release payload.' }
$sidecarSource = Join-Path $repo 'src-tauri/binaries/lexium-import-x86_64-pc-windows-msvc.exe'
if ((Get-FileHash -LiteralPath $sidecarSource).Hash -ne (Get-FileHash -LiteralPath (Join-Path $installDirectory 'lexium-import.exe')).Hash) { throw 'Installed importer does not match the bundled importer.' }
foreach ($resource in Get-ChildItem (Join-Path $repo 'src-tauri/ffmpeg') -File) {
    $destination = Join-Path (Join-Path $installDirectory 'ffmpeg') $resource.Name
    if ((Get-FileHash -LiteralPath $resource.FullName).Hash -ne (Get-FileHash -LiteralPath $destination).Hash) { throw "Resource mismatch: $($resource.Name)" }
}
$desktopPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Lexium.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($desktopPath)
$shortcut.TargetPath = $installed
$shortcut.WorkingDirectory = $installDirectory
$shortcut.IconLocation = "$installed,0"
$shortcut.Description = "Lexium $version"
$shortcut.Save()
[pscustomobject]@{ Version = (Get-Item -LiteralPath $installed).VersionInfo.ProductVersion; Executable = $installed; DesktopShortcut = $desktopPath; HashVerified = $true } | ConvertTo-Json
