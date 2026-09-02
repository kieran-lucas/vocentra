# Lexium vocabulary JSON — generation contract v1

You are given a list of English words or expressions and a destination block
path. Produce **one JSON document** that Lexium can import directly.

This file is self-contained. You do not need the Lexium source code, and you must
not ask for it.

Lexium generates the pronunciation audio itself, with a voice and codec it has
already chosen. **Never put audio, voice, codec or file-path information in the
document.** Your job is the words.

---

## 1. Document shape

```json
{
  "schemaVersion": 1,
  "batchId": "custom_electronics_20260902_001",
  "destination": {
    "blockId": null,
    "blockPath": ["Custom", "Electronics"],
    "createIfMissing": true
  },
  "entries": [ /* LexicalEntry objects, see §3 */ ]
}
```

| field | rule |
| --- | --- |
| `schemaVersion` | always `1` |
| `batchId` | a stable, unique id for this file. Letters, digits, `. _ : -` only. Convention: `<topic>_<yyyymmdd>_<nnn>` |
| `destination.blockId` | `null` unless the user gave you a specific block id |
| `destination.blockPath` | the path from the library root, e.g. `["Custom", "Electronics"]`. 1–8 levels |
| `destination.createIfMissing` | `true` unless the user says the block must already exist |
| `entries` | 1–500 entries. **All entries in one file go to one block.** For a second block, produce a second file |

---

## 2. Rules that apply everywhere

**Identifiers.** Every `entryId`, `formId`, `pronunciationId`, `senseId`,
`exampleId` and Additional-item `id` must be present, unique across the whole
file, and stable. Use only letters, digits, `.` `_` `:` `-` — no spaces.
Conventions:

```text
entry_<lemma>                            entry_gradient_descent
form_<lemma>_01                          form_gradient_descent_01
pron_<lemma>_<locale>_01                 pron_gradient_descent_en_us_01
sense_<lemma>_<pos>_01                   sense_gradient_descent_noun_01
ex_<lemma>_01 / ex_<lemma>_02            ex_gradient_descent_01
add_<lemma>_<kind>_01                    add_gradient_descent_usage_01
```

Lowercase the lemma and replace spaces and hyphens with `_`. These ids are the
identity of the data: re-importing a file with the same ids **updates** those
entries instead of duplicating them, and the learner's mastery is preserved.

**Null and empty.** These are not interchangeable:

- a list that exists but is empty → `[]`
- an optional value that is absent → `null`
- **never** `""` for "no value"; an empty string is rejected

Required text fields must be non-empty and non-blank.

**Locales.** `en-US` for pronunciations, `vi` for Vietnamese glosses and
translations. Other locales are allowed and additive; the format is `xx` or
`xx-XX`.

**Forbidden fields.** The document is rejected if any object, at any depth,
contains a key named (case-insensitive): `voice`, `ttsVoice`, `ttsProvider`,
`tts`, `provider`, `sourceFormat`, `audioFormat`, `audioCodec`, `codec`,
`audio`, `audioPath`, `audioHash`, `audioChecksum`, `audioVoice`,
`audioPipelineVersion`, `ffmpegArgs`, `masterPath`, `appAudioPath`, `bitrate`,
`rate`, `format`, `dbPath`, `mastery`, `masteryScore`, `reviewHistory`,
`schedulerState`.

`pronunciations` and `ipa` are **not** forbidden — phonetic transcription is
lexical data and belongs in the file. What is forbidden is anything describing
*how the audio is produced*.

---

## 3. A LexicalEntry

One entry = one lemma. Its senses are separate; different parts of speech never
share a sense.

```json
{
  "entryId": "entry_responsible",
  "lemma": "responsible",
  "entryType": "word",
  "forms": [ /* §4 */ ],
  "senses": [ /* §5 */ ]
}
```

- `lemma` — the headword as a learner would look it up.
- `entryType` — `"word"`, `"phrase"`, `"idiom"`, `"abbreviation"` or `null`.
  Use `"phrase"` for multiword terms such as *gradient descent*, *look forward to*.

---

## 4. Forms and pronunciations

```json
{
  "formId": "form_responsible_01",
  "written": "responsible",
  "morphology": null,
  "pronunciations": [
    {
      "pronunciationId": "pron_responsible_en_us_01",
      "locale": "en-US",
      "ipa": "/rɪˈspɑːnsəbəl/"
    }
  ]
}
```

- `written` is what Lexium will speak. For a multiword entry, keep the spaces:
  `"gradient descent"`, not `"gradient_descent"`.
