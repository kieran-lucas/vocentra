<#
.SYNOPSIS
Checks what an installed Lexium build actually wrote after a JSON import.

Reads the live app database and audio directory directly, so the answer does not
depend on anything the UI claims. Used by the release acceptance run.
#>
[CmdletBinding()]
param(
    [string]$AppData = (Join-Path $env:APPDATA 'com.lexium.desktop')
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
memberships = connection.execute(
    "SELECT p.name || ' / ' || b.name path, COUNT(*) count "
    "FROM blocks b JOIN blocks p ON p.id=b.parent_id "
    "JOIN block_entries be ON be.block_id=b.id JOIN vocabulary_entries v ON v.id=be.entry_id "
    "WHERE p.name='Import Test' AND b.name IN ('V2 Leaf A','V2 Leaf B') "
    "AND v.sense_id LIKE 'sense_v2e2e_%' GROUP BY b.id,p.name,b.name ORDER BY b.name").fetchall()
out = {"blocks": {r["path"]: r["count"] for r in memberships}}
out["rows"] = [dict(r) for r in connection.execute(
    "SELECT p.name || ' / ' || b.name block_name,v.word,v.ipa,v.part_of_speech,v.audio_voice,v.audio_path,v.extra_metadata "
    "FROM blocks b JOIN blocks p ON p.id=b.parent_id JOIN block_entries be ON be.block_id=b.id "
    "JOIN vocabulary_entries v ON v.id=be.entry_id WHERE p.name='Import Test' "
    "AND b.name IN ('V2 Leaf A','V2 Leaf B') AND v.sense_id LIKE 'sense_v2e2e_%' ORDER BY b.name,v.word")]
out["canonical_v2_cards"] = connection.execute(
    "SELECT COUNT(*) FROM vocabulary_entries WHERE sense_id LIKE 'sense_v2e2e_%'").fetchone()[0]
out["assets"] = [dict(r) for r in connection.execute(
    "SELECT pronunciation_id, status, fingerprint, ROUND(duration_seconds,3) duration, app_path "
    "FROM lexical_audio_assets WHERE pronunciation_id LIKE 'pron_v2e2e_%' ORDER BY 1")]
out["pilot"] = connection.execute(
    "SELECT COUNT(*) FROM vocabulary_entries WHERE source_name='oxford3000'").fetchone()[0]
out["pilot_audio_paths"] = [r[0] for r in connection.execute(
    "SELECT DISTINCT audio_path FROM vocabulary_entries WHERE source_name='oxford3000' AND audio_path IS NOT NULL")]
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
$report = & $python $temp $database | ConvertFrom-Json
Remove-Item $temp -Force

if ($report.canonical_v2_cards -ne 2) { throw "Expected exactly 2 canonical V2 cards, found $($report.canonical_v2_cards)" }
if ($report.blocks.'Import Test / V2 Leaf A' -ne 2) { throw 'Leaf A does not contain exactly 2 V2 cards' }
if ($report.blocks.'Import Test / V2 Leaf B' -ne 2) { throw 'Leaf B does not contain exactly 2 V2 cards' }
if ($report.assets.Count -ne 2) { throw "Expected 2 shared audio assets, found $($report.assets.Count)" }
if ($report.pilot -ne 180 -or $report.pilot_imported -ne 180 -or $report.pilot_failed -ne 0) {
    throw "Oxford pilot changed: $($report.pilot) / $($report.pilot_imported) / $($report.pilot_failed)"
}
if ($report.lexical_tables -ne 11) { throw "Expected the existing 11-table lexical model, found $($report.lexical_tables)" }

Write-Host "V2 leaf memberships       : $($report.blocks | ConvertTo-Json -Compress)"
Write-Host "canonical V2 cards        : $($report.canonical_v2_cards)"
foreach ($row in $report.rows) {
    $additional = ($row.extra_metadata | ConvertFrom-Json).items.Count
    Write-Host ("  {0,-10} {1,-12} {2,-8} {3,-16} voice={4} additional={5}" -f $row.block_name, $row.word, $row.part_of_speech, $row.ipa, $row.audio_voice, $additional)
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
    if ($asset.fingerprint -notlike '*opus-64k-mono-vbr*') { throw "Wrong final encoding target: $($asset.fingerprint)" }
    if ($asset.duration -le 0.2) { throw "Suspiciously short audio for $($asset.pronunciation_id)" }
}
Write-Host "pilot entries / imported / failed : $($report.pilot) / $($report.pilot_imported) / $($report.pilot_failed)"
$pilotAudioFiles = @($report.pilot_audio_paths | ForEach-Object { Join-Path $AppData $_ } | Where-Object { Test-Path $_ } | Get-Item)
$latestPilotAudio = $pilotAudioFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host "pilot audio files / latest write    : $($pilotAudioFiles.Count) / $($latestPilotAudio.LastWriteTime.ToString('o'))"
Write-Host "mastery / reviews / study events  : $($report.mastery_sum) / $($report.reviews_sum) / $($report.study_events)"
Write-Host "lexical tables / migrations       : $($report.lexical_tables) / $($report.migrations -join ',')"
