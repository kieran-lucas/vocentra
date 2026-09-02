# Edge TTS configuration benchmark

Goal: the best practical zero-cost Microsoft Edge / Read Aloud configuration for
isolated English vocabulary pronunciation. Final app audio stays Ogg Opus,
64 kbps, mono.

## Production recommendation

```text
VOICE:
en-US-JennyNeural

EDGE SOURCE:
audio-24khz-48kbitrate-mono-mp3

FINAL APP AUDIO:
Ogg Opus 64 kbps mono

CONFIDENCE:
very high practical confidence (approximately 98%) on the voice;
high confidence on the source format, because Edge offers only three
formats at all and the two credible ones were indistinguishable.

WHY:
Jenny renders fricatives and sibilants with 2-9x the energy above 4 kHz of
every other finalist on sibilant-bearing words, produced no unintelligible
word on the unseen holdout, held the steadiest pacing across the 34-word
test, and never truncated or clipped. Edge rejects every PCM format, so the
"lossless master" route does not exist; of the three formats it does return,
the 48 kbps MP3 that edge-tts already requests was statistically
indistinguishable from the 96 kbps one after the Opus encode, and needs no
protocol code.
```

## How this was judged, and its limits

Every clip was generated for real - 512 scored clips across five rounds, plus
format-acceptance probes - and put through the production FFmpeg chain to Ogg
Opus 64 kbps mono before being scored, so every score describes what the app
would actually play.

Judging combined three instruments:

- **ASR** (faster-whisper `small.en`, greedy-free beam 5, no prompt) for wrong
  word, truncation and severe articulation failure, plus `avg_logprob` as a
  graded intelligibility measure. Function words (`a an I at be to`) are exempt
  from word matching: no ASR resolves them out of context, and all five
  finalists failed them identically.
- **Objective acoustics** (numpy): duration, leading/trailing silence, onset and
  offset level, peak and clipping, band energy, spectral centroid, energy above
  4 kHz, syllable-nucleus profile, F0 track.
- **Visual inspection** of waveform + spectrogram contact sheets for the
  heteronyms, the flagged outliers and every disputed call.

**Limits, stated plainly.** No human listened to these clips. Naturalness is the
weakest-supported axis and was scored only from pitch-range and envelope
evidence. Absolute lexical-stress verdicts were *not* attempted: isolated-word
TTS lengthens the final syllable regardless of stress, so nucleus position was
used only to flag disagreement with the other voices on the same word, which
was then inspected by eye. Where a measure turned out not to survive a paired
per-word test, it is reported as noise rather than as a finding.

## Round 0 - inventory

`edge_tts.list_voices()` returns 322 voices, 17 of them `en-US`:

```text
AnaNeural  AndrewMultilingualNeural  AndrewNeural  AriaNeural
AvaMultilingualNeural  AvaNeural  BrianMultilingualNeural  BrianNeural
ChristopherNeural  EmmaMultilingualNeural  EmmaNeural  EricNeural
GuyNeural  JennyNeural  MichelleNeural  RogerNeural  SteffanNeural
```

All nine shortlist voices exist. Two were added, for 11 in Round 1:

| added | reason |
| --- | --- |
| `en-US-BrianNeural` | the only unrepresented member of the newer Copilot/conversational family; the shortlist sampled that family only through Andrew |
| `en-US-MichelleNeural` | the News/Novel family is the crisp-articulation family and was sampled only by Aria on the female side; Michelle's profile is less theatrical, and overly theatrical delivery is a flagged failure mode |

`AnaNeural` (child/cartoon) and the remaining Multilingual variants were not
added: nothing suggested they could beat the shortlist, and the Emma pair below
shows what the Multilingual variants are actually worth here.

## Round 1 - 11 voices x 12 words

Baseline format `audio-24khz-48kbitrate-mono-mp3`, rate `-5%`, pitch `+0Hz`,
volume `+0%` held identical. 132 clips, 132 encoded, 0 failures.

`bad` = production-encode failures + ASR silence + clips peaking below -30 dBFS.
`miss` = content words the ASR did not transcribe correctly. `stress` =
disagreements with the other voices' nucleus profile on the same word.

