#!/bin/sh
set -e

# 生产环境数据库迁移请在部署时单独执行：
#   docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
# 种子数据初始化请在首次部署时单独执行：
#   docker compose -f docker-compose.prod.yml run --rm api python scripts/seed.py

exec "$@"
