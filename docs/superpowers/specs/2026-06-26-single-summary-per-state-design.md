# 工单状态维度单条总结 + 追加权限控制设计

## 背景

当前工单详情页的回复框允许无限次回复。业务上希望把“回复”改成“处理说明”：每个状态下，当前处理人只能提交一次总结性言论；已提交则禁用输入。同时限制“追加”功能的使用场景。

## 目标

1. 每个工单状态下，`type='reply'` 的 article 只能有一条。
2. 当前状态下已存在处理说明时，回复框禁用。
3. “追加”仅在工单处于 `pending / open / on_hold` 状态时可用。
4. 仅 `admin` 和 `agent` 角色可追加；`handler` 不可追加。

## 方案

### 1. 数据层

#### 迁移 `backend/migrations/008_add_article_state_key.sql`

```sql
BEGIN;

ALTER TABLE articles ADD COLUMN state_key VARCHAR(30);
CREATE INDEX idx_articles_ticket_state ON articles(ticket_id, state_key);

COMMIT;
```

- `state_key` 记录该 article 创建时工单所处的状态。
- 历史数据保留为 `NULL`。

#### 模型 `backend/app/models/ticket.py`

- `Article` 增加 `state_key: Mapped[str | None]`。

#### Schema `backend/app/schemas/article.py`

- `ArticleOut` 增加 `state_key: str | None`。

### 2. 后端接口 `backend/app/api/v1/articles.py`

#### 创建 article 时

- 对所有 `type='reply'` 请求：
  - 查询 `articles` 中是否已存在同 `ticket_id`、同 `state_key`、同 `type='reply'` 的记录。
  - 若存在，返回 `409 Conflict`，提示“当前状态下已存在处理说明”。
  - 否则写入 `state_key = ticket.state`。
- 对 `type='addition'` 请求：
  - 校验当前用户角色：`user.role in ('admin', 'agent')`。
  - 校验当前工单状态：`ticket.state in ('pending', 'open', 'on_hold')`。
  - 任一不满足返回 `403 Forbidden` 或 `422 Unprocessable Entity`。
- `type='reminder'` 不受本次改动影响。

#### 列表接口

- 返回字段中加入 `state_key`。

### 3. 前端 `frontend/src/components/ticket/ReplyEditor.vue`

#### Props 调整

接收父组件传入的当前工单和文章列表：

```vue
<ReplyEditor
  :ticket="ticket"
  :articles="ticket.articles"
  @submitted="onRefresh"
/>
```

#### Tab 与文案

- “回复” tab 文案改为“处理说明”。
- 发送按钮文案改为“提交处理说明”。
- placeholder 改为“请输入当前状态的处理说明…”。

#### 当前状态是否已有处理说明

```ts
const hasSummaryForCurrentState = computed(() =>
  props.articles.some(
    a => a.type === 'reply' && a.state_key === props.ticket.state_key
  )
)
```

- 若 `hasSummaryForCurrentState` 为 true：
  - 禁用 textarea 和发送按钮。
  - 显示提示：
    > “当前状态下已提交处理说明，流转到下一状态后可继续补充。”

#### 追加 tab 显隐控制

```ts
const canAppend = computed(() => {
  const allowedStates = ['pending', 'open', 'on_hold']
  return authStore.isAgent && allowedStates.includes(props.ticket.state_key)
})
```

- `canAppend` 为 false 时隐藏“追加” tab。
- 即使通过接口直接调用，后端也会二次校验。

### 4. 前端数据层

- `frontend/src/types/index.ts`：`Article` 增加 `state_key?: string`。
- `frontend/src/api/tickets.ts`：`adaptArticle` 把后端返回的 `state_key` 透传。
- Mock 数据与 Mock API 同步更新，保证本地开发一致。

## 改动文件

- `backend/migrations/008_add_article_state_key.sql`
- `backend/app/models/ticket.py`
- `backend/app/schemas/article.py`
- `backend/app/api/v1/articles.py`
- `frontend/src/types/index.ts`
- `frontend/src/api/tickets.ts`
- `frontend/src/views/TicketDetailView.vue`
- `frontend/src/components/ticket/ReplyEditor.vue`
- `frontend/src/mock/index.ts`
- `frontend/src/mock/data.ts`

## 验收标准

- [ ] 同一状态下只能提交一条 `reply`。
- [ ] 当前状态已有 `reply` 时，处理说明输入框禁用并提示。
- [ ] 状态流转到新状态后，处理说明输入框恢复可用。
- [ ] “追加” tab 仅在 `pending / open / on_hold` 且当前用户为 `admin/agent` 时显示。
- [ ] 后端对非法追加请求返回 403/422。
- [ ] 沟通记录中可看到每条总结对应的状态 `state_key`。