- One form is normal. Add more only for genuinely distinct written forms.
- `morphology` is `null`, or `{"formType": "...", "irregular": true|false,
  "inflections": ["went", "gone"]}`. Ordinary inflection belongs here — **not**
  in Additional.
- Give one `en-US` pronunciation per form. Give two only for a true heteronym
  (see §8).

---

## 5. Senses

```json
{
  "senseId": "sense_responsible_adjective_01",
  "pos": "adjective",
  "formId": "form_responsible_01",
  "pronunciationId": "pron_responsible_en_us_01",
  "glosses": [{"locale": "vi", "text": "chịu trách nhiệm; có trách nhiệm"}],
  "definition": "having the duty to take care of something or to make decisions about it",
  "examples": [ /* exactly two, §6 */ ],
  "additional": { "schemaVersion": 1, "items": [ /* §7 */ ] }
}
```

- `pos` — `noun`, `verb`, `adjective`, `adverb`, `preposition`, `conjunction`,
  `pronoun`, `determiner`, `interjection`, `phrase`, `idiom`.
- `formId` and `pronunciationId` are optional but **always include them** — they
  say which spelling and which reading this sense uses.
- `glosses` — always include a `vi` gloss. Short, accurate, learner-facing.
  Several Vietnamese equivalents separated by `;` is good; a paragraph is not.
- `definition` — plain learner English. Do not copy a dictionary.
- `additional` may be omitted entirely, or be `{"schemaVersion": 1, "items": []}`.

One sense per meaning a learner should actually study. Two or three senses for a
common word is normal; twelve is not.

---

## 6. The two examples

Exactly two, one of each type, in this order.

```json
[
  {
    "exampleId": "ex_responsible_01",
    "type": "meaning",
    "en": "She is responsible for the safety of the children.",
    "note": null,
    "translations": [{"locale": "vi", "text": "Cô ấy chịu trách nhiệm về sự an toàn của những đứa trẻ."}]
  },
  {
    "exampleId": "ex_responsible_02",
    "type": "usage",
    "en": "Managers are responsible for making sure the work is completed on time.",
    "note": "Followed by 'for', then a noun or an -ing form.",
    "translations": [{"locale": "vi", "text": "Các quản lý có trách nhiệm đảm bảo công việc được hoàn thành đúng hạn."}]
  }
]
```

- **`meaning`** — clarifies the central meaning in a natural sentence.
- **`usage`** — teaches something usable: the required preposition, a
  collocation, a grammatical pattern, a register constraint. Its `note` is a
  short learner tip, or `null`.
- Every example needs a `vi` translation.
- The two must not be near-duplicates of each other.

---

## 7. Additional

Pedagogical enrichment for **this sense**, not for the spelling in general.

```json
{
  "id": "add_responsible_pattern_01",
  "kind": "pattern",
  "salience": 1,
  "text": "responsible for + noun / V-ing",
  "note": null,
  "target": null,
  "attributes": {"patternType": "complementation"}
}
```

All seven keys are required on every item. `text` and `note` may each be `null`
as long as the item still carries something: at least one of `text`, `note` or
`target` must be present. A `wordFormation` or `relation` item whose whole point
is the cross-reference may leave both `text` and `note` `null`.

**`salience`** — pedagogical value, not scheduling: `1` essential, `2` useful,
`3` optional.

**`target`** — `null`, or `{"entryId": "...", "senseId": ...}` pointing at
another entry or sense by id. A target that is not in this file is kept and
resolves later when that entry is imported. Never identify a target by spelling
alone.

**`kind`** is one of exactly six. `attributes` carries the subtype; the listed
values validate strongly, and an unlisted but sensible value is preserved with a
warning.

| kind | use for | `attributes` |
| --- | --- | --- |
| `pattern` | complementation, valency, required preposition, transitivity, construction | `patternType`: `complementation`, `valency`, `preposition`, `transitivity`, `reflexive`, `reciprocal`, `construction`, `other` |
| `collocation` | natural high-value word combinations | `relation`: `verb+noun`, `adjective+noun`, `adverb+adjective`, `noun+noun`, `verb+adverb`, `preposition+noun`, `other` |
| `usage` | countability, register, region, domain, style, a common learner error | `usageType`: `countability`, `transitivity`, `register`, `region`, `dialect`, `style`, `domain`, `medium`, `dated`, `rare`, `offensive`, `technical`, `learnerError`, `selectional`, `pragmatics`, `politeness`, `frequency`, `other` (plus a free `value`) |
| `relation` | synonym, antonym, confusable, contrast | `relationType`: `synonym`, `near_synonym`, `antonym`, `contrast`, `confusable`, `false_friend`, `broader`, `narrower`, `related`, `other` |
| `wordFormation` | derivation, compounding, conversion | `relationType`: `derivation`, `compounding`, `conversion`, `clipping`, `blending`, `other`; plus `targetPos` |
| `expression` | a multiword expression tied to this sense | `expressionType`: `phrasalVerb`, `idiom`, `collocationalPhrase`, `fixedExpression`, `other` |

