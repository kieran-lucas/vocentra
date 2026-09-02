use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, sqlx::FromRow)]
#[serde(rename_all = "camelCase")]
pub struct BlockSummary {
    pub id: String,
    pub parent_id: Option<String>,
    pub name: String,
    pub icon_key: String,
    pub sort_order: i64,
    pub child_count: i64,
    pub word_count: i64,
    pub average_mastery: f64,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NewBlock {
    pub parent_id: Option<String>,
    pub name: String,
    pub icon_key: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
#[serde(rename_all = "camelCase")]
pub struct VocabularyEntry {
    pub id: String,
    pub word: String,
    pub ipa: String,
    pub part_of_speech: String,
    pub vi_meaning: String,
    pub en_definition: String,
    pub example_meaning_en: String,
    pub example_meaning_vi: String,
    pub example_usage_en: String,
    pub example_usage_vi: String,
    pub collocations: String,
    pub usage_note: Option<String>,
    pub register: Option<String>,
    pub word_family: String,
    pub synonyms: String,
    pub antonyms: String,
    pub accepted_answers: String,
    pub extra_metadata: String,
    pub source_key: Option<String>,
    pub source_name: Option<String>,
    pub source_level: Option<String>,
    pub source_index: Option<i64>,
    pub cefr: Option<String>,
    pub audio_path: Option<String>,
    pub audio_voice: Option<String>,
    pub audio_checksum: Option<String>,
}

#[derive(Debug, Serialize, sqlx::FromRow)]
#[serde(rename_all = "camelCase")]
pub struct ManagedEntry {
    #[sqlx(flatten)]
    #[serde(flatten)]
    pub entry: VocabularyEntry,
    pub block_entry_id: String,
    pub mastery_score: i64,
    pub total_reviews: i64,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ImportBatch {
    pub entries: Vec<ImportEntry>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ImportEntry {
    pub word: String,
    pub ipa: String,
    pub part_of_speech: String,
    pub vi_meaning: String,
    pub en_definition: String,
    pub example_meaning: BilingualExample,
    pub example_usage: UsageExample,
    #[serde(default)]
    pub accepted_answers: Vec<String>,
    #[serde(default)]
    pub extras: ImportExtras,
}
#[derive(Debug, Clone, Deserialize)]
pub struct BilingualExample {
    pub en: String,
    pub vi: String,
}
#[derive(Debug, Clone, Deserialize)]
pub struct UsageExample {
    pub en: String,
    pub vi: String,
    pub note: Option<String>,
}
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ImportExtras {
    #[serde(default)]
    pub collocations: Vec<String>,
    pub register: Option<String>,
    #[serde(default)]
    pub word_family: Vec<String>,
    #[serde(default)]
    pub synonyms: Vec<String>,
    #[serde(default)]
    pub antonyms: Vec<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ImportPreview {
    pub valid_count: usize,
    pub errors: Vec<String>,
}
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ImportResult {
    pub imported_count: usize,
}

#[derive(Debug, Clone, Serialize, sqlx::FromRow)]
#[serde(rename_all = "camelCase")]
pub struct StudyItem {
    pub block_entry_id: String,
    pub mastery_score: i64,
    #[sqlx(flatten)]
    #[serde(flatten)]
    pub entry: VocabularyEntry,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StudyStart {
    pub turn_id: String,
    pub block_name: String,
    pub total_unique: usize,
}
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StudyNext {
    pub card: Option<StudyItem>,
    pub unique_covered: usize,
    pub total_unique: usize,
    pub total_shown: usize,
    pub completed: bool,
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Rating {
    Again,
    Hard,
    Good,
    Easy,
}
impl Rating {
    pub fn points(self) -> i64 {
        match self {
            Self::Again => 0,
            Self::Hard => 1,
            Self::Good => 2,
            Self::Easy => 4,
        }
    }
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Again => "again",
            Self::Hard => "hard",
            Self::Good => "good",
            Self::Easy => "easy",
        }
    }
}
