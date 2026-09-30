# 已退回工单重新提交改造设计

## 背景

当前工单详情页对 `returned`（已退回）状态显示**重新提交**按钮，点击后直接调用 `returned → pending` 状态流转。业务上，客服处理从「待受理」被退回的工单时，往往需要：

1. 补充必要信息（文字说明）。
2. 重新选择派工的「技能组」和「部门对接人」。

因此需要把"重新提交"从一次性按钮，改为一个可编辑的补充/指派面板。

## 目标

- 在「已退回」工单详情页，移除顶部"重新提交"按钮。
- 在时间流转线下方展示**补充说明 + 技能组 + 部门对接人**编辑模块。
- 客服填写/修改后，通过面板内的"重新提交"按钮一次性完成：
  - 保存补充说明为追加记录（addition）。
  - 更新工单的技能组、部门对接人。
  - 将工单状态从 `returned` 流转回 `pending`。
- 在该场景下不再显示 `ReplyEditor` 的"您当前无权在该工单提交处理说明或追加。"提示。

## 方案

采用**内联编辑面板 + 两步 API 调用**方案，不新增后端聚合接口。

### 前端改造

#### 1. 新增/复用面板

在 `TicketDetailView.vue` 的流转时间线卡片下方，新增 `TicketReturnResubmitPanel`（可内联实现，不强制拆组件）：

- 显示条件：`state_key === 'returned'` 且当前用户有权限（creator / admin），与现有 `canResubmit` 逻辑一致。
- 面板内容：
  - **补充说明**：`el-input type="textarea"`，最多 2000 字，选填。
  - **归属技能组**：`el-select`，从 `metaApi.getSkillGroups()` 加载。
  - **部门对接人**：`el-select`，根据技能组联动加载 `metaApi.getDispatchers(skill_group_id)`；切换技能组时清空已选对接人。
  - **重新提交**按钮：主按钮，校验技能组、对接人已选。

#### 2. 提交逻辑

1. 如果有填写补充说明，先调用 `ticketStore.addArticle({
     type: 'addition',
     body: supplement.value,
     append_reason: '退回补充说明'
   })`。
2. 再调用 `ticketStore.updateTicket(ticket.id, {
     state: 'pending',
     skill_group_id: selectedSkillGroup.value,
     dispatcher_id: selectedDispatcher.value,
     reason: supplement.value || '客服补充后重新提交'
   })`。
3. 成功后刷新列表缓存 `ticketStore.refreshCurrentInList()`，并重新拉取详情 `loadTicket()`。

> 先新增追加记录再改状态，可保证一旦补充写入失败不会误流转；状态流转所需的 `reason` 由系统自动带入，不需要客服额外填写。

#### 3. 隐藏原有重新提交入口

- 移除 `TicketDetailView` 顶部 header-actions 中的"重新提交"按钮及对应弹窗 `resubmitDialogVisible` / `doResubmit`。
- 当面板显示时，不再渲染 `ReplyEditor`，避免展示"您当前无权在该工单提交处理说明或追加。"提示。
- 保留 `returned` 状态下的"撤销"按钮（现有 `canCancel` 逻辑不变）。

### 后端改造

#### 1. 允许已退回工单追加

`backend/app/api/v1/articles.py` 中：

```python
ADDITION_ALLOWED_STATES = {"pending", "open", "on_hold", "returned"}
```

角色限制仍为 admin / agent，无需额外改动。

#### 2. 状态流转保持现状

`returned → pending` 已存在于 `state_machine.TRANSITIONS`。
`check_transition_permission` 已允许 creator / admin 执行。
`requires_reason` 仍要求 `returned → pending` 必须有 `reason`，前端提交时会自动携带，因此后端无需调整。

## 组件/文件改动

| 文件 | 改动 |
|------|------|
| `frontend/src/views/TicketDetailView.vue` | 移除顶部重新提交按钮及弹窗；新增退回补充面板；控制 `ReplyEditor` 显隐。 |
| `frontend/src/api/overviews.ts` | 已提供 `getSkillGroups` / `getDispatchers`，无需改动。 |
| `backend/app/api/v1/articles.py` | `ADDITION_ALLOWED_STATES` 增加 `"returned"`。 |
| `frontend/src/stores/ticket.ts` | 已提供 `addArticle` / `updateTicket` / `refreshCurrentInList`，无需改动。 |

## 数据流

```
客服进入 returned 工单
  → 显示补充面板
  → 填写补充说明、选择技能组/对接人
  → 点击重新提交
    → POST /tickets/{id}/articles  (addition)
    → PATCH /tickets/{id}  (state=pending, skill_group_id, dispatcher_id, reason)
  → refreshCurrentInList + fetchTicketDetail
  → 状态变为 pending，时间线显示追加节点 + 状态流转节点
```

## 边界与异常处理

- **补充说明为空**：跳过新增 addition，直接更新工单。
- **未选择技能组/对接人**：按钮禁用，点击时提示"请选择技能组和部门对接人"。
- **切换技能组**：清空已选对接人，防止对接人不属于新技能组。
- **追加成功但更新失败**：工单仍停留在 returned，追加记录保留在时间线，客服可再次修改并提交。
- **后端权限/状态校验失败**：按现有逻辑显示后端返回的错误信息。

## 验收标准

- [ ] `returned` 状态工单详情页顶部无"重新提交"按钮。
- [ ] 流转时间线下方出现"补充说明 + 技能组 + 部门对接人"面板。
- [ ] 填写内容并点击面板内"重新提交"后，工单状态回到 `pending`。
- [ ] 补充说明作为追加记录出现在流转时间线中。
- [ ] 技能组/部门对接人被更新为面板所选值。
- [ ] 该场景下不显示"您当前无权在该工单提交处理说明或追加。"提示。
- [ ] 非 creator / admin 用户查看 returned 工单时，不显示该面板（可保持现有提示或隐藏）。
- [ ] 撤销按钮在 returned 状态下仍可用。
