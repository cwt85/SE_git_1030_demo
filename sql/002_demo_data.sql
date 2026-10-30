-- Optional synthetic demo data. Run ONCE after 001_initial.sql.
BEGIN;
INSERT INTO events (title, description, location, starts_at, ends_at, registration_deadline, status)
VALUES
 ('【測試】開放報名活動', '資料庫串接測試用，非真實活動。', '測試教室', CURRENT_TIMESTAMP + INTERVAL '7 days', CURRENT_TIMESTAMP + INTERVAL '7 days 2 hours', CURRENT_TIMESTAMP + INTERVAL '6 days', 'open'),
 ('【測試】手動停止活動', '此活動應拒絕新報名。', '測試教室', CURRENT_TIMESTAMP + INTERVAL '7 days', NULL, NULL, 'closed'),
 ('【測試】已過截止活動', '狀態仍是 open，但截止時間已過，應拒絕新報名。', '測試教室', CURRENT_TIMESTAMP + INTERVAL '7 days', NULL, CURRENT_TIMESTAMP - INTERVAL '1 day', 'open');
INSERT INTO registrations (event_id, name, phone)
SELECT id, '測試同學甲', '0000000001' FROM events WHERE title = '【測試】開放報名活動';
INSERT INTO registrations (event_id, name, phone)
SELECT id, '測試同學乙', '0000000002' FROM events WHERE title = '【測試】開放報名活動';
COMMIT;
