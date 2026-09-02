# Lexium

Lexium is a Windows-only, offline-first vocabulary desktop app built with Tauri 2, Svelte 5, TypeScript, Rust, SQLx, SQLite, GSAP, and local Ogg Opus pronunciation audio.

## What works

- Arbitrarily nested block grids with breadcrumb navigation, CRUD, bundled icons, descendant counts, and aggregate mastery.
- Leaf-block vocabulary management with search, editing, removal, JSON validation, and transactional batch import.
- Modular front/back cards, persistent typing practice, local speaker playback, and Again / Hard / Good / Easy ratings.
- Per-block mastery, durable review/typing history, unique-coverage turns, adaptive repeats, cooldown, fairness, and a termination cap.
- Local SQLite and local app-data audio; the shipped app has no account, telemetry, remote font, or runtime cloud dependency.

## Windows development

Prerequisites are Windows 10/11 with WebView2, Node.js 20+, pnpm, stable Rust MSVC, and Visual Studio Build Tools with Desktop C++ and a Windows SDK.

```powershell
pnpm install
pnpm tauri dev
```

The database is `%APPDATA%\com.lexium.desktop\lexium.sqlite3`. Startup enables SQLite foreign keys, WAL, `synchronous=NORMAL`, a five-second busy timeout, a small pool, and embedded forward migrations.

## Build and test

```powershell
pnpm check
pnpm build
cargo fmt --manifest-path src-tauri/Cargo.toml -- --check
cargo test --manifest-path src-tauri/Cargo.toml
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings
uv run --with edge-tts --with jsonschema python -m unittest discover -s tools/ingest/tests -v
powershell -File tools/build_importer_sidecar.ps1
pnpm tauri build            # builds the importer sidecar first, then the installers
```

Installers are written under `src-tauri/target/release/bundle/`.

## Oxford A1 pilot

The manifest is the first 180 A1 records in the alphabetical order published in Oxford's American English CEFR PDF. “A1 Pilot” is a Lexium run label, not an Oxford subdivision. Oxford supplies only the headword, POS, CEFR, and order; card prose and examples are independently authored.

The ingestion state machine is stored in the app SQLite database. Stable `source_key` values, source indices, deterministic block/entry IDs, and UPSERTs make reruns safe. Audio masters stay under `data/audio-master/en-US/`; final files are encoded to Ogg Opus at a 64 kbps target, mono, verified with ffprobe, and copied to app data for offline playback.

```powershell
# Inspect source and DB without mutations or paid calls
uv run tools/ingest/ingest_oxford_a1_pilot.py --dry-run

# Durable progress report
uv run tools/ingest/ingest_oxford_a1_pilot.py --status

# Reproducible 20-card semantic sample and full 180-file audio verification
uv run python -m tools.ingest.quality_audit

# Agent-assisted pronunciation audit (20-card sample plus sensitive entries)
uv run tools/ingest/audio_semantic_audit.py

# Initial eight-card end-to-end gate, or resume it
uv run tools/ingest/ingest_oxford_a1_pilot.py --preflight

# Retry only failed work or a specific source record
uv run tools/ingest/ingest_oxford_a1_pilot.py --retry-failed --preflight
uv run tools/ingest/ingest_oxford_a1_pilot.py --source-index 4
uv run tools/ingest/ingest_oxford_a1_pilot.py --source-key oxford3000:a1:000004 --regenerate-audio
```

The pilot uses `en-US-JennyNeural` with the Edge source format `audio-24khz-48kbitrate-mono-mp3` through the Microsoft Edge neural speech service during dataset generation; both were selected by the benchmark recorded in `data/audio-benchmark/report.md`. It needs no Google billing or API key. The returned audio is retained as an intermediate master, normalized conservatively, encoded locally with FFmpeg, and copied into app data. The shipped app remains fully offline and never calls a speech service at runtime. The provider adapter is isolated in `tools/ingest/audio_microsoft.py` so it can be replaced without changing validation, encoding, import, or app playback.

