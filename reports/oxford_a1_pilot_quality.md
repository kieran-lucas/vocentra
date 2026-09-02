# Oxford A1 Pilot Quality Audit

- Deterministic seed: `1802026`
- Random card sample: 20/20 PASS
- Full audio technical verification: 180/180 PASS
- Manual semantic review: 20/20 PASS after one targeted repair to `cook`; a full 180-card POS/meaning/definition scan produced six additional scope corrections.
- Audio semantic review: 29 items checked (the 20-card seeded sample plus pronunciation-sensitive entries). ASR matched 22 exactly; seven short isolated words produced expected homophone/near-phoneme transcripts and were retained with the exact synthesis text recorded. No wrong source word was found.
- Full pilot state: 180/180 imported, last contiguous 180, no pending or failed items.

## Sample
- #006 `activity` — PASS
- #012 `advice` — PASS
- #015 `afternoon` — PASS
- #023 `also` — PASS
- #029 `another` — PASS
- #031 `any` — PASS
- #036 `April` — PASS
- #065 `beach` — PASS
- #073 `begin` — PASS
- #082 `big` — PASS
- #095 `bored` — PASS
- #097 `born` — PASS
- #102 `boyfriend` — PASS
- #116 `buy` — PASS
- #124 `cannot` — PASS
- #128 `career` — PASS
- #131 `cat` — PASS
- #138 `cheap` — PASS
- #153 `club` — PASS
- #167 `cook` — PASS

Detailed bilingual fields and checks are stored in `reports/oxford_a1_pilot_quality.json`.