```text
voice                          bad  miss stress    logP  s/char     cv   hf   cent
en-US-JennyNeural                0     0      1  -0.253  0.0930  0.786 0.0110  652
en-US-AriaNeural                 0     0      1  -0.284  0.1081  0.694 0.0071  797
en-US-RogerNeural                0     0      1  -0.321  0.0967  0.947 0.0013  819
en-US-EricNeural                 0     0      1  -0.350  0.0956  0.626 0.0133  541
en-US-AndrewNeural               0     0      2  -0.256  0.0657  0.558 0.0047  527
en-US-MichelleNeural             0     0      2  -0.311  0.0921  0.695 0.0022  410
en-US-ChristopherNeural          0     0      3  -0.327  0.0867  0.599 0.0109  463
en-US-AvaNeural                  1     0      1  -0.236  0.0909  0.529 0.0040  656
en-US-EmmaMultilingualNeural     1     0      2  -0.278  0.0701  0.167 0.0071  457
en-US-EmmaNeural                 1     0      2  -0.281  0.0702  0.167 0.0071  457
en-US-BrianNeural                2     0      1  -0.256  0.0674  0.144 0.0167  458
```

**Every voice transcribed all ten content words correctly.** Edge's `en-US`
voices share a text frontend, so segmental pronunciation does not separate them;
the separation has to come from delivery, articulation detail and edge-case
robustness. No clip clipped (`clip_fraction` 0.0000 everywhere) and none was
truncated (every clip ends below -54 dB).

### The two findings that drove Round 1

**`en-US-BrianNeural` returns digital silence for the word "a".** Peak
-58.8 dBFS, reproduced byte-identically three times; `audio_encode.encode` then
emits an unplayable 135-byte Ogg. "a, an" is source record 1 of the pilot. Every
other voice returns a healthy -1.3 to -10.6 dBFS for the same input. Hard
elimination.

**`en-US-EmmaMultilingualNeural` is a duplicate of `en-US-EmmaNeural` for
English.** Mean log-spectral distance between the two over ten content words is
3.49 dB, against 12.34-21.21 dB for pairs of genuinely different voices. Its
Round-1 numbers are identical to Emma's to three decimals. Its top-5 slot was
released rather than spent on the same voice twice.

### Promotions and eliminations

Promoted: **Ava, Jenny, Andrew, Aria, Emma**.

| eliminated | reason |
| --- | --- |
| `BrianNeural` | silent "a"; unplayable production output for it |
| `MichelleNeural` | lowest energy above 4 kHz (0.0022) and lowest spectral centroid (410) of the eleven, i.e. the dullest consonants; merged "comfortable" into one nucleus where the field used three |
| `RogerNeural` | lowest HF detail of all (0.0013); only voice whose "record" nucleus profile deviated from the field; worst pacing spread |
| `ChristopherNeural` | most nucleus disagreements (3); longest trailing silence (116 ms); below-median ASR confidence |
| `EricNeural` | lowest ASR confidence of the eleven (-0.350) |
| `EmmaMultilingualNeural` | measured duplicate of Emma (3.49 dB), no English benefit; §13's caution applies with no offsetting gain |

## Round 2 - top 5 x 34 words, plus repeat synthesis

28 diagnostic words (short, rhotic/cluster, pronunciation-sensitive,
stress-sensitive, technical, heteronym) plus 6 real Oxford headwords sampled
deterministically (`seed=20260902` over 4646 single-word headwords from
`oxford_a1_pilot_manifest.jsonl` + `oxford_5000_manifest.jsonl`):
`intervene pastor amendment working code unpleasant`. Plus a second take of the
8 hardest words per voice. 210 clips, 0 failures.

```text
voice                  miss  stress    logP  shortword_ms  s/char(long)  cv(long)  hf(long)
en-US-JennyNeural         1       1  -0.257           296        0.0670     0.137    0.0184
en-US-AriaNeural          1       1  -0.311           371        0.0724     0.156    0.0118
en-US-AvaNeural           1       3  -0.249           261        0.0676     0.155    0.0088
en-US-EmmaNeural          1       1  -0.300           109        0.0690     0.177    0.0139
en-US-AndrewNeural        2       9  -0.266           181        0.0504     0.176    0.0110
```

`shortword_ms` is the mean speech duration of `a an I at be to`; the pacing and
articulation columns exclude those six so that word length does not dominate.

