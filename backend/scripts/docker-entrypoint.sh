#!/bin/sh
set -e

# 运行数据库迁移
echo "Running database migrations..."
alembic upgrade head

# 灌入种子数据（仅当 users 表为空时执行）
echo "Seeding database..."
python scripts/seed.py

# 启动应用
echo "Starting application..."
exec "$@"
