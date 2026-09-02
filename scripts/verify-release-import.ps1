<#
.SYNOPSIS
Checks what an installed Lexium build actually wrote after a JSON import.

Reads the live app database and audio directory directly, so the answer does not
depend on anything the UI claims. Used by the release acceptance run.
#>
[CmdletBinding()]
param(
    [string]$AppData = (Join-Path $env:APPDATA 'com.lexium.desktop'),
    [string]$BlockName = 'Release E2E'
)

$ErrorActionPreference = 'Stop'
$database = Join-Path $AppData 'lexium.sqlite3'
if (-not (Test-Path $database)) { throw "No database at $database" }

# The installed app ships ffprobe; prefer it so this check needs no dev tools.
$installed = Get-ChildItem -Path "$env:LOCALAPPDATA\Programs" -Filter 'ffprobe.exe' -Recurse -ErrorAction SilentlyContinue |
    Select-Object -First 1
$onPath = Get-Command ffprobe -ErrorAction SilentlyContinue
$ffprobe = if ($installed) { $installed.FullName } elseif ($onPath) { $onPath.Source } else { $null }

Add-Type -AssemblyName System.Data
$sqlitePs = @"
import json, sqlite3, sys
connection = sqlite3.connect(sys.argv[1]); connection.row_factory = sqlite3.Row
block = connection.execute("SELECT id FROM blocks WHERE name=?", (sys.argv[2],)).fetchone()
out = {"block": bool(block)}
if block:
    out["cards"] = connection.execute(
        "SELECT COUNT(*) FROM block_entries WHERE block_id=?", (block["id"],)).fetchone()[0]
    out["rows"] = [dict(r) for r in connection.execute(
        "SELECT v.word, v.ipa, v.part_of_speech, v.audio_voice, v.audio_path, v.extra_metadata "
        "FROM block_entries be JOIN vocabulary_entries v ON v.id=be.entry_id WHERE be.block_id=? ORDER BY v.word",
        (block["id"],))]
out["assets"] = [dict(r) for r in connection.execute(
    "SELECT pronunciation_id, status, fingerprint, ROUND(duration_seconds,3) duration, app_path "
    "FROM lexical_audio_assets WHERE pronunciation_id LIKE 'pron_e2e_%' ORDER BY 1")]
out["pilot"] = connection.execute(
    "SELECT COUNT(*) FROM vocabulary_entries WHERE source_name='oxford3000'").fetchone()[0]
out["pilot_imported"] = connection.execute(
    "SELECT COUNT(*) FROM ingestion_items WHERE status='IMPORTED'").fetchone()[0]
out["pilot_failed"] = connection.execute(
    "SELECT COUNT(*) FROM ingestion_items WHERE status='FAILED'").fetchone()[0]
out["mastery_sum"] = connection.execute("SELECT COALESCE(SUM(mastery_score),0) FROM block_entries").fetchone()[0]
out["reviews_sum"] = connection.execute("SELECT COALESCE(SUM(total_reviews),0) FROM block_entries").fetchone()[0]
out["study_events"] = connection.execute("SELECT COUNT(*) FROM study_events").fetchone()[0]
out["lexical_tables"] = connection.execute(
    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'lexical_%'").fetchone()[0]
out["migrations"] = [r[0] for r in connection.execute("SELECT version FROM _sqlx_migrations ORDER BY version")]
print(json.dumps(out, ensure_ascii=False))
"@

$temp = New-TemporaryFile
Set-Content -Path $temp -Value $sqlitePs -Encoding utf8
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) { throw 'This verification helper needs python to read the database; the app itself does not.' }
$python = $pythonCommand.Source
$env:PYTHONIOENCODING = 'utf-8'
$report = & $python $temp $database $BlockName | ConvertFrom-Json
Remove-Item $temp -Force

Write-Host "block '$BlockName' present : $($report.block)"
Write-Host "cards in block            : $($report.cards)"
foreach ($row in $report.rows) {
    $additional = ($row.extra_metadata | ConvertFrom-Json).items.Count
    Write-Host ("  {0,-12} {1,-8} {2,-16} voice={3} additional={4}" -f $row.word, $row.part_of_speech, $row.ipa, $row.audio_voice, $additional)
    $file = Join-Path $AppData $row.audio_path
    if (-not (Test-Path $file)) { throw "Missing audio file for $($row.word): $file" }
    if ($ffprobe) {
        $probe = & $ffprobe -v error -show_entries stream=codec_name,channels -show_entries format=duration -of default=nw=1 $file
        Write-Host ("               {0}" -f ($probe -join ' '))
        if ($probe -notcontains 'codec_name=opus') { throw "$($row.word) is not Opus" }
        if ($probe -notcontains 'channels=1') { throw "$($row.word) is not mono" }
    }
}
Write-Host "audio assets              : $($report.assets.Count)"
foreach ($asset in $report.assets) {
    Write-Host ("  {0,-32} {1,-13} {2}s" -f $asset.pronunciation_id, $asset.status, $asset.duration)
    if ($asset.fingerprint -notlike '*en-US-JennyNeural*') { throw "Wrong voice in fingerprint: $($asset.fingerprint)" }
    if ($asset.fingerprint -notlike '*audio-24khz-48kbitrate-mono-mp3*') { throw "Wrong source format: $($asset.fingerprint)" }
    if ($asset.duration -le 0.2) { throw "Suspiciously short audio for $($asset.pronunciation_id)" }
}
Write-Host "pilot entries / imported / failed : $($report.pilot) / $($report.pilot_imported) / $($report.pilot_failed)"
Write-Host "mastery / reviews / study events  : $($report.mastery_sum) / $($report.reviews_sum) / $($report.study_events)"
Write-Host "lexical tables / migrations       : $($report.lexical_tables) / $($report.migrations -join ',')"
