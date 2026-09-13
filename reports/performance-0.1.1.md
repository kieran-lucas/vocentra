# Lexium 0.1.1 performance and desktop upgrade

Verified 2026-09-14. Source baseline: `2a008a3ea684009d3ef84bfa30eeefdd5383c297`.

## Delivered

- SQLite initialization and migrations run concurrently with window creation. Every database command waits for the same initialization result.
- The library renders immediately when its data arrives; the previous 120 ms exit animation no longer delays it. Native animations replace GSAP and honor reduced motion.
- Management, study and import screens are loaded on demand. Initial production JavaScript decreases from 178,433 to 83,912 bytes (53.0%); initial CSS decreases from 29,000 to 13,383 bytes (53.9%). These are uncompressed asset sizes, not percentages of total startup time.
- Library totals traverse only the visible branch. A covering SQLite index serves membership counts and mastery aggregation.
- Vocabulary pages request at most 101 records and render 100, instead of fetching and rendering up to 1,000. Later pages can reach entries beyond the previous 1,000-entry cap. Search discards stale responses, and offscreen rows defer rendering.
- Scheduler priority calculation computes maximum mastery once per selection instead of rescanning the whole deck for each repeat candidate.
- Rating and selecting the next card share one IPC call; the rating transaction still commits before advancing. Failed transactions leave the current card available for retry.
- Completed and abandoned study sessions release their cards. Audio reuses a player and a bounded cache; moving to another card cancels pending playback. Typing counters reset for every exposure.

## Verification

- Svelte/TypeScript: zero errors and warnings.
- Rust: 20 tests passed, including initialization races and failures, rollback/retry of ratings, study-session cleanup, and pagination beyond 1,000 entries.
- Clippy with `--all-targets -- -D warnings`: passed.
- Production frontend smoke test in an isolated Edge instance: lazy loading, pagination, out-of-order search, audio reuse, one-call rating, typing reset, reduced motion, session cleanup and dialogs passed without page errors. IPC uses synthetic fixtures.
- SQL benchmark: the old and new queries return identical rows for seven navigation cases over 1,102 blocks and 50,000 memberships. Timings varied substantially with machine load. One run measured root totals at 23.4 → 13.2 ms and a child collection at 5.7 → 0.18 ms; a later run showed a root regression (172 → 273 ms). These samples do not establish a stable root speedup.
- Installed native app: successfully rendered the existing library and was visually inspected. Three debug-enabled launch samples were 4,621 / 4,322 / 7,202 ms for the old version and 3,323 / 9,968 / 11,225 ms for the new version. The new library-ready marks were 278 / 352 / 255 ms after document navigation. Two new runs lacked FCP entries. This uncontrolled launch check is inconclusive for overall startup improvement and is not a cold-boot benchmark.

## Installed result and data preservation

- NSIS installer: `src-tauri/target/release/bundle/nsis/Lexium_0.1.1_x64-setup.exe`.
- Installed executable: `%LOCALAPPDATA%/Lexium/lexium.exe`, version 0.1.1.
- Existing Desktop shortcut points to the updated installed executable.
- The installed executable matches the release bytes after applying Tauri's expected `__TAURI_BUNDLE_TYPE_VAR_UNK` → `__TAURI_BUNDLE_TYPE_VAR_NSS` packaging marker. Importer and FFmpeg resource hashes also match.
- All 20 application tables match their pre-upgrade row hashes exactly, including 263 vocabulary entries, 233 memberships and 34 study events. SQLite integrity and foreign-key checks pass. Only migration bookkeeping and the new index change.
- A consistent pre-upgrade SQLite backup is retained locally at `src-tauri/target/upgrade-backup/lexium-before-0.1.1.sqlite3` (ignored by Git).

Reproduction commands are in the README. Raw launch results and screenshots are retained under `src-tauri/target/`.
