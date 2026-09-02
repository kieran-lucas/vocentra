INSERT OR IGNORE INTO blocks (id, parent_id, name, icon_key, sort_order, created_at, updated_at)
VALUES
  ('11111111-1111-4111-8111-111111111111', NULL, 'Starter English', 'languages', 0, '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z'),
  ('22222222-2222-4222-8222-222222222222', '11111111-1111-4111-8111-111111111111', 'Everyday Words', 'book-open', 0, '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z');

INSERT OR IGNORE INTO vocabulary_entries (
  id, word, ipa, part_of_speech, vi_meaning, en_definition,
  example_meaning_en, example_meaning_vi, example_usage_en, example_usage_vi,
  collocations, usage_note, register, word_family, synonyms, antonyms,
  accepted_answers, extra_metadata, created_at, updated_at
)
VALUES
  ('30000000-0000-4000-8000-000000000001', 'curious', '/ˈkjʊəriəs/', 'adjective', 'tò mò; ham tìm hiểu', 'wanting to learn or know more about something', 'The child was curious about how the clock worked.', 'Đứa trẻ tò mò về cách chiếc đồng hồ hoạt động.', 'I am curious to see what happens next.', 'Tôi rất muốn biết điều gì sẽ xảy ra tiếp theo.', '["curious about","curious to know"]', 'Often followed by about or an infinitive.', 'neutral', '["curiosity","curiously"]', '["inquisitive"]', '[]', '["curious"]', '{}', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z'),
  ('30000000-0000-4000-8000-000000000002', 'steady', '/ˈstedi/', 'adjective', 'ổn định; đều đặn', 'developing or continuing at a regular and reliable rate', 'She made steady progress throughout the course.', 'Cô ấy tiến bộ đều đặn trong suốt khóa học.', 'Keep a steady pace instead of rushing.', 'Hãy giữ nhịp độ ổn định thay vì vội vàng.', '["steady progress","steady pace"]', NULL, 'neutral', '["steadily","steadiness"]', '["stable","consistent"]', '["unstable"]', '["steady"]', '{}', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z'),
  ('30000000-0000-4000-8000-000000000003', 'notice', '/ˈnəʊtɪs/', 'verb', 'nhận thấy; chú ý thấy', 'to become aware of something through observation', 'I noticed a small change in his voice.', 'Tôi nhận thấy một thay đổi nhỏ trong giọng nói của anh ấy.', 'Did you notice that the door was open?', 'Bạn có để ý rằng cửa đang mở không?', '["notice a difference","notice that"]', 'Commonly followed by a noun, that-clause, or object plus verb-ing.', 'neutral', '["noticeable","noticeably"]', '["observe","detect"]', '[]', '["notice"]', '{}', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z'),
  ('30000000-0000-4000-8000-000000000004', 'improve', '/ɪmˈpruːv/', 'verb', 'cải thiện; trở nên tốt hơn', 'to make something better or to become better', 'Daily practice improved her pronunciation.', 'Việc luyện tập hằng ngày đã cải thiện phát âm của cô ấy.', 'The weather should improve by tomorrow.', 'Thời tiết có thể sẽ tốt hơn vào ngày mai.', '["improve performance","improve significantly"]', NULL, 'neutral', '["improvement","improved"]', '["enhance"]', '["worsen"]', '["improve"]', '{}', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z'),
  ('30000000-0000-4000-8000-000000000005', 'reliable', '/rɪˈlaɪəbəl/', 'adjective', 'đáng tin cậy', 'able to be trusted to work well or behave consistently', 'This is a reliable source of information.', 'Đây là một nguồn thông tin đáng tin cậy.', 'We need a reliable way to back up the data.', 'Chúng ta cần một cách đáng tin cậy để sao lưu dữ liệu.', '["reliable source","highly reliable"]', NULL, 'neutral', '["rely","reliability","reliably"]', '["dependable","trustworthy"]', '["unreliable"]', '["reliable"]', '{}', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z'),
  ('30000000-0000-4000-8000-000000000006', 'approach', '/əˈprəʊtʃ/', 'noun', 'cách tiếp cận; phương pháp', 'a particular way of dealing with a task or problem', 'Their approach made the lesson easier to understand.', 'Cách tiếp cận của họ khiến bài học dễ hiểu hơn.', 'We took a practical approach to solving the issue.', 'Chúng tôi áp dụng cách tiếp cận thực tế để giải quyết vấn đề.', '["practical approach","approach to doing something"]', 'As a noun, approach is commonly followed by to plus a noun or gerund.', 'neutral', '[]', '["method","strategy"]', '[]', '["approach"]', '{}', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z');

INSERT OR IGNORE INTO block_entries (id, block_id, entry_id, created_at, updated_at)
VALUES
  ('40000000-0000-4000-8000-000000000001', '22222222-2222-4222-8222-222222222222', '30000000-0000-4000-8000-000000000001', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z'),
  ('40000000-0000-4000-8000-000000000002', '22222222-2222-4222-8222-222222222222', '30000000-0000-4000-8000-000000000002', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z'),
  ('40000000-0000-4000-8000-000000000003', '22222222-2222-4222-8222-222222222222', '30000000-0000-4000-8000-000000000003', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z'),
  ('40000000-0000-4000-8000-000000000004', '22222222-2222-4222-8222-222222222222', '30000000-0000-4000-8000-000000000004', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z'),
  ('40000000-0000-4000-8000-000000000005', '22222222-2222-4222-8222-222222222222', '30000000-0000-4000-8000-000000000005', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z'),
  ('40000000-0000-4000-8000-000000000006', '22222222-2222-4222-8222-222222222222', '30000000-0000-4000-8000-000000000006', '2026-09-02T00:00:00Z', '2026-09-02T00:00:00Z');
