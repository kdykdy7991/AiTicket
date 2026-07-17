-- 为 articles 增加 state_key，用于记录该 article 创建时工单所处的状态
BEGIN;

ALTER TABLE articles ADD COLUMN state_key VARCHAR(30);
CREATE INDEX idx_articles_ticket_state ON articles(ticket_id, state_key);

COMMIT;
