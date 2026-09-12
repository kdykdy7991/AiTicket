# POC 问题闭环改造：后端开发任务书

## 1. 开发目标

将后端从客服工单状态机改造为 POC 问题闭环服务。以 [开发总约定](./00_poc_workflow_development_contract.md) 为唯一接口和枚举契约；遇到歧义先更新总约定，再同步前端，不在代码中自行创造编码。

## 2. 交付边界

后端开发负责：

- 数据库迁移和存量测试数据处理。
- 新角色、状态、优先级及权限规则。
- POC 字段模型、Schema 和序列化。
- 建单、列表、详情、动作、附件、日志、导出 API。
- 每个状态动作的服务端权限与必填校验。
- 流程通知事件。
- 后端单元测试和接口测试。
- 提供最新 OpenAPI JSON 或可访问的 Swagger。

后端开发不负责 Vue 页面和前端展示权限。

## 3. 第一批：数据库和基础模型

### BE-01 新增 Alembic 迁移

在 `backend/alembic/versions/` 新增迁移，完成：

1. 修改用户角色约束，只允许：
   - `admin`
   - `presales`
   - `approver`
   - `taskforce`
   - `subsystem`
   - `quality`
2. 迁移开发环境旧角色：
   - `agent → presales`
   - `handler → subsystem`
   - 原部门对接人不再作为角色或标记使用。
3. 删除或停止使用 `user_skill_groups.is_dispatcher`；为了迁移可回滚，第一阶段允许保留数据库列，但任何新业务代码不得依赖。
4. 将旧工单标记为非 POC 历史数据，或在 POC 环境初始化时清空业务测试数据。禁止把旧状态强行映射成新流程中的审批结果。
5. 修改 `tickets.state` 约束为总约定中的状态集合。
6. 修改优先级约束为 `p0_blocker/p1_critical/p2_normal/p3_low`，默认 `p2_normal`。
7. 给 `tickets` 增加总约定第 5 节全部字段。
8. 增加：
   - `approver_id → users.id`
   - `subsystem_owner_id → users.id`
   - `defect_registered_by_id → users.id`
   - `state_version INTEGER NOT NULL DEFAULT 1`
   - `return_to_state VARCHAR(40) NULL`
9. 增加查询索引：
   - `(state, updated_at DESC)`
   - `(approver_id, state)`
   - `(subsystem_owner_id, state)`
   - `(skill_group_id, state)`
   - `(planned_completion_at)`，过滤未闭环状态
   - `(defect_id)`，允许空值但非空时唯一性由业务确认后决定

验收：全新数据库可升级；已有开发库可升级；`alembic downgrade -1` 可回退结构。

### BE-02 修改 ORM 模型

涉及文件：

- `backend/app/models/ticket.py`
- `backend/app/models/user.py`
- 必要时拆分 `backend/app/models/ticket_action.py`

要求：

- `Ticket` 声明全部新字段和人员关系。
- `TicketStateLog` 增加 `action`、`comment`、`payload_snapshot JSONB`、`state_version`、`responsible_role_snapshot`。
- 如果继续复用 `ArticleAttachment`，增加 `ticket_id`、`stage`、`uploader_id`，使创建阶段附件不依赖 Article。
- 所有用户输入文本定义明确长度；报告正文使用 `Text`。

## 4. 第二批：领域状态机与权限

### BE-03 集中定义枚举

新增建议文件：`backend/app/domain/poc_workflow.py`。

集中定义：

- `BusinessRole`
- `TicketState`
- `TicketAction`
- `Priority`
- `VerificationStatus`
- `TRANSITIONS`
- `ACTION_REQUIREMENTS`

删除散落在 API、报表、导出代码中的重复字符串映射。旧 `backend/app/services/state_machine.py` 可以替换或改为仅调用该领域模块。

验收：单元测试遍历所有状态，确保每个非终态至少有一个允许动作，终态没有正向动作。

### BE-04 实现动作服务

