use super::vocabulary::list;

#[tokio::test]
async fn pagination_has_no_duplicates_and_can_reach_past_one_thousand() {
    let pool = crate::db::memory().await.unwrap();
    let leaf = "22222222-2222-4222-8222-222222222222";
    sqlx::query("DELETE FROM block_entries")
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("DELETE FROM vocabulary_entries")
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("WITH RECURSIVE n(i) AS (SELECT 0 UNION ALL SELECT i+1 FROM n WHERE i<1004) INSERT INTO vocabulary_entries(id,word,ipa,part_of_speech,vi_meaning,en_definition,example_meaning_en,example_meaning_vi,example_usage_en,example_usage_vi,created_at,updated_at) SELECT printf('%04d',i),'same word','ipa','noun','vi','en','en','vi','en','vi','','' FROM n")
        .execute(&pool).await.unwrap();
    sqlx::query("INSERT INTO block_entries(id,block_id,entry_id,created_at,updated_at) SELECT id,?,id,'','' FROM vocabulary_entries")
        .bind(leaf).execute(&pool).await.unwrap();
    let mut ids = Vec::new();
    for offset in (0..1100).step_by(100) {
        let entries = list(&pool, leaf, "same", offset, 100).await.unwrap();
        assert!(entries.len() <= 100);
        ids.extend(entries.into_iter().map(|entry| entry.entry.id));
    }
    assert_eq!(ids.len(), 1005);
    assert!(ids.windows(2).all(|pair| pair[0] < pair[1]));
    assert!(
        list(&pool, leaf, "missing", 0, 100)
            .await
            .unwrap()
            .is_empty()
    );
}