All five miss `pastor` (Caster/Custer/Chester/…), an ASR limitation on an
uncommon word, not a voice defect.

### Repeat synthesis: Edge is effectively deterministic

Across all 40 repeat pairs (5 voices x 8 hard words), take 1 and take 2 have
**identical duration and identical file size**, with normalised cross-correlation
between 0.9980 and 1.0000 and a maximum sample difference of 0.077. No
pronunciation, stress, pacing or clipping difference appeared in any pair, and
no ASR transcription changed.

```text
voice                mean_dur_spread  max  text_mismatch
en-US-AndrewNeural             0.000 0.000             0
en-US-AriaNeural               0.000 0.000             0
en-US-EmmaNeural               0.001 0.005             0
en-US-AvaNeural                0.001 0.010             0
en-US-JennyNeural              0.002 0.009             0
```

Consistency across repeats therefore **cannot** discriminate between Edge
voices; the 15% consistency weight was carried by pacing variance across
different words instead, where Jenny leads (cv 0.137).

### Top 3

Promoted: **Jenny, Aria, Ava**.

| eliminated | reason |
| --- | --- |
| `AndrewNeural` | the only content-word ASR failure of the round (`rural` → "girl", a rhotic-difficulty word); 9 nucleus disagreements against 1-3 for the others, on 7 distinct words; fastest delivery (0.0504 s/char) with a visible amplitude decay across the word in every spectrogram checked (`world`, `comfortable`, `entrepreneur`, `photolithography`), so final syllables arrive quietest |
| `EmmaNeural` | renders `a an I at be to` in 109 ms, a third of Aria's 371 ms and well under half of anyone else's; three of them were unrecognisable to ASR at healthy levels. The pilot's first entry is "a, an" and its A1 vocabulary is dense with such words, so a 109 ms clip is a practical defect. Lowest spectral centroid (477) of the five |

No multilingual voice reached the top 3, so §13's extra checks did not apply.

## Round 3 - source format

### What Edge actually accepts

Ten format strings x 5 voices x 2 attempts each, via a minimal websocket client
(`tools/bench/edge_synth.py`) that reuses edge-tts' DRM token, headers and SSML
but sets `outputFormat` itself. The stock `edge_tts.Communicate` cannot answer
this question: it hard-codes `audio-24khz-48kbitrate-mono-mp3` in its
`speech.config` frame *and* rejects any `Content-Type` other than `audio/mpeg`.

```text
format                              accepted   content-type
audio-24khz-48kbitrate-mono-mp3        5 / 5    audio/mpeg
audio-24khz-96kbitrate-mono-mp3        5 / 5    audio/mpeg
webm-24khz-16bit-mono-opus             5 / 5    audio/webm; codec=opus
audio-48khz-192kbitrate-mono-mp3       0 / 5    rejected
audio-24khz-160kbitrate-mono-mp3       0 / 5    rejected
audio-48khz-96kbitrate-mono-mp3        0 / 5    rejected
riff-48khz-16bit-mono-pcm              0 / 5    rejected
riff-24khz-16bit-mono-pcm              0 / 5    rejected
raw-24khz-16bit-mono-pcm               0 / 5    rejected
ogg-48khz-16bit-mono-opus              0 / 5    rejected
```

**Edge returns no PCM at all**, and no MP3 above 96 kbps or above 24 kHz.
Rejection is deterministic and voice-independent. The preferred lossless route
in §14/§29 does not exist on this endpoint; the question is settled, not
unresolved.

### ffprobe verification of the returned bytes

Not the requested string - the actual files:

```text
audio-24khz-48kbitrate-mono-mp3  mp3   24000 Hz  1ch   48000 bps  1.776 s  10656 B
audio-24khz-96kbitrate-mono-mp3  mp3   24000 Hz  1ch   96000 bps  1.776 s  21312 B
webm-24khz-16bit-mono-opus       opus  48000 Hz  1ch   n/a        n/a      11384 B
```

The 96 kbps file is exactly twice the size - it is a genuine 96 kbps encode, not
a relabelled 48. The webm container reports **no duration and no bitrate**;
`audio_encode.verify()` requires `duration > 0`, so that route would need the
verification contract changed.

