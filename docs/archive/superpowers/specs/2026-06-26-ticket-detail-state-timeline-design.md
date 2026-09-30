# 工单详情页流转时间线位置调整设计

## 背景

当前工单详情页 `TicketDetailView` 的主栏顺序为：

1. 沟通记录时间线（`ArticleTimeline`）
2. 回复框（`ReplyEditor`）

流转时间线（`StateLogTimeline`）目前位于右侧 `TicketInfoSidebar` 的“流转”区块下方。用户进入页面后，需要先看右侧或滚动才能了解工单当前所处的状态，不够直观。

## 目标

让用户进入工单详情页后，**第一眼就能看到工单的具体状态及流转历史**，同时将回复框保留在页面底部以便操作。

## 方案

采用**方案一：主栏顶部完整时间线**。

### 调整后布局

`TicketDetailView.detail-main` 的垂直顺序改为：

1. **流转时间线卡片**（新增）
2. **沟通记录时间线（`ArticleTimeline`）**
3. **回复框（`ReplyEditor`）**

右侧 `TicketInfoSidebar` 中移除“流转时间线”区块，避免信息重复。

## 组件设计

### 复用 `StateLogTimeline`

- 传参保持不变：
  ```vue
  <StateLogTimeline :logs="ticket.state_logs" :ticket="ticket" />
  ```
- 内部时间线样式、空状态、当前状态高亮等逻辑均不变。

### 主栏卡片容器

在 `TicketDetailView` 中为流转时间线增加一个主栏卡片容器，样式对齐现有设计系统：

- 背景：`var(--color-bg-card)`
- 边框：`1px solid var(--color-border-light)`
- 圆角：`var(--radius-lg)`
- 内边距：`16px`
- 标题：“流转时间线”，使用与侧边栏 `section-title` 一致的字号、字重和颜色

`StateLogTimeline` 内部 `.timeline-content` 使用 `var(--color-bg-subtle)` 背景，在白色卡片容器内仍能形成层次。

## 数据流

- 无新增接口，继续使用 `ticketStore.fetchTicketDetail()` 返回的 `ticket.state_logs`。
- 用户提交回复、侧边栏变更状态后都会重新拉取详情，`StateLogTimeline` 自动同步。
- 空状态（`state_logs` 为空数组或不存在）由组件自身显示“暂无流转记录”。

## 改动文件

1. `frontend/src/views/TicketDetailView.vue`
   - 在 `detail-main` 顶部插入流转时间线卡片。
   - 增加 `.timeline-card` / `.timeline-section-title` 样式。

2. `frontend/src/components/ticket/TicketInfoSidebar.vue`
   - 删除“流转时间线”侧边栏区块（含标题、分隔线、`StateLogTimeline` 引用）。

## 验收标准

- [ ] 进入工单详情页，主栏最上方显示流转时间线。
- [ ] 侧边栏不再出现“流转时间线”。
- [ ] 状态变更或回复后，时间线内容同步刷新。
- [ ] 移动端/窄屏下时间线不溢出，布局正常。
- [ ] 无新增运行时错误。
