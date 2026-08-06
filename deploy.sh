#!/bin/bash
set -euo pipefail

# 生产环境部署脚本
# 用法：
#   chmod +x deploy.sh
#
# 常规部署（会备份数据库）：
#   ./deploy.sh              # tag 自动生成 vYYYYMMDD-NN（N 同日自增）
#   ./deploy.sh v20260721-01 # 显式指定 tag
#
# 首次部署（全新环境，自动跑 migration + seed，不备份）：
#   ./deploy.sh --init
#   ./deploy.sh --init v20260721-01

COMPOSE_FILE="docker-compose.prod.yml"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${PROJECT_DIR}/backups"
INIT_MODE=false
TAG=""

# 生成默认 tag：vYYYYMMDD-NN，NN 同日自增
# 失败（docker 未起 / 无历史镜像）时退化为 vYYYYMMDD-01
gen_default_tag() {
    local prefix="v$(date '+%Y%m%d')"
    local last_seq=0
    local t
    while IFS= read -r t; do
        if [[ "$t" =~ ^${prefix}-([0-9]+)$ ]]; then
            local n=$((10#${BASH_REMATCH[1]}))
            (( n > last_seq )) && last_seq=$n
        fi
    done < <(docker images --format '{{.Tag}}' "skdy-api" 2>/dev/null || true)
    printf '%s-%02d' "$prefix" "$((last_seq + 1))"
}

# 解析参数
for arg in "$@"; do
    if [ "$arg" = "--init" ]; then
        INIT_MODE=true
    else
        TAG="$arg"
    fi
done

# 未传 tag 则自动生成
if [ -z "$TAG" ]; then
    TAG="$(gen_default_tag)"
fi

cd "${PROJECT_DIR}"

# 加载环境变量
if [ ! -f .env ]; then
    echo "错误：.env 文件不存在，请先 cp .env.example .env 并填值"
    exit 1
fi

set -a
source .env
set +a

echo "======================================"
if [ "$INIT_MODE" = true ]; then
    echo "首次部署模式：skdy-api:${TAG}"
else
    echo "常规部署模式：skdy-api:${TAG}"
fi
echo "时间：$(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================"

if [ "$INIT_MODE" = true ]; then
    # 首次部署：先启动基础设施
    echo "[1/4] 启动数据库和缓存 ..."
    docker compose -f "${COMPOSE_FILE}" up -d db redis

    echo "等待数据库就绪 ..."
    until docker compose -f "${COMPOSE_FILE}" exec -T db pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" > /dev/null 2>&1; do
        sleep 1
    done
    echo "数据库已就绪"

    # 2. 构建镜像
    echo "[2/4] 构建镜像 skdy-api:${TAG} ..."
    DOCKER_BUILDKIT=1 docker compose -f "${COMPOSE_FILE}" build api web
    docker tag skdy_prod-api "skdy-api:${TAG}" 2>/dev/null || true
    docker tag skdy_prod-api "skdy-api:latest" 2>/dev/null || true

    # 3. 执行数据库迁移 + 种子数据
    echo "[3/4] 初始化数据库 ..."
    docker compose -f "${COMPOSE_FILE}" run --rm api alembic upgrade head
    docker compose -f "${COMPOSE_FILE}" run --rm api python scripts/seed.py

    # 4. 启动全部服务
    echo "[4/4] 启动全部服务 ..."
    docker compose -f "${COMPOSE_FILE}" up -d
else
    # 常规部署

    # 1. 创建备份目录
    mkdir -p "${BACKUP_DIR}"

    # 2. 备份数据库
    BACKUP_FILE="${BACKUP_DIR}/skdy_ticket_$(date +%Y%m%d_%H%M%S).sql"
    echo "[1/5] 备份数据库到 ${BACKUP_FILE} ..."
    docker exec skdy_prod-db-1 pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" > "${BACKUP_FILE}"
    echo "数据库备份完成：${BACKUP_FILE}"

    # 3. 构建镜像
    echo "[2/5] 构建镜像 skdy-api:${TAG} ..."
    DOCKER_BUILDKIT=1 docker compose -f "${COMPOSE_FILE}" build api web
    docker tag skdy_prod-api "skdy-api:${TAG}" 2>/dev/null || true
    docker tag skdy_prod-api "skdy-api:latest" 2>/dev/null || true

    # 4. 执行数据库迁移
    echo "[3/5] 执行数据库迁移 ..."
    docker compose -f "${COMPOSE_FILE}" run --rm api alembic upgrade head

    # 同步种子数据（分类、对接人/处理人等，幂等，可重复执行）
    echo "[4/5] 同步种子数据 ..."
    docker compose -f "${COMPOSE_FILE}" run --rm api python scripts/update_seed_data.py

    # 历史归档工单数据修正（已归档+未回访 → 无需回访，幂等，可重复执行）
    echo "[4b/5] 修正历史归档回访标记 ..."
    docker compose -f "${COMPOSE_FILE}" run --rm api python scripts/sync_archived_callback.py

    # 5. 启动/更新服务
    echo "[5/6] 启动服务 ..."
    docker compose -f "${COMPOSE_FILE}" up -d

    # 6. 健康检查
    echo "[6/6] 等待服务健康检查 ..."
    # 循环等待 api 健康检查通过（最多 ~60s），避免单次 sleep 不足导致误报
    for _ in $(seq 1 12); do
      docker compose -f "${COMPOSE_FILE}" ps api | grep -q "healthy" && break
      sleep 5
    done
fi

# 通用健康检查
echo "======================================"
echo "检查服务状态 ..."
docker compose -f "${COMPOSE_FILE}" ps

if docker compose -f "${COMPOSE_FILE}" ps api | grep -q "healthy"; then
    echo "======================================"
    echo "部署成功：skdy-api:${TAG}"
    echo "======================================"
else
    echo "======================================"
    echo "警告：api 服务健康检查未通过，请查看日志"
    echo "回滚命令：docker compose -f ${COMPOSE_FILE} run --rm api alembic downgrade -1"
    echo "======================================"
    docker compose -f "${COMPOSE_FILE}" logs api --tail=50
    exit 1
fi
