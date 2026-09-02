use crate::{
    error::{AppError, AppResult},
    models::{Rating, StudyItem, StudyNext, StudyStart},
    repositories::vocabulary,
    services::scheduler::Scheduler,
};
use chrono::Utc;
use sqlx::SqlitePool;
use std::collections::HashMap;
use tokio::sync::Mutex;
use uuid::Uuid;

pub struct ActiveStudy {
    pub turn_id: String,
    pub items: Vec<StudyItem>,
    pub scheduler: Scheduler,
    pub current: Option<usize>,
    pub shown_at: String,
}
pub struct StudySessions(pub Mutex<HashMap<String, ActiveStudy>>);
impl Default for StudySessions {
    fn default() -> Self {
        Self(Mutex::new(HashMap::new()))
    }
}
pub async fn start(
    pool: &SqlitePool,
    sessions: &StudySessions,
    block_id: &str,
) -> AppResult<StudyStart> {
    let child: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM blocks WHERE parent_id=?")
        .bind(block_id)
        .fetch_one(pool)
        .await?;
    if child > 0 {
        return Err(AppError::Validation(
            "Study is available only for leaf blocks".into(),
        ));
    }
    let name: Option<String> = sqlx::query_scalar("SELECT name FROM blocks WHERE id=?")
        .bind(block_id)
        .fetch_optional(pool)
        .await?;
    let name = name.ok_or_else(|| AppError::NotFound("Block not found".into()))?;
    let items = vocabulary::study_items(pool, block_id).await?;
    if items.is_empty() {
        return Err(AppError::Validation(
            "Import vocabulary before starting study".into(),
        ));
    }
    let turn_id = Uuid::new_v4().to_string();
    let now = Utc::now().to_rfc3339();
    sqlx::query(
        "INSERT INTO study_turns(id,block_id,started_at,target_unique_count)VALUES(?,?,?,?)",
    )
    .bind(&turn_id)
    .bind(block_id)
    .bind(&now)
    .bind(items.len() as i64)
    .execute(pool)
    .await?;
    let scores = items.iter().map(|x| x.mastery_score).collect();
    sessions.0.lock().await.insert(
        turn_id.clone(),
        ActiveStudy {
            turn_id: turn_id.clone(),
            items,
            scheduler: Scheduler::new(scores, rand::random()),
            current: None,
            shown_at: now,
        },
    );
    let total_unique = sessions
        .0
        .lock()
        .await
        .get(&turn_id)
        .map(|session| session.items.len())
        .unwrap_or_default();
    Ok(StudyStart {
        turn_id,
        block_name: name,
        total_unique,
    })
}
pub async fn next(sessions: &StudySessions, turn_id: &str) -> AppResult<StudyNext> {
    let mut guard = sessions.0.lock().await;
    let session = guard
        .get_mut(turn_id)
        .ok_or_else(|| AppError::NotFound("Study turn is no longer active".into()))?;
    if session.current.is_some() {
        return Err(AppError::Validation("Rate the current card first".into()));
    }
    if let Some(index) = session.scheduler.next() {
        session.current = Some(index);
        session.shown_at = Utc::now().to_rfc3339();
        Ok(StudyNext {
            card: Some(session.items[index].clone()),
            unique_covered: session.scheduler.covered(),
            total_unique: session.items.len(),
            total_shown: session.scheduler.total_shown(),
            completed: false,
        })
    } else {
        Ok(StudyNext {
            card: None,
            unique_covered: session.scheduler.covered(),
            total_unique: session.items.len(),
            total_shown: session.scheduler.total_shown(),
            completed: true,
        })
    }
}
pub async fn rate(
    pool: &SqlitePool,
    sessions: &StudySessions,
    turn_id: &str,
    rating: Rating,
    typing_correct: i64,
    typing_errors: i64,
) -> AppResult<()> {
    let mut guard = sessions.0.lock().await;
    let session = guard
        .get_mut(turn_id)
        .ok_or_else(|| AppError::NotFound("Study turn is no longer active".into()))?;
    let index = session
        .current
        .take()
        .ok_or_else(|| AppError::Validation("No current card".into()))?;
    let item = &mut session.items[index];
    let before = item.mastery_score;
    let after = before + rating.points();
    let now = Utc::now().to_rfc3339();
    let mut tx = pool.begin().await?;
    sqlx::query(r#"UPDATE block_entries SET mastery_score=?,last_rating=?,total_reviews=total_reviews+1,again_count=again_count+?,hard_count=hard_count+?,good_count=good_count+?,easy_count=easy_count+?,typing_correct_count=typing_correct_count+?,typing_error_count=typing_error_count+?,last_reviewed_at=?,updated_at=? WHERE id=?"#).bind(after).bind(rating.as_str()).bind((rating==Rating::Again)as i64).bind((rating==Rating::Hard)as i64).bind((rating==Rating::Good)as i64).bind((rating==Rating::Easy)as i64).bind(typing_correct).bind(typing_errors).bind(&now).bind(&now).bind(&item.block_entry_id).execute(&mut*tx).await?;
    sqlx::query("INSERT INTO study_events(id,turn_id,block_entry_id,sequence_index,rating,mastery_before,mastery_after,typing_correct_count,typing_error_count,shown_at,rated_at)VALUES(?,?,?,?,?,?,?,?,?,?,?)").bind(Uuid::new_v4().to_string()).bind(&session.turn_id).bind(&item.block_entry_id).bind(session.scheduler.total_shown()as i64).bind(rating.as_str()).bind(before).bind(after).bind(typing_correct).bind(typing_errors).bind(&session.shown_at).bind(&now).execute(&mut*tx).await?;
    if session.scheduler.complete() {
        sqlx::query("UPDATE study_turns SET ended_at=?,total_shown=?,completed=1 WHERE id=?")
            .bind(&now)
            .bind(session.scheduler.total_shown() as i64)
            .bind(&session.turn_id)
            .execute(&mut *tx)
            .await?;
    } else {
        sqlx::query("UPDATE study_turns SET total_shown=? WHERE id=?")
            .bind(session.scheduler.total_shown() as i64)
            .bind(&session.turn_id)
            .execute(&mut *tx)
            .await?;
    }
    tx.commit().await?;
    item.mastery_score = after;
    session.scheduler.rate(index, rating);
    Ok(())
}
