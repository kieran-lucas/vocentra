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
uv run python -m unittest discover -s tools/ingest/tests -v
pnpm tauri build
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

The pilot uses `en-US-AriaNeural` through the Microsoft Edge neural speech service during dataset generation. It needs no Google billing or API key. The returned audio is retained as an intermediate master, normalized conservatively, encoded locally with FFmpeg, and copied into app data. The shipped app remains fully offline and never calls a speech service at runtime. The provider adapter is isolated in `tools/ingest/audio_microsoft.py` so it can be replaced without changing validation, encoding, import, or app playback.

## Architecture

- `src/lib/api/` and `src/lib/components/` — typed IPC, modular cards, block navigation, study, and audio UI.
- `src-tauri/src/repositories/`, `services/`, and `commands/` — SQL, business rules, and thin Tauri boundaries.
- `src-tauri/migrations/` — app schema, sample seed, and ingestion/audio tracking.
- `tools/ingest/` — manifest discovery, critic, validators, speech generation, FFmpeg encoding, import, status, audit, and tests.
- `tools/prompts/` and `tools/schemas/` — stable generation/critic specs, golden cards, and card schema.
- `data/source/`, `data/generated/`, and `reports/` — deterministic manifest, normalized output, failures, and durable run report.

Interrupted study turns are not resumed, but every committed rating, typing count, mastery change, and study event survives restart. Interrupted ingestion runs resume by source key and source index.
