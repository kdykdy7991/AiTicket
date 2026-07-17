# 工单催办功能设计

## 背景

当前客服在处理工单时，若工单长时间停留在 `pending`（待受理）、`open`（处理中）、`on_hold`（暂缓处理）状态，缺乏主动催促处理人加快处理的方式。需要在上述状态下提供**催办**能力：客服填写催办内容后，记录到流转时间线，并在未结单列表中将该工单置顶，以便处理人优先响应。

## 目标

1. 在工单状态为 `pending`、`open`、`on_hold` 时，仅对 `admin` / `agent` 显示**催办**入口。
2. 每个工单**整个生命周期只能催办一次**。
3. 催办内容必填，长度不超过 200 字。
4. 催办后，流转时间线像“追加”一样显示：催办时间、催办人、催办内容。
5. 催办后的工单在所有工单列表中全局置顶。
6. 预留通知扩展点，未来可接入钉钉等通知渠道。

## 方案

采用**复用 `Article(type='reminder')` + `Ticket` 新增 `urged_at` / `urged_by_id`** 方案。

### 后端改造

#### 1. 数据模型

在 `backend/app/models/ticket.py` 的 `Ticket` 模型新增：

```python
urged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
urged_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
```

对应数据库迁移增加两列。`Article` 表本身已支持 `type='reminder'`，无需改动 schema。

#### 2. API 逻辑

在 `backend/app/api/v1/articles.py` 的 `create_article()` 中新增 `reminder` 分支：

- **权限校验**：当前用户 role 必须为 `admin` 或 `agent`。
- **状态校验**：工单当前状态 ∈ `{"pending", "open", "on_hold"}`。
- **次数校验**：`ticket.urged_at is None`。
- **内容校验**：`body` 必填，去除首尾空白后长度 ≤ 200。
- **副作用**：
  1. 创建 `Article(type='reminder', body=body, sender_id=user.id, state_key=str(ticket.state))`。
  2. 更新 `ticket.urged_at = now()`，`ticket.urged_by_id = user.id`。
  3. 调用通知扩展点 `notification_service.remind_handler(ticket, article)`，本次仅做空实现或日志记录。

#### 3. 列表排序

所有工单列表统一采用以下排序：

1. `urged_at DESC NULLS LAST` — 催办工单置顶
2. `in_progress_breached DESC` — 进行中且 SLA 超时的次之
3. `created_at DESC` — 最后按创建时间倒序

### 前端改造

#### 1. 催办入口

在 `frontend/src/components/ticket/ReplyEditor.vue` 中新增“催办” Tab：

- 显示条件 `canRemind`：
  - 当前用户为 `admin` 或 `agent`。
  - 工单状态 ∈ `(pending, open, on_hold)`。
  - `ticket.urged_at` 为空。
- 催办输入框：
  - `el-input type="textarea"`，最大长度 200。
  - 提交按钮禁用逻辑：内容为空或超过 200 字。
- 提交数据：`{ type: 'reminder', body }`。

#### 2. 时间线展示

在 `frontend/src/components/ticket/StateLogTimeline.vue` 中：

- `TimelineNode` 类型新增 `kind: 'reminder'`。
- `nodes` computed 将 `type === 'reminder'` 的 article 按时间合并进时间线。
- 渲染样式与“追加”节点区分：显示催办图标/标签、催办时间、催办人、催办内容。

#### 3. 数据适配

在 `frontend/src/api/tickets.ts` 中：

- `adaptTicket()` 暴露 `urged_at` 和 `urged_by`。
- `adaptArticle()` 中 `reminder` 的 `senderType` 从 `system` 改为 `agent`（催办由客服发起）。

#### 4. 列表置顶标识（可选）

在工单列表卡片上，当 `urged_at` 存在时显示“已催办”标签，提升可读性。

## 组件/文件改动

| 文件 | 改动 |
|------|------|
| `backend/app/models/ticket.py` | `Ticket` 模型新增 `urged_at`、`urged_by_id`。 |
| `backend/migrations/xxx_add_ticket_urged_fields.sql` | 新增迁移文件，给 `tickets` 表加两列。 |
| `backend/app/api/v1/articles.py` | `create_article()` 增加 `reminder` 分支及校验。 |
| `backend/app/services/notification.py`（或新增） | 预留 `remind_handler(ticket, article)` 扩展点。 |
| `backend/app/api/v1/tickets.py`（列表接口） | 未结单列表排序增加 `urged_at DESC NULLS LAST`。 |
| `frontend/src/types/index.ts` | `Ticket` / `Article` 类型补充 `urged_at`、`urged_by`。 |
| `frontend/src/api/tickets.ts` | `adaptTicket`、`adaptArticle` 适配新字段。 |
| `frontend/src/components/ticket/ReplyEditor.vue` | 新增催办 Tab 及提交逻辑。 |
| `frontend/src/components/ticket/StateLogTimeline.vue` | 新增 reminder 时间线节点渲染。 |
| `frontend/src/views/TicketDetailView.vue` | 无需大改，操作成功后刷新详情即可。 |

## 数据流

```
客服进入 pending/open/on_hold 工单
  → ReplyEditor 显示“催办” Tab
  → 填写催办内容（≤200 字）
  → 点击催办
    → POST /tickets/{id}/articles  (type='reminder', body)
    → 后端校验权限 / 状态 / 未催办 / 内容长度
    → 创建 reminder article，更新 ticket.urged_at / urged_by_id
    → 调用 notification_service.remind_handler()（本次空实现）
  → 前端刷新详情 + 刷新列表
  → 流转时间线显示催办节点
  → 所有工单列表中该工单置顶
```

## 边界与异常处理

- **无权限**：非 `admin` / `agent` 用户不显示催办入口；后端直接返回 403。
- **状态不允许**：工单处于 `resolved` / `archived` / `cancelled` / `returned` 时，后端返回 400。
- **已催办**：`ticket.urged_at` 已存在时，前端隐藏入口，后端返回 400。
- **内容非法**：空内容或超过 200 字，提交按钮禁用，后端返回 400。
- **列表排序**：所有列表统一生效；`urged_at` 为 NULL 的工单排在有值的后面，避免影响正常列表。
- **通知失败**：本次通知扩展点不阻塞主流程，仅记录日志。

## 验收标准

- [ ] `pending` / `open` / `on_hold` 状态下，`admin` / `agent` 能看到催办 Tab。
- [ ] `handler` 角色及未登录用户看不到催办入口。
- [ ] 催办内容必填，超过 200 字无法提交。
- [ ] 同一工单催办一次后，入口隐藏，再次调用接口返回错误。
- [ ] 催办成功后流转时间线显示催办时间、催办人、催办内容。
- [ ] 催办后的工单在所有工单列表中置顶显示。
- [ ] 后端预留通知扩展点，不报错。
