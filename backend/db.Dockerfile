# db 镜像：只提供空的 Postgres 实例
# schema 由 api 容器的 Alembic 创建，种子数据由 api 启动后灌入
FROM postgres:15-alpine