**Keep it to 0–5 items per sense.** This is a study card, not a dictionary
entry. Never invent a learner error to fill the field. Never list twenty
synonyms. Never restate example 2 as an Additional item.

**Never put in Additional:** CEFR level, frequency rank, block membership,
mastery or review history, source or provenance, or anything about audio.
Ordinary inflection goes in `morphology`.

---

## 8. Heteronyms

When one spelling has two readings, use **one form with two pronunciations**, and
have each sense name the one it uses:

```json
"forms": [{
  "formId": "form_record_01",
  "written": "record",
  "morphology": null,
  "pronunciations": [
    {"pronunciationId": "pron_record_noun_en_us", "locale": "en-US", "ipa": "/ˈrekərd/"},
    {"pronunciationId": "pron_record_verb_en_us", "locale": "en-US", "ipa": "/rɪˈkɔːrd/"}
  ]
}]
```

Then `sense_record_noun_01` sets `"pronunciationId": "pron_record_noun_en_us"`
and `sense_record_verb_01` sets the verb one. Lexium will import both, flag the
audio for review (it speaks text, so it cannot choose a reading), and show the
correct IPA on each card.

Do this **only** for genuine heteronyms. Do not add a second pronunciation for
ordinary accent variation.

---

## 9. Complete worked example

Three entries: a plain adjective, a heteronym, and a multiword technical term.