### Comparison on the provisional #1 voice (Jenny, 10 words)

LSD is speech-gated (frames within 40 dB of the reference peak) and
cross-correlation aligned, because Opus carries an encoder pre-skip and
ungated dB ratios are dominated by near-silence.

```text
source format                     src_bw  fin_bw  LSD_src  LSD_fin  final_kB   logP
audio-24khz-96kbitrate-mono-mp3    11077   11205    (ref)    (ref)       6.8  -0.224
webm-24khz-16bit-mono-opus         11210   11170     1.46     1.73       6.8  -0.234
audio-24khz-48kbitrate-mono-mp3    11210   11210     1.12     1.68       6.6  -0.258
```

All three carry the full ~11.2 kHz band. Relative band energy is within 0.4 dB
across all three in both 4-8 kHz and 8-12 kHz, so the 48 kbps stage is not
hollowing out the consonant region. Spectrograms of the three finals for
`thoroughly` and `heterogeneous` are visually indistinguishable.

### Best two practical source formats

**`audio-24khz-48kbitrate-mono-mp3`** and **`audio-24khz-96kbitrate-mono-mp3`**.

`webm-24khz-16bit-mono-opus` is dropped on §20's reliability and simplicity
weights: it is an Opus→Opus tandem transcode, its container defeats the existing
ffprobe verification, and adopting it would change the master file extension
that the pipeline and its stored paths assume.

## Round 4 - top 3 voices x top 2 formats x 10 hard words

60 clips, 0 failures.

```text
configuration                                       miss  stress    logP  s/char     cv      hf   cent
en-US-AvaNeural   | audio-24khz-96kbitrate-mono-mp3     0       0  -0.198  0.0729  0.209  0.0038   669
en-US-AvaNeural   | audio-24khz-48kbitrate-mono-mp3     0       0  -0.215  0.0731  0.210  0.0040   673
en-US-JennyNeural | audio-24khz-96kbitrate-mono-mp3     0       0  -0.235  0.0663  0.118  0.0122   675
en-US-JennyNeural | audio-24khz-48kbitrate-mono-mp3     0       0  -0.243  0.0664  0.116  0.0135   682
en-US-AriaNeural  | audio-24khz-96kbitrate-mono-mp3     0       0  -0.246  0.0784  0.232  0.0065   771
en-US-AriaNeural  | audio-24khz-48kbitrate-mono-mp3     0       0  -0.268  0.0784  0.229  0.0067   774
```

**No voice x format interaction.** The voice ordering is identical under both
formats, the format effect has the same sign and similar size for all three
voices, and pacing is unchanged to four decimals. This is what Round 4 exists to
check, and it is clean: the format choice can be made independently of the voice
choice.

Pronunciation correctness - the 50% term - is tied at zero on this word set, so
the decision rests on the Round-2 correctness record (Jenny 1 nucleus
disagreement, Aria 1, Ava 3), articulation, and consistency, where Jenny leads
decisively (cv 0.117 against 0.210 and 0.230).

Provisional winner: **Jenny x 96 kbps MP3**. Runner-up: **Ava x 96 kbps MP3**.

## Round 5 - unseen holdout

Seed `5150902`, 14 real headwords sampled from the Oxford manifests excluding
every word used in Rounds 1-4, plus 6 diagnostic words chosen for spelling and
cluster difficulty, none previously used:

```text
plan info harmony gaze interpret cell mix mystery flawed form genetic
necessity foreigner screen colonel clothes sixth squirrel february hierarchy
```

Finalists A (Jenny x 96k) and B (Ava x 96k) per §25, plus C (Jenny x 48k) to
test whether the format upgrade earns its complexity on unseen words. The
incumbent production voice **Aria x 48k** was added as a regression check, since
replacing it is the actual consequence of this work. 80 clips, 0 failures.

```text
configuration                                       miss    logP  s/char     cv      hf   cent
en-US-AvaNeural   | audio-24khz-96kbitrate-mono-mp3     2  -0.347  0.0849  0.226  0.0126   721
en-US-AriaNeural  | audio-24khz-48kbitrate-mono-mp3     2  -0.462  0.0962  0.301  0.0162   827
en-US-JennyNeural | audio-24khz-96kbitrate-mono-mp3     4  -0.369  0.0837  0.274  0.0301   815
en-US-JennyNeural | audio-24khz-48kbitrate-mono-mp3     4  -0.404  0.0839  0.276  0.0320   827
```