新增建议文件：`backend/app/services/poc_workflow.py`。

入口建议：

```python
async def execute_action(
    db: AsyncSession,
    ticket: Ticket,
    actor: User,
    action: TicketAction,
    payload: dict,
    comment: str | None,
    expected_version: int,
) -> Ticket:
    ...
```

执行顺序必须固定：

1. 校验工单非终态。
2. 校验 `expected_version == ticket.state_version`。
3. 校验当前状态允许该动作。
4. 校验用户角色。
5. 校验人员范围：审批人、创建人、分系统负责人等。
6. 校验 payload 必填字段及关联对象角色。
7. 更新业务字段和状态。
8. `state_version += 1`。
9. 写入不可变状态日志和人员快照。
10. 在同一事务中提交。
11. 事务成功后触发通知；通知失败不能回滚业务动作，但必须留失败记录。

禁止继续通过通用 `PATCH /tickets/{id}` 直接修改 `state`、责任人、分系统或审批人。

### BE-05 权限矩阵

| 资源/动作 | presales | approver | taskforce | subsystem | quality | admin |
| --- | --- | --- | --- | --- | --- | --- |
| 创建/保存本人草稿 | 允许 | 禁止 | 禁止 | 禁止 | 禁止 | 允许 |
| 查看本人创建问题 | 允许 | 按审批范围 | 全部未闭环 | 按分系统/本人 | 全部 | 全部 |
| 审批 | 禁止 | 仅 `approver_id=本人` | 禁止 | 禁止 | 禁止 | 允许 |
| 确认和流转 | 禁止 | 禁止 | 允许 | 禁止 | 禁止 | 允许 |
| 接收/计划/分析 | 禁止 | 禁止 | 禁止 | 仅对应分系统负责人 | 禁止 | 允许 |
| 确认计划 | 仅创建人 | 禁止 | 禁止 | 禁止 | 禁止 | 允许 |
| 质量评审 | 禁止 | 禁止 | 禁止 | 禁止 | 允许 | 允许 |
| 缺陷入库 | 禁止 | 禁止 | 禁止 | 禁止 | 允许 | 允许 |
| 用户与基础配置 | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 | 允许 |

所有矩阵规则在服务端实现。列表查询和单条详情使用同一 `ticket_scope_for(user)`，避免“列表看不到但可猜 ID 访问详情”。

## 5. 第三批：Schema 与 API

### BE-06 重写 Ticket Schema

修改 `backend/app/schemas/ticket.py`：

- `TicketCreate` 按总约定创建字段定义（含必填的 `proposer`、`proposer_department`）。
- 草稿允许字段为空，正式提交使用单独 Schema 或业务校验。
- `TicketUpdate` 只允许当前阶段可编辑的非状态字段。
- 新增 `TicketActionRequest`：`action`、`comment`、`payload`、`expected_version`。
- `TicketBrief` 返回列表需要的 POC 字段。
- `TicketDetail` 返回全部字段、人员展示名、附件、`allowed_actions`、当前责任角色/人员、是否逾期。
- 响应中不返回旧字段语义：回访满意度、部门对接人、旧处理状态等。

### BE-07 改造工单 API

主要修改 `backend/app/api/v1/tickets.py`，建议将复杂逻辑移入 service/repository：

- `POST /tickets`
  - 仅 `presales/admin`。
  - 草稿不生成正式编号；正式提交生成编号并进入 `pending_approval`。
  - 校验 `approver_id` 对应有效批准人。
- `GET /tickets`
  - 应用角色数据范围。
  - 支持 `state/priority/skill_group_id/responsible_user_id/is_overdue/verification_status/keyword/date_from/date_to`。
- `GET /tickets/{id}`
  - 应用同一数据范围。
  - 返回 `allowed_actions`。
- `PATCH /tickets/{id}`
  - 禁止更新 `state` 和受保护人员字段。
  - 只允许当前责任人在规定节点编辑规定字段。
- `POST /tickets/{id}/actions`
  - 调用 BE-04 动作服务。
