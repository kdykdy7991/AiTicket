#!/usr/bin/env bash
# 把开发库（backend-db-1 容器, localhost:5433/skdy_ticket）的数据同步到试用库
# （docker-compose.prod.yml 的 skdy_prod-db-1 容器）。
#
# 用途：dev 里改了数据/造了测试数据后，想让试用环境也更新时执行。
# 效果：试用库现有数据被完全替换为 dev 库内容。
#
# 用法： bash scripts/sync_trial_data.sh
set -euo pipefail

DEV_CONTAINER="backend-db-1"
TRIAL_CONTAINER="skdy_prod-db-1"
DB_USER="skdy"
DB_NAME="skdy_ticket"
DUMP_FILE="/tmp/skdy_dev_dump_$$.sql"   # $$ 带 PID，避免并发撞名

echo "==> 检查容器..."
docker ps --format '{{.Names}}' | grep -qx "$DEV_CONTAINER"   || { echo "开发库容器 $DEV_CONTAINER 未运行"; exit 1; }
docker ps --format '{{.Names}}' | grep -qx "$TRIAL_CONTAINER" || { echo "试用库容器 $TRIAL_CONTAINER 未运行（先 docker compose -f docker-compose.prod.yml up -d）"; exit 1; }

echo "==> 从开发库导出数据..."
docker exec "$DEV_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --no-privileges > "$DUMP_FILE"
echo "    导出 $(wc -c < "$DUMP_FILE") 字节"

echo "==> 拷贝到试用库容器..."
docker cp "$DUMP_FILE" "$TRIAL_CONTAINER":/tmp/dump.sql

echo "==> 清空试用库现有数据（重建 schema）..."
docker exec "$TRIAL_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
  "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO $DB_USER; GRANT ALL ON SCHEMA public TO public;" >/dev/null

echo "==> 导入开发库数据..."
docker exec "$TRIAL_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -f /tmp/dump.sql >/dev/null

echo "==> 清理临时文件..."
rm -f "$DUMP_FILE"
docker exec "$TRIAL_CONTAINER" rm -f /tmp/dump.sql

echo "==> 验证数据量..."
docker exec "$TRIAL_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
  "SELECT 'users='||count(*) FROM users; SELECT 'tickets='||count(*) FROM tickets; SELECT 'users_id_seq='||last_value FROM users_id_seq;"

echo
echo "✅ 同步完成。试用库已与开发库一致。"