## External vocabulary JSON import

One JSON file in, usable cards out. Ask any LLM for a file matching
`tools/prompts/external_vocab_generation_v1.md` (a self-contained contract - the
model never needs this repository), then import it. Lexium validates it, resolves
or creates the destination block, generates the pronunciation audio with the
locked production voice, encodes and verifies it, and upserts the lexical data.

- Contract for the generating LLM: `tools/prompts/external_vocab_generation_v1.md`
- Machine-readable schema: `tools/schemas/external_vocabulary_import.v1.schema.json`
- Importer (the only one): `tools/ingest/import_external_vocabulary.py`
- Audio source of truth: `tools/ingest/audio_profile.py`

In the app, use **Import JSON** in the header, choose the file, and watch the
progress. From a terminal:

```powershell
# Import into the app database
uv run tools/ingest/import_external_vocabulary.py my_words.json

# Check a file without writing anything or contacting the speech service
uv run tools/ingest/import_external_vocabulary.py my_words.json --validate-only
```

The file carries words and a destination only. Any attempt to set a voice,
source format, codec, audio path or learner state is rejected before validation
completes, and the production profile always wins. Re-importing the same file
changes nothing and re-synthesises nothing; changing a definition updates the
card and keeps the audio; changing what is spoken regenerates just that clip.
Mastery, review history and block membership are never reset by an import.

### How the importer ships

The app runs the importer as a child process, only while an import is in
progress: there is no daemon, no localhost server and no startup cost.

`tools/build_importer_sidecar.ps1` freezes `import_external_vocabulary.py` with
PyInstaller into a single `lexium-import.exe`, smoke-tests it with
`--validate-only`, and stages it plus a slim LGPL FFmpeg build:

```text
src-tauri/binaries/lexium-import-x86_64-pc-windows-msvc.exe   (externalBin)
src-tauri/ffmpeg/{ffmpeg.exe, ffprobe.exe, *.dll}             (resources)
```

`pnpm tauri build` runs that script from `beforeBuildCommand`, so a release
either contains a working importer or fails before packaging. The installed
layout is:

```text
<install>/lexium.exe
<install>/lexium-import.exe
<install>/ffmpeg/...
```

`resolve_importer()` takes the bundled sidecar first, so release behaviour never
depends on the environment; `LEXIUM_IMPORTER` and the checked-out script are
development fallbacks. `find_binary()` likewise prefers `<install>/ffmpeg` over
`PATH`. The importer writes its intermediate masters under app data when frozen
and into the repository when run from a checkout.

Put a slim FFmpeg in `tools/vendor/ffmpeg/` to control installer size; the build
script falls back to whatever FFmpeg the build machine has, which for a static
build is far larger.

To re-run the installed-build acceptance check, launch the app with
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222` and run:

```powershell
node scripts/release-import-smoke.mjs tools/ingest/tests/fixtures/external/release_e2e_batch.json tools/ingest/tests/fixtures/external/release_e2e_forbidden_voice.json
powershell -File scripts/verify-release-import.ps1
```

## Architecture

- `src/lib/api/` and `src/lib/components/` — typed IPC, modular cards, block navigation, study, and audio UI.
- `src-tauri/src/repositories/`, `services/`, and `commands/` — SQL, business rules, and thin Tauri boundaries.
- `src-tauri/migrations/` — app schema, sample seed, and ingestion/audio tracking.
- `tools/ingest/` — manifest discovery, critic, validators, speech generation, FFmpeg encoding, import, status, audit, and tests.
- `tools/prompts/` and `tools/schemas/` — stable generation/critic specs, golden cards, and card schema.
- `data/source/`, `data/generated/`, and `reports/` — deterministic manifest, normalized output, failures, and durable run report.

Interrupted study turns are not resumed, but every committed rating, typing count, mastery change, and study event survives restart. Interrupted ingestion runs resume by source key and source index.