- 删除或暂时下线批量改状态，避免绕过逐节点必填校验。

### BE-08 人员和组织元数据 API

改造 `backend/app/api/v1/common.py`：

- 用户创建/编辑只接受新角色。
- `GET /users?role=approver` 给售前选择批准人。
- `GET /users?role=subsystem&skill_group_id=x` 给专项小组选择分系统负责人。
- `GET /skill-groups` 继续作为分系统列表。
- 删除 `dispatchers` 和 `handlers` 旧语义接口，或返回 `410 Gone`，前端不得继续调用。
- 非管理员元数据接口只返回流程需要的最小人员字段：`id/name/roles/skill_groups`。
- 用户角色改用 `user_roles` 关联表，一人可多角色；接口一律以 `roles: string[]` 表达
  （见总约定 2 与 6.4）。

## 6. 第四批：附件、通知、导出

### BE-09 附件

修改 `backend/app/api/v1/articles.py` 或新增 `attachments.py`：

- 提供 `POST /tickets/{id}/attachments`。
- 支持总约定文件类型。
- 上传前检查工单访问权限和当前节点编辑权限。
- 下载改为鉴权接口，例如 `GET /attachments/{id}/download`。
- 文件名随机化；原文件名只存元数据；校验 MIME、扩展名、大小。
- 列表/详情只返回鉴权下载地址，不返回真实磁盘路径。

### BE-10 通知事件

扩展 `backend/app/services/notification.py`：

- 针对每个正向流转通知下一责任角色/人员。
- 退回通知退回后的责任人。
- 计划到期前和逾期提醒可放第二阶段；第一阶段至少实现动作后的即时通知。
- 保存通知类型、接收人、发送结果、错误原因。
- 机器人未配置或发送失败不得阻断状态动作。

### BE-11 跟踪表导出

改造 `GET /tickets/export`：

- 默认导出 POC 跟踪字段。
- 字段至少包含编号、名称、客户、产品线、级别、类型、发生时间、当前阶段、当前责任人、分系统、计划完成时间、是否逾期、验证状态、缺陷 ID、SVN 路径、创建/闭环时间。
- 导出查询必须复用列表数据权限。

## 7. 清理项

后端全局搜索并移除业务使用：

```text
agent
handler
dispatcher
pending/open/resolved/on_hold/archived
callback/is_callbacked/satisfaction
p1_urgent/p2_high/p3_normal/p4_enterprise
```

数据库历史兼容代码若暂时保留，必须标注为 migration-only，不得出现在 OpenAPI 枚举及新响应中。

更新 `backend/scripts/seed.py`，创建每种业务角色的测试账号和五个分系统，不再生成旧角色测试用户。

## 8. 自动化测试

新增：

- `backend/tests/test_poc_workflow.py`
- `backend/tests/test_poc_permissions.py`
- `backend/tests/test_poc_validation.py`
- `backend/tests/test_poc_attachments.py`

最低覆盖：

1. 主流程从创建到闭环完整成功。
2. 每个动作当前角色成功、其他五类角色均返回 `403`。
3. 人员角色正确但不是指定审批人/创建人/分系统负责人时返回 `403`。
4. 每个业务必填字段缺失返回 `400/422`。
5. 非法跳状态返回 `400`。
6. 旧角色、旧状态、旧优先级返回 `422`。
7. `expected_version` 冲突返回 `409`。
8. 退回三个路径可以修改后重新提交。
9. 未填写缺陷 ID 或 SVN 路径不能闭环。
10. 无权限用户不能通过详情、附件下载或导出读取工单。

执行：

```bash
cd backend
pytest
```

## 9. 后端交付检查

- Alembic 升降级通过。
- `pytest` 全部通过。
- Swagger 中没有旧业务角色、旧状态和旧优先级。
- 提供一套从售前到质量的联调账号。
- 提供前端需要的 OpenAPI/接口示例。
- 提供一条可完整流转的种子 POC 问题或联调脚本。