```json
{
  "schemaVersion": 1,
  "batchId": "example_v1_001",
  "destination": {"blockId": null, "blockPath": ["Custom", "General English"], "createIfMissing": true},
  "entries": [
    {
      "entryId": "entry_responsible",
      "lemma": "responsible",
      "entryType": "word",
      "forms": [{
        "formId": "form_responsible_01",
        "written": "responsible",
        "morphology": null,
        "pronunciations": [{"pronunciationId": "pron_responsible_en_us_01", "locale": "en-US", "ipa": "/rɪˈspɑːnsəbəl/"}]
      }],
      "senses": [{
        "senseId": "sense_responsible_adjective_01",
        "pos": "adjective",
        "formId": "form_responsible_01",
        "pronunciationId": "pron_responsible_en_us_01",
        "glosses": [{"locale": "vi", "text": "chịu trách nhiệm; có trách nhiệm"}],
        "definition": "having the duty to take care of something or to make decisions about it",
        "examples": [
          {"exampleId": "ex_responsible_01", "type": "meaning", "en": "She is responsible for the safety of the children.", "note": null,
           "translations": [{"locale": "vi", "text": "Cô ấy chịu trách nhiệm về sự an toàn của những đứa trẻ."}]},
          {"exampleId": "ex_responsible_02", "type": "usage", "en": "Managers are responsible for making sure the work is completed on time.", "note": "Followed by 'for', then a noun or an -ing form.",
           "translations": [{"locale": "vi", "text": "Các quản lý có trách nhiệm đảm bảo công việc được hoàn thành đúng hạn."}]}
        ],
        "additional": {"schemaVersion": 1, "items": [
          {"id": "add_responsible_pattern_01", "kind": "pattern", "salience": 1, "text": "responsible for + noun / V-ing", "note": null, "target": null, "attributes": {"patternType": "complementation"}},
          {"id": "add_responsible_collocation_01", "kind": "collocation", "salience": 1, "text": "take responsibility for", "note": null, "target": null, "attributes": {"relation": "verb+noun"}}
        ]}
      }]
    },
    {
      "entryId": "entry_record",
      "lemma": "record",
      "entryType": "word",
      "forms": [{
        "formId": "form_record_01",
        "written": "record",
        "morphology": null,
        "pronunciations": [
          {"pronunciationId": "pron_record_noun_en_us", "locale": "en-US", "ipa": "/ˈrekərd/"},
          {"pronunciationId": "pron_record_verb_en_us", "locale": "en-US", "ipa": "/rɪˈkɔːrd/"}
        ]
      }],
      "senses": [
        {
          "senseId": "sense_record_noun_01", "pos": "noun",
          "formId": "form_record_01", "pronunciationId": "pron_record_noun_en_us",
          "glosses": [{"locale": "vi", "text": "bản ghi; hồ sơ"}],
          "definition": "a written account of something that is kept so it can be looked at later",
          "examples": [
            {"exampleId": "ex_record_noun_01", "type": "meaning", "en": "The clinic keeps a record of every visit.", "note": null,
             "translations": [{"locale": "vi", "text": "Phòng khám lưu hồ sơ của mỗi lần khám."}]},
            {"exampleId": "ex_record_noun_02", "type": "usage", "en": "There is no record of the payment in our system.", "note": "Stress falls on the first syllable in the noun.",
             "translations": [{"locale": "vi", "text": "Không có bản ghi nào về khoản thanh toán trong hệ thống của chúng tôi."}]}
          ],
          "additional": {"schemaVersion": 1, "items": []}
        },
        {
          "senseId": "sense_record_verb_01", "pos": "verb",
          "formId": "form_record_01", "pronunciationId": "pron_record_verb_en_us",
          "glosses": [{"locale": "vi", "text": "ghi lại; thu âm"}],
          "definition": "to store sound, pictures or information so that it can be used later",
          "examples": [
            {"exampleId": "ex_record_verb_01", "type": "meaning", "en": "They recorded the lecture on a phone.", "note": null,
             "translations": [{"locale": "vi", "text": "Họ đã ghi âm bài giảng bằng điện thoại."}]},
            {"exampleId": "ex_record_verb_02", "type": "usage", "en": "Please record the temperature every morning.", "note": "Stress falls on the second syllable in the verb.",
             "translations": [{"locale": "vi", "text": "Hãy ghi lại nhiệt độ vào mỗi buổi sáng."}]}
          ],
          "additional": {"schemaVersion": 1, "items": [
            {"id": "add_record_verb_usage_01", "kind": "usage", "salience": 1, "text": null, "note": "The noun and the verb are spelled the same but stressed differently.", "target": null, "attributes": {"usageType": "other"}}
          ]}
        }
      ]
    },
    {
      "entryId": "entry_gradient_descent",
      "lemma": "gradient descent",
      "entryType": "phrase",
      "forms": [{
        "formId": "form_gradient_descent_01",
        "written": "gradient descent",
        "morphology": null,
        "pronunciations": [{"pronunciationId": "pron_gradient_descent_en_us_01", "locale": "en-US", "ipa": "/ˈɡreɪdiənt dɪˈsent/"}]
      }],
      "senses": [{
        "senseId": "sense_gradient_descent_noun_01",
        "pos": "noun",
        "formId": "form_gradient_descent_01",
        "pronunciationId": "pron_gradient_descent_en_us_01",
        "glosses": [{"locale": "vi", "text": "phương pháp hạ gradient"}],
        "definition": "a method that repeatedly adjusts values in the direction that most reduces an error",
        "examples": [
          {"exampleId": "ex_gradient_descent_01", "type": "meaning", "en": "Gradient descent slowly moves the model toward a lower error.", "note": null,
           "translations": [{"locale": "vi", "text": "Phương pháp hạ gradient dần đưa mô hình tới mức lỗi thấp hơn."}]},
          {"exampleId": "ex_gradient_descent_02", "type": "usage", "en": "We trained the network using stochastic gradient descent.", "note": "Usually uncountable, and often modified: batch, stochastic, mini-batch.",
           "translations": [{"locale": "vi", "text": "Chúng tôi huấn luyện mạng bằng phương pháp hạ gradient ngẫu nhiên."}]}
        ],
        "additional": {"schemaVersion": 1, "items": [
          {"id": "add_gradient_descent_usage_01", "kind": "usage", "salience": 1, "text": null, "note": "Uncountable: say 'use gradient descent', not 'use a gradient descent'.", "target": null, "attributes": {"usageType": "countability", "value": "uncountable"}},
          {"id": "add_gradient_descent_collocation_01", "kind": "collocation", "salience": 2, "text": "stochastic gradient descent", "note": null, "target": null, "attributes": {"relation": "adjective+noun"}}
        ]}
      }]
    }
  ]
}
```

---

## 10. Quality bar

For every sense: an accurate short Vietnamese gloss, a clear learner-level
English definition, a meaning example, a usage example that teaches something,
Vietnamese for both, and Additional only where it genuinely helps.

Avoid: generic filler, two examples that say the same thing, invented learner
errors, dictionary-length definitions, long synonym or collocation dumps, and
anything copied verbatim from a proprietary dictionary.

---

## 11. Output

When the user asks for the file, reply with **the JSON document only** — no
prose, no explanation, no markdown fences around it unless the user asks. It
must parse as UTF-8 JSON. Do not embed audio, base64 or binary of any kind.
