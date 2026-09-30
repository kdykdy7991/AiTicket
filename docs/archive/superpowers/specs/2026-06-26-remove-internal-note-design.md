# 移除内部备注功能设计

## 背景

当前工单沟通记录支持四种 article 类型：`reply`、`internal_note`、`addition`、`reminder`。其中 `internal_note` 为内部备注，仅部分角色可见。业务上决定彻底移除该功能。

## 目标

前后端完全移除内部备注功能，并删除历史内部备注数据。

## 方案

### 1. 数据库迁移 `backend/migrations/007_remove_article_internal.sql`

- 删除 `articles` 表中所有 `internal = TRUE` 的记录。
- 删除约束 `chk_internal_note`。
- 重建 `chk_article_type` 检查约束，枚举值只保留 `'reply' / 'addition' / 'reminder'`。
- 删除 `internal` 字段。

### 2. 后端模型 `backend/app/models/ticket.py`

- 移除 `Article.internal` 字段定义。

### 3. 后端 Schema `backend/app/schemas/article.py`

- `ArticleCreate.type` 注释与校验中移除 `internal_note`。
- `ArticleOut` 中移除 `internal` 字段。

### 4. 后端接口 `backend/app/api/v1/articles.py`

- 创建 article 时不再根据 `internal_note` 设置 `internal`。
- 列表接口中移除 `handler` 角色的 `internal == False` 过滤。
- 响应 JSON 中不再返回 `internal`。
- 若客户端仍传入 `type='internal_note'`，接口返回 422。

### 5. 前端 `frontend/src/components/ticket/ReplyEditor.vue`

- 删除“内部备注” tab。
- `activeTab` 类型收窄为 `'reply' | 'addition'`。
- 删除内部备注相关 placeholder、提交文案、样式类。
- 提交时 `type` 只可能是 `reply` 或 `addition`。

### 6. 前端 `frontend/src/components/ticket/ArticleTimeline.vue`

- 删除 `is-internal` 样式分支和“内部备注” badge。

### 7. 前端类型与数据层

- `frontend/src/types/index.ts`：移除 `Article.internal` 和 `ArticleCreatePayload.internal`。
- `frontend/src/api/tickets.ts`：`adaptArticle` 不再处理 `internal_note`。
- `frontend/src/mock/index.ts` 和 `frontend/src/mock/data.ts`：删除内部备注相关 mock 数据与处理逻辑。

## 改动文件

- `backend/migrations/007_remove_article_internal.sql`
- `backend/app/models/ticket.py`
- `backend/app/schemas/article.py`
- `backend/app/api/v1/articles.py`
- `frontend/src/components/ticket/ReplyEditor.vue`
- `frontend/src/components/ticket/ArticleTimeline.vue`
- `frontend/src/types/index.ts`
- `frontend/src/api/tickets.ts`
- `frontend/src/mock/index.ts`
- `frontend/src/mock/data.ts`

## 生产环境注意事项

- 该改动包含数据库迁移，会**永久删除**所有历史内部备注记录，部署前必须备份数据库。
- Docker 生产环境需要在重新部署后端容器前，先执行新增迁移脚本 `007_remove_article_internal.sql`。
- 如果生产环境使用 alembic 或其他迁移工具，需要把该 SQL 纳入对应迁移管理流程。
- 前端构建产物需要随新版本镜像一起发布，确保用户端看不到“内部备注”入口。

## 验收标准

- [ ] 回复框只剩“回复”和“追加”两个 tab。
- [ ] 前端不再发送 `internal_note` 类型。
- [ ] 后端 `ArticleCreate` / `ArticleOut` 不再包含 `internal` 字段。
- [ ] 数据库 `articles` 表不再包含 `internal` 字段和 `internal_note` 类型记录。
- [ ] 沟通记录中不再出现“内部备注”标签。
- [ ] 传入 `type='internal_note'` 时后端返回 422。
