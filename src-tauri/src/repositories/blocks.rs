use crate::{
    error::{AppError, AppResult},
    models::{BlockSummary, NewBlock},
};
use chrono::Utc;
use sqlx::SqlitePool;
use uuid::Uuid;

pub async fn list(pool: &SqlitePool, parent_id: Option<&str>) -> AppResult<Vec<BlockSummary>> {
    let rows = sqlx::query_as::<_, BlockSummary>(r#"
      WITH RECURSIVE descendants(root_id, id) AS (
        SELECT id, id FROM blocks UNION ALL SELECT d.root_id, b.id FROM blocks b JOIN descendants d ON b.parent_id=d.id
      )
      SELECT b.id,b.parent_id,b.name,b.icon_key,b.sort_order,
        (SELECT COUNT(*) FROM blocks c WHERE c.parent_id=b.id) child_count,
        (SELECT COUNT(*) FROM descendants d JOIN block_entries be ON be.block_id=d.id WHERE d.root_id=b.id) word_count,
        COALESCE((SELECT AVG(be.mastery_score) FROM descendants d JOIN block_entries be ON be.block_id=d.id WHERE d.root_id=b.id),0.0) average_mastery
      FROM blocks b WHERE ((?1 IS NULL AND b.parent_id IS NULL) OR b.parent_id=?1) ORDER BY b.sort_order,b.name COLLATE NOCASE
    "#).bind(parent_id).fetch_all(pool).await?;
    Ok(rows)
}

pub async fn create(pool: &SqlitePool, input: NewBlock) -> AppResult<String> {
    let name = input.name.trim();
    if name.is_empty() {
        return Err(AppError::Validation("Block name is required".into()));
    }
    if let Some(parent) = &input.parent_id {
        let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM block_entries WHERE block_id=?")
            .bind(parent)
            .fetch_one(pool)
            .await?;
        if count > 0 {
            return Err(AppError::Validation(
                "Remove vocabulary before adding child blocks".into(),
            ));
        }
    }
    let id = Uuid::new_v4().to_string();
    let now = Utc::now().to_rfc3339();
    sqlx::query("INSERT INTO blocks(id,parent_id,name,icon_key,sort_order,created_at,updated_at) VALUES(?,?,?,?,(SELECT COALESCE(MAX(sort_order),-1)+1 FROM blocks WHERE parent_id IS ?),?,?)")
      .bind(&id).bind(&input.parent_id).bind(name).bind(input.icon_key).bind(&input.parent_id).bind(&now).bind(&now).execute(pool).await?;
    Ok(id)
}
pub async fn update(pool: &SqlitePool, id: &str, name: &str, icon_key: &str) -> AppResult<()> {
    if name.trim().is_empty() {
        return Err(AppError::Validation("Block name is required".into()));
    }
    sqlx::query("UPDATE blocks SET name=?,icon_key=?,updated_at=? WHERE id=?")
        .bind(name.trim())
        .bind(icon_key)
        .bind(Utc::now().to_rfc3339())
        .bind(id)
        .execute(pool)
        .await?;
    Ok(())
}
pub async fn delete(pool: &SqlitePool, id: &str) -> AppResult<()> {
    sqlx::query("DELETE FROM blocks WHERE id=?")
        .bind(id)
        .execute(pool)
        .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn creates_lists_and_deletes_nested_blocks() {
        let pool = crate::db::memory().await.unwrap();
        sqlx::query("DELETE FROM blocks WHERE id='11111111-1111-4111-8111-111111111111'")
            .execute(&pool)
            .await
            .unwrap();
        let root = create(
            &pool,
            NewBlock {
                parent_id: None,
                name: "Root".into(),
                icon_key: "library".into(),
            },
        )
        .await
        .unwrap();
        create(
            &pool,
            NewBlock {
                parent_id: Some(root.clone()),
                name: "Leaf".into(),
                icon_key: "book-open".into(),
            },
        )
        .await
        .unwrap();

        let roots = list(&pool, None).await.unwrap();
        assert_eq!(roots.len(), 1);
        assert_eq!(roots[0].child_count, 1);
        let children = list(&pool, Some(&root)).await.unwrap();
        assert_eq!(children[0].name, "Leaf");

        delete(&pool, &root).await.unwrap();
        assert!(list(&pool, None).await.unwrap().is_empty());
    }
}