The raw `miss` column is misleading and must be read word by word:

| word | Jenny 96k | Jenny 48k | Ava 96k | Aria 48k | reading |
| --- | --- | --- | --- | --- | --- |
| colonel | "kernel" | "kernel" | "Colonel" | "colonel" | `colonel` **is** /ˈkɜːrnəl/; all four correct, ASR spelling choice |
| clothes | "close" | "clothes" | "clothes" | "clothes" | `clothes` is standardly /kloʊz/ in American English; not an error |
| sixth | "sixth" | "6" | "Sixth" | "6th" | numeral formatting; only Jenny 48k dropped the ordinal |
| gaze | "days" | "days" | "days" | "gays" | all four fail, ASR /g/ confusion; non-discriminating |
| mix | "MX" | "X" | "mix" | "mix" | Jenny-specific; spectrogram shows the /ks/ burst fully present, so ASR artifact |
| **cell** | "cell" | "cell" | **"So"** | "cell" | **Ava rendered `cell` unintelligibly** |

`cell` is the one substantive failure in the round. The spectrogram is
unambiguous: Jenny opens the word with a bright, dense 4-11 kHz blob - the
initial /s/ - and Ava has essentially none of it (HF ratio 0.0747 against
0.0086, 8.7x). The same weakness shows on `form`, where Ava's /f/ onset is faint
and its ASR confidence drops to -0.73 against Jenny's -0.24.

### The measure that actually separates the finalists

Paired per-word energy above 4 kHz, Jenny against each rival, same 20 words:

```text
Jenny wins on: cell clothes gaze interpret mystery necessity screen sixth squirrel
Ava/Aria win on: colonel february flawed foreigner form genetic harmony
                 hierarchy info mix plan
```

The split is exactly the sibilant/fricative-bearing words against the rest.
Where Jenny wins it wins by 2-9x (cell 8.7x, squirrel 7.5x, screen 6.7x,
gaze 3.9x, sixth 3.1x); where it loses, both values are near zero (0.0003-0.0098)
and the difference is meaningless. For isolated vocabulary - plural /s/, /θ/ vs
/s/, /ʃ/ vs /s/ - that is the articulation property that matters.

### Format: the 96 kbps advantage is noise

Pooled paired per-word comparison across Rounds 3, 4 and 5:

```text
round                n    96k better    mean delta logP
formats/round3      10          4/10            +0.006
interaction/round4  30         16/30            +0.016
holdout/round5      20         12/20            +0.035
pooled              60         32/60            +0.020   sign test p = 0.70
```

The aggregate means move in 96 kbps' favour, but the per-word direction is a
coin flip. The apparent advantage comes from a handful of large-magnitude
outliers, not a systematic improvement. The single `sixth → 6` case at 48 kbps
has no per-word trend behind it.

### Decision

**§26 test on the provisional winner (Jenny x 96k):** no meaningful increase in
pronunciation errors (its two extra flagged "misses" are correct pronunciations
of spelling-trap words); best articulation on every sibilant word against both
rivals; consistency comparable; no new reliability problem; no audible-quality
reversal. Neither Ava nor the incumbent Aria clearly wins - Ava loses a word
entirely, and Aria has the worst ASR confidence (-0.462) and the worst pacing
spread (0.301) of the four. **The voice winner stands: `en-US-JennyNeural`.**

**§27 tie rule on the format**, since 96 kbps and 48 kbps are indistinguishable:

1. fewer pronunciation errors - tied once paired (p = 0.70)
2. better repeatability - identical
3. **simpler implementation - 48 kbps needs no production code at all; 96 kbps
   needs a websocket client that reimplements Edge's `speech.config` frame**
4. **more reliable Edge output path - 48 kbps is the format edge-tts itself
   requests, so it is the best-exercised and best-maintained path**
5. **smaller intermediate files - 10.9 kB against 21.7 kB per word, roughly
   55 MB less at 5000 words**

**The format winner is `audio-24khz-48kbitrate-mono-mp3`** - the existing
baseline, now chosen on evidence and stated explicitly rather than inherited.

