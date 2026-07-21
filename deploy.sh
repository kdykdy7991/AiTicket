#!/bin/bash
set -euo pipefail

# 生产环境部署脚本
# 用法：
#   chmod +x deploy.sh
#   ./deploy.sh [tag]
#
# 例如：
#   ./deploy.sh v20260721-01

COMPOSE_FILE="docker-compose.prod.yml"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${PROJECT_DIR}/backups"
TAG="${1:-latest}"

cd "${PROJECT_DIR}"

# 加载环境变量
if [ ! -f .env ]; then
    echo "错误：.env 文件不存在"
    exit 1
fi

set -a
source .env
set +a

echo "======================================"
echo "开始部署：skdy-api:${TAG}"
echo "时间：$(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================"

# 1. 创建备份目录
mkdir -p "${BACKUP_DIR}"

# 2. 备份数据库
BACKUP_FILE="${BACKUP_DIR}/skdy_ticket_$(date +%Y%m%d_%H%M%S).sql"
echo "[1/5] 备份数据库到 ${BACKUP_FILE} ..."
docker exec skdy_prod-db-1 pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" > "${BACKUP_FILE}"
echo "数据库备份完成：${BACKUP_FILE}"

# 3. 构建/拉取镜像
echo "[2/5] 构建镜像 skdy-api:${TAG} ..."
# 使用 BUILD_TAG 作为构建参数，在 Dockerfile 里不需要的话可忽略
DOCKER_BUILDKIT=1 docker compose -f "${COMPOSE_FILE}" build --no-cache api

# 给镜像打标签（可选，方便回滚）
docker tag skdy_prod-api "skdy-api:${TAG}" || true

# 4. 执行数据库迁移
echo "[3/5] 执行数据库迁移 ..."
docker compose -f "${COMPOSE_FILE}" run --rm api alembic upgrade head

# 5. 启动/更新服务
echo "[4/5] 启动服务 ..."
docker compose -f "${COMPOSE_FILE}" up -d

# 6. 健康检查
echo "[5/5] 等待服务健康检查 ..."
sleep 5

if docker compose -f "${COMPOSE_FILE}" ps api | grep -q "healthy"; then
    echo "======================================"
    echo "部署成功：skdy-api:${TAG}"
    echo "数据库版本：$(docker compose -f ${COMPOSE_FILE} run --rm api alembic current 2>/dev/null | tail -1)"
    echo "======================================"
else
    echo "======================================"
    echo "警告：api 服务健康检查未通过，请查看日志"
    echo "回滚命令：docker compose -f ${COMPOSE_FILE} run --rm api alembic downgrade -1"
    echo "======================================"
    docker compose -f "${COMPOSE_FILE}" logs api --tail=50
    exit 1
fi
