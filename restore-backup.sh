#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE_FILE="docker-compose.prod.yml"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export COMPOSE_PROJECT_NAME="skdy-poc"

usage() {
    echo "用法：./restore-backup.sh <数据库备份.sql> <附件备份.tar.gz>"
    echo "示例：./restore-backup.sh backups/restore/skdy_ticket_20260913_134042.sql backups/restore/skdy-poc_uploads_20260913.tar.gz"
}

if [ "$#" -ne 2 ]; then
    usage >&2
    exit 2
fi

cd "$PROJECT_DIR"
BACKUP_FILE="$1"
UPLOADS_BACKUP="$2"
if [[ "$BACKUP_FILE" != /* ]]; then
    BACKUP_FILE="${PROJECT_DIR}/${BACKUP_FILE}"
fi
if [[ "$UPLOADS_BACKUP" != /* ]]; then
    UPLOADS_BACKUP="${PROJECT_DIR}/${UPLOADS_BACKUP}"
fi

[ -s "$BACKUP_FILE" ] || {
    echo "错误：备份文件不存在或为空：${BACKUP_FILE}" >&2
    exit 1
}
[ -s "$UPLOADS_BACKUP" ] || {
    echo "错误：附件备份不存在或为空：${UPLOADS_BACKUP}" >&2
    exit 1
}
[ -f .env ] || {
    echo "错误：缺少 ${PROJECT_DIR}/.env" >&2
    exit 1
}
grep -q "PostgreSQL database dump" "$BACKUP_FILE" || {
    echo "错误：文件不像 PostgreSQL 纯 SQL 备份：${BACKUP_FILE}" >&2
    exit 1
}
tar -tzf "$UPLOADS_BACKUP" >/dev/null || {
    echo "错误：附件备份不是有效的 tar.gz：${UPLOADS_BACKUP}" >&2
    exit 1
}

set -a
source .env
set +a

echo "即将把 POC 数据库恢复为：${BACKUP_FILE}"
echo "即将把 POC 附件恢复为：${UPLOADS_BACKUP}"
echo "目标 Compose 项目：${COMPOSE_PROJECT_NAME}"
read -r -p "此操作会覆盖本机 POC 数据库和附件，输入 RESTORE 继续：" CONFIRM
[ "$CONFIRM" = "RESTORE" ] || { echo "已取消"; exit 1; }

echo "[1/9] 启动 POC 数据库和 Redis ..."
docker compose -f "$COMPOSE_FILE" up -d db redis
until docker compose -f "$COMPOSE_FILE" exec -T db \
    pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; do
    sleep 1
done

echo "[2/9] 停止 POC API 和 Web ..."
docker compose -f "$COMPOSE_FILE" stop api web 2>/dev/null || true

mkdir -p backups backups/restore
RESTORE_TIME="$(date +%Y%m%d_%H%M%S)"
SAFETY_BACKUP="${PROJECT_DIR}/backups/pre_restore_${RESTORE_TIME}.sql"
SAFETY_UPLOADS="${PROJECT_DIR}/backups/pre_restore_uploads_${RESTORE_TIME}.tar.gz"
echo "[3/9] 备份本机当前数据库：${SAFETY_BACKUP}"
docker compose -f "$COMPOSE_FILE" exec -T db \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$SAFETY_BACKUP"

echo "[4/9] 备份本机当前附件：${SAFETY_UPLOADS}"
docker run --rm -v skdy-poc_uploads:/data skdy-poc-api \
    tar -C /data -czf - . > "$SAFETY_UPLOADS"

echo "[5/9] 断开数据库连接 ..."
docker compose -f "$COMPOSE_FILE" exec -T db psql \
    -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${POSTGRES_DB}' AND pid <> pg_backend_pid();"

echo "[6/9] 重建数据库 ..."
docker compose -f "$COMPOSE_FILE" exec -T db \
    dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
docker compose -f "$COMPOSE_FILE" exec -T db \
    createdb -U "$POSTGRES_USER" "$POSTGRES_DB"

echo "[7/9] 导入数据库备份 ..."
if ! docker compose -f "$COMPOSE_FILE" exec -T db psql \
    -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$BACKUP_FILE"; then
    echo "错误：导入失败，API/Web 保持停止。恢复前快照：${SAFETY_BACKUP}" >&2
    exit 1
fi

echo "[8/9] 恢复附件 ..."
if ! docker run --rm -i -v skdy-poc_uploads:/data skdy-poc-api \
    tar -C /data -xzf - < "$UPLOADS_BACKUP"; then
    echo "错误：附件导入失败，API/Web 保持停止。恢复前附件：${SAFETY_UPLOADS}" >&2
    exit 1
fi

echo "[9/9] 执行迁移并启动 POC ..."
exec env DEPLOY_AFTER_PULL=1 ./deploy.sh