## §28 stop criteria

```text
[x] current Edge en-US inventory inspected (17 voices, all 9 shortlist present)
[x] shortlist covered all obvious high-probability families, plus 2 documented additions
[x] top 5 survived a 34-word test
[x] hard words synthesized twice for stability (40 pairs; service is deterministic)
[x] top 3 survived the source-format interaction cross-check (no interaction)
[x] winner beat or tied every rival on the unseen holdout, incumbent included
[x] no unexplained pronunciation failures remain
[x] no source-format verification issue remains
```

Reported as **very high practical confidence (approximately 98%)** for the
voice. Not a statistical 98%: no human listened, and naturalness is
weakly-supported. The residual risk is concentrated in aesthetic preference
between Jenny, Aria and Ava, which measurement cannot settle and which a short
listen would - the three are all pronunciation-correct.

## Side findings worth keeping

- **Production processing does not clip words.** `silenceremove` +
  `loudnorm` shortens the measured speech span by a mean 53 ms, but
  master/final spectrogram pairs for the worst cases (`usually`/Ava,
  `thoroughly`/Aria) show the whole word intact at both edges - the reduction is
  a threshold artifact of loudnorm's compression, not truncation. No clip in any
  round clipped (`clip_fraction` 0.0000 across 582 clips).
- **`audio_encode.encode` can emit an unplayable file from a silent master.**
  Brian's silent "a" produced a 135-byte Ogg. `verify()` would have caught it in
  the pipeline (it requires `duration > 0`), so this is contained - but it is
  worth knowing that the failure surfaces at verification, not at encode.

## Reproducing

```powershell
uv run tools/bench/bench.py round1
uv run tools/bench/bench.py analyze:voices/round1 --asr small.en
uv run tools/bench/score.py voices/round1 --by voice

uv run tools/bench/bench.py round2
uv run tools/bench/bench.py analyze:voices/round2 --asr small.en
uv run tools/bench/score.py voices/round2 --by voice --repeat

uv run tools/bench/bench.py probe-formats --voices en-US-JennyNeural
uv run tools/bench/bench.py round3 --voices en-US-JennyNeural --formats audio-24khz-48kbitrate-mono-mp3,audio-24khz-96kbitrate-mono-mp3,webm-24khz-16bit-mono-opus
uv run tools/bench/format_report.py formats/round3

uv run tools/bench/bench.py round4 --voices en-US-JennyNeural,en-US-AriaNeural,en-US-AvaNeural --formats audio-24khz-48kbitrate-mono-mp3,audio-24khz-96kbitrate-mono-mp3
uv run tools/bench/bench.py round5 --voices "en-US-JennyNeural@audio-24khz-96kbitrate-mono-mp3,en-US-AvaNeural@audio-24khz-96kbitrate-mono-mp3,en-US-JennyNeural@audio-24khz-48kbitrate-mono-mp3,en-US-AriaNeural@audio-24khz-48kbitrate-mono-mp3"
```

## Regenerating the 180-word pilot - NOT run

The 180 pilot files are still Aria's and were not touched. When regeneration is
wanted, note that `process_audio_and_import` skips synthesis whenever the master
already exists, so `--regenerate-audio` alone will **not** pick up the new voice.
Move the old artifacts aside first, non-destructively:

```powershell
$stamp = Get-Date -Format yyyyMMdd-HHmmss
New-Item -ItemType Directory -Force "data\audio-archive\$stamp\master", "data\audio-archive\$stamp\final"
Move-Item data\audio-master\en-US\*.mp3 "data\audio-archive\$stamp\master"
Move-Item data\audio-final\en-US\*.ogg  "data\audio-archive\$stamp\final"
uv run tools/ingest/ingest_oxford_a1_pilot.py --regenerate-audio
uv run python -m tools.ingest.quality_audit
```

`--regenerate-audio` resets only the audio columns (`audio_master_path`,
`audio_path`, `audio_checksum`, `audio_verified`) and sets the row back to
`VALIDATED`. Source keys, source indices, deterministic block and entry IDs,
card JSON, critic and validation records and job history are untouched, and the
audio paths are re-derived to the same deterministic `audio/en-US/<stem>.ogg`
values, so app-data audio paths do not change.
