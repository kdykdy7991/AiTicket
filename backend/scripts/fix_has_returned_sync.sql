-- 一次性回填：让 has_returned 跟"最新一次动作"对齐
-- 规则：最新一条 ticket_state_logs 的 (from_state, to_state) 落在
--       {('pending','returned'), ('open','pending')} 之一时，has_returned = true，否则 false
-- 不存在任何 state_log 的工单：保持当前值不动（极少，新建的工单）

BEGIN;

WITH latest_log AS (
  SELECT DISTINCT ON (ticket_id)
    ticket_id, from_state, to_state
  FROM ticket_state_logs
  ORDER BY ticket_id, created_at DESC
),
target AS (
  SELECT t.id
  FROM tickets t
  JOIN latest_log l ON l.ticket_id = t.id
  WHERE
    (l.from_state = 'pending' AND l.to_state = 'returned')
    OR (l.from_state = 'open' AND l.to_state = 'pending')
),
-- 反向：最新一次动作不是退回
non_return AS (
  SELECT DISTINCT t.id
  FROM tickets t
  JOIN latest_log l ON l.ticket_id = t.id
  WHERE NOT (
    (l.from_state = 'pending' AND l.to_state = 'returned')
    OR (l.from_state = 'open' AND l.to_state = 'pending')
  )
)
-- 置 true
UPDATE tickets
SET has_returned = TRUE
WHERE id IN (SELECT id FROM target)
  AND has_returned = FALSE;

-- 置 false
UPDATE tickets
SET has_returned = FALSE
WHERE id IN (SELECT id FROM non_return)
  AND has_returned = TRUE;

-- 影响行数
SELECT
  (SELECT COUNT(*) FROM target)   AS marked_true,
  (SELECT COUNT(*) FROM non_return) AS marked_false;

COMMIT;
