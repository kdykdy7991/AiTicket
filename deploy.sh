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
# POC 必须使用独立 Compose 项目，严禁复用同机主系统的 skdy_prod 容器和数据卷。
export COMPOSE_PROJECT_NAME="skdy-poc"
INIT_MODE=false
TAG=""
REFRESH_BASE_IMAGES=false
BASE_IMAGES=("python:3.11-slim" "node:20-alpine" "nginx:1.27-alpine" "postgres:15-alpine" "redis:7-alpine")

cd "${PROJECT_DIR}"

# 每次部署前先同步当前分支。拉取完成后重新执行脚本，确保本次部署使用
# Git 中的最新 deploy.sh。DEPLOY_AFTER_PULL 用于防止重复拉取。
if [ "${DEPLOY_AFTER_PULL:-0}" != "1" ]; then
    if [ -d .git ]; then
        echo "[0] 同步 Git 代码 ..."
        git pull --ff-only
        exec env DEPLOY_AFTER_PULL=1 "$0" "$@"
    else
        echo "警告：当前目录不是 Git 仓库，跳过代码同步"
    fi
fi

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

# 数据库发布步骤统一收口在这里。首次部署和常规部署都必须执行：
# - upgrade head 自动应用包括 leader 角色在内的全部迁移；
# - current --check-heads 保证数据库确实到达镜像内的最新迁移头；
# - seed.py 幂等同步基础账号与分系统，可安全重复执行。
migrate_and_seed() {
    echo "执行数据库迁移 ..."
    docker compose -f "${COMPOSE_FILE}" run --rm api alembic upgrade head

    echo "校验数据库迁移版本 ..."
    docker compose -f "${COMPOSE_FILE}" run --rm api alembic current --check-heads

    echo "同步基础数据 ..."
    docker compose -f "${COMPOSE_FILE}" run --rm api python scripts/seed.py
}

# Docker Hub 偶发 EOF/超时不应让整次部署立即失败；仅重试构建步骤，避免重复备份数据库。
build_images() {
    local image
    for image in "${BASE_IMAGES[@]}"; do
        if ! docker image inspect "${image}" > /dev/null 2>&1; then
            echo "缺少本地基础镜像：${image}"
            echo "请先执行：./deploy.sh --refresh-base-images"
            return 1
        fi
    done
    local max_attempts=3
    local attempt=1
    while true; do
        if DOCKER_BUILDKIT=1 docker compose -f "${COMPOSE_FILE}" build api web; then
            return 0
        fi
        if [ "${attempt}" -ge "${max_attempts}" ]; then
            echo "镜像构建连续失败 ${max_attempts} 次，请检查 Docker Hub 网络后重新执行 deploy.sh"
            return 1
        fi
        echo "镜像构建失败，10 秒后自动重试（$((attempt + 1))/${max_attempts}）..."
        sleep 10
        attempt=$((attempt + 1))
    done
}

refresh_base_images() {
    local image
    for image in "${BASE_IMAGES[@]}"; do
        echo "拉取基础镜像：${image}"
        docker pull "${image}"
    done
}

# 解析参数
for arg in "$@"; do
    if [ "$arg" = "--init" ]; then
        INIT_MODE=true
    elif [ "$arg" = "--refresh-base-images" ]; then
        REFRESH_BASE_IMAGES=true
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
if [ "${REFRESH_BASE_IMAGES}" = true ]; then
    refresh_base_images
    echo "基础镜像已更新并保存在本机"
    exit 0
fi

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
    build_images
    docker tag skdy-poc-api "skdy-api:${TAG}" 2>/dev/null || true
    docker tag skdy-poc-api "skdy-api:latest" 2>/dev/null || true

    # 3. 执行数据库迁移、校验版本并同步种子数据
    echo "[3/4] 初始化数据库 ..."
    migrate_and_seed

    # 4. 启动全部服务
    echo "[4/4] 启动全部服务 ..."
    docker compose -f "${COMPOSE_FILE}" up -d
else
    # 常规部署

    # 确保数据库和缓存已启动（兼容整套服务被 stop 后再次部署）
    echo "[1/7] 启动数据库和缓存 ..."
    docker compose -f "${COMPOSE_FILE}" up -d db redis
    echo "等待数据库就绪 ..."
    until docker compose -f "${COMPOSE_FILE}" exec -T db pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" > /dev/null 2>&1; do
        sleep 1
    done

    # 2. 创建备份目录
    mkdir -p "${BACKUP_DIR}"

    # 2. 备份数据库
    BACKUP_FILE="${BACKUP_DIR}/skdy_ticket_$(date +%Y%m%d_%H%M%S).sql"
    echo "[2/7] 备份数据库到 ${BACKUP_FILE} ..."
    docker compose -f "${COMPOSE_FILE}" exec -T db pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" > "${BACKUP_FILE}"
    echo "数据库备份完成：${BACKUP_FILE}"

    # 3. 构建镜像
    echo "[3/7] 构建镜像 skdy-api:${TAG} ..."
    build_images
    docker tag skdy-poc-api "skdy-api:${TAG}" 2>/dev/null || true
    docker tag skdy-poc-api "skdy-api:latest" 2>/dev/null || true

    # 4-5. 执行数据库迁移、校验版本并同步种子数据
    echo "[4-5/7] 更新数据库 ..."
    migrate_and_seed

    # 6. 启动/更新服务
    echo "[6/7] 启动服务 ..."
    docker compose -f "${COMPOSE_FILE}" up -d

    # 7. 健康检查
    echo "[7/7] 等待服务健康检查 ..."
    # 循环等待 api 健康检查通过（最多 ~60s），避免单次 sleep 不足导致误报
    for _ in $(seq 1 12); do
      docker compose -f "${COMPOSE_FILE}" ps api | grep -q "healthy" && break
      sleep 5
    done
fi

# 首次启动时 API 需要一些初始化时间；常规部署若已等待完成，此处会立即通过。
echo "等待 API 健康检查 ..."
for _ in $(seq 1 12); do
    docker compose -f "${COMPOSE_FILE}" ps api | grep -q "healthy" && break
    sleep 5
done

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
