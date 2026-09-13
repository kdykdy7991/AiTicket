# POC 问题闭环改造：开发总约定

## 1. 目标与范围

本分支将现有客服工单系统改造成仅服务 POC 质量问题闭环的独立项目。第一目标是跑通以下主流程：

```text
售前提交
→ 批准人审批
→ 专项小组确认问题并选择分系统（确认即流转到分系统）
→ 分系统提交闭环计划
→ 售前确认闭环计划
→ 分系统提交分析验证结果
→ 质量评审
→ 批准人复核
→ 已闭环
```

本期不兼容原客服工单流程，不保留旧业务角色、旧状态和旧业务文案。`admin` 作为隐藏系统管理员保留，只用于用户、组织及基础配置，不在业务角色选择器、工单责任人选择器和流程时间线中展示为业务角色。

原始业务依据：

- [POC 质量问题闭环流程](../08_poc_quality_issue_process.md)
- [POC 问题反馈表字段](../09_poc_feedback_form_fields.md)

## 2. 固定业务角色

前后端统一使用以下编码，不得自行增加别名：

| 编码 | 展示名称 | 主要职责 |
| --- | --- | --- |
| `presales` | 售前 | 创建问题、确认闭环计划、参与验证 |
| `approver` | 批准人 | 审批售前提交的问题；质量评审后复核并批准闭环 |
| `taskforce` | 专项小组 | 确认问题描述并选择分系统，确认即流转（不通过则驳回） |
| `subsystem` | 分系统 | 接收、制定计划、分析整改及验证 |
| `quality` | 质量 | 跟踪、组织评审、给出验证结论 |
| `admin` | 系统管理员 | 隐藏管理角色；业务操作兜底 |

约束：

- 删除前端所有 `agent`、`handler`、`dispatcher` 的角色选项和业务文案。
- 后端 API 不再接受上述旧角色编码。
- **一个用户可以拥有一个或多个业务角色**（`user_roles` 关联表，值为上表编码，至少一个）。同一个人的不同职责不再需要拆成多个账号。
- 多角色用户的权限按并集生效：
  - 数据范围 = 各角色数据范围的并集；
  - 可执行动作 = 各角色动作规则与对应人员范围都满足的并集（`allowed_actions`）；
  - 流程节点上的「当前责任角色」仍由**工单状态**决定（单值），与操作人拥有几个角色无关。
- `subsystem` 用户通过 `skill_groups` 关联一个或多个分系统；拥有 `subsystem` 角色的用户才可被选为分系统负责人。
- `taskforce` 可查看**批准人批准之后**的未闭环 POC 问题（`pending_routing` 起），
  用于判断涉及分系统。待审批（`pending_approval`）阶段问题尚未进入专项小组环节，
  专项小组不可见；被批准人驳回后处于 `returned` 且退回目标为 `pending_approval`
  的问题同样不可见。
- `quality` 可查看全部 POC 问题。
- `presales` 默认只能查看本人创建的问题；如保留组长能力，暂不在第一阶段开放。
- `approver` 可查看待本人审批及本人处理过的问题。
- 人员接口统一用 `roles: string[]` 表达角色；`GET /users?role=x` 的含义是「**拥有**角色 x 的用户」。

## 3. 固定状态定义

前后端统一使用以下编码：

| 顺序 | 编码 | 展示名称 | 当前责任角色 |
| --- | --- | --- | --- |
| 1 | `pending_approval` | 待审批 | 批准人 |
| 2 | `pending_routing` | 待确认流转 | 专项小组 |
| 3 | `planning` | 闭环计划制定 | 分系统 |
| 4 | `pending_plan_confirmation` | 待计划确认 | 售前 |
| 5 | `processing` | 分析验证 | 分系统 |
| 6 | `pending_quality_review` | 待验证确认 | 质量 |
| 7 | `pending_final_approval` | 待批准人复核 | 批准人 |
| 8 | `closed` | 已闭环 | 无 |
| — | `returned` | 已退回 | 根据 `return_to_state` 确定 |
| — | `cancelled` | 已撤销 | 无 |

专项小组节点为**一步到位**：确认问题描述、选定分系统与分系统负责人都在
`pending_routing` 一次完成，通过即流转到分系统（直接进入 `planning`），
分系统无需再确认接收。

### 3.1 正向动作

| 当前状态 | 动作编码 | 下一状态 | 操作角色 | 后端必填数据 |
| --- | --- | --- | --- | --- |
| `pending_approval` | `approve` | `pending_routing` | `approver` | 可选审批意见 |
| `pending_routing` | `route` | `planning` | `taskforce` | `skill_group_id`、`subsystem_owner_id`；`confirmation_comment` 必填 |
| `planning` | `submit_plan` | `pending_plan_confirmation` | 对应 `subsystem` | `initial_investigation`、`long_term_measure`、`planned_completion_at`；临时措施可选 |
| `pending_plan_confirmation` | `confirm_plan` | `processing` | 创建该问题的 `presales` | 可选确认意见 |
| `processing` | `submit_analysis` | `pending_quality_review` | 对应 `subsystem` | `root_cause`、`analysis_report`（举一反三） |
| `pending_quality_review` | `pass_review` | `pending_final_approval` | `quality` | `verification_status`、`verification_conclusion`、`quality_review_result` |
| `pending_final_approval` | `approve_closure` | `closed` | 该问题的 `approver` | 可选复核意见 |

### 3.2 退回和撤销

- 审批人可以执行 `reject`，填写原因后进入 `returned`，`return_to_state=pending_approval`，由创建人修改后重新提交。
- 专项小组、售前、质量、批准人可以执行 `return`，必须填写原因，并明确 `return_to_state`。
  - 专项小组在 `pending_routing` 判定不通过时即执行 `return`（界面文案「驳回」）。
  - 批准人在 `pending_final_approval` 复核不通过时即执行 `return`（界面文案「驳回」）。
- 第一阶段限定退回目标：
  - 待确认流转驳回 → `pending_approval`
  - 计划确认退回 → `planning`
  - 质量评审退回 → `processing`
  - 批准人复核驳回 → `pending_quality_review`
- **退回后一步修订**：`returned` 状态下只放行与 `return_to_state` 匹配的处置动作，
  由该节点的责任人在同一次提交里修订字段并回到流程，不需要先“重新提交”再执行节点动作；
  界面文案统一为「修订并…」。

  | 退回目标 | 责任人 | 退回态动作 | 可修订字段 | 结果状态 |
  | --- | --- | --- | --- | --- |
  | `pending_approval` | 创建人（`presales`） | `resubmit` | 创建阶段字段 | `pending_approval` |
  | `planning` | 该分系统负责人 | `submit_plan` | 闭环计划字段 | `pending_plan_confirmation` |
  | `processing` | 该分系统负责人 | `submit_analysis` | 分析验证字段 | `pending_quality_review` |
  | `pending_quality_review` | `quality` | `pass_review` | 评审字段 | `pending_final_approval` |

- 携带与当前退回目标无关的字段一律 `422`；`returned` 只是动作展示状态。
- 创建人可在 `pending_approval` 或 `returned` 执行 `cancel`；管理员可兜底撤销未闭环问题。
- `closed`、`cancelled` 为终态。

## 4. 固定优先级

| 编码 | 展示名称 |
| --- | --- |
| `p0_blocker` | P0 阻断 |
| `p1_critical` | P1 严重 |
| `p2_normal` | P2 一般 |
| `p3_low` | P3 低 |

默认值为 `p2_normal`。旧编码 `p1_urgent`、`p2_high`、`p3_normal`、`p4_enterprise` 不得继续出现在页面和新接口中。

## 5. 数据字段契约

### 5.1 创建阶段字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `title` | string(500) | 是 | 问题名称 |
| `proposer` | string(100) | 是 | 提出人：实际反馈问题的人（售前组使用公用账号，必须手填） |
| `proposer_department` | string(100) | 是 | 提出部门：提出人所属部门 |
| `product_line` | string(100) | 是 | 产品线；第一阶段文本输入 |
| `customer_name` | string(100) | 是 | 客户名称 |
| `priority` | enum | 是 | 固定 P0—P3 编码 |
| `problem_type` | string(100) | 是 | 第一阶段文本输入 |
| `closure_requirement` | text | 是 | 闭环时限或要求 |
| `occurred_at` | datetime | 是 | 问题发生时间 |
| `location` | string(300) | 是 | 地点描述 |
| `longitude` | decimal(10,7) | 否 | 经度 |
| `latitude` | decimal(10,7) | 否 | 纬度 |
| `device_info` | text | 是 | 设备名称、型号、编号、版本、配置等 |
| `description` | text | 是 | 问题现象概述 |
| `approver_id` | bigint | 是 | 必须是有效 `approver` |
| `attachments` | file[] | 否 | 现场照片或其他证据 |

`proposer` / `proposer_department` 是**业务字段**，与系统自动生成的 `creator_id` /
`creator_department`（账号及其部门快照）不同：售前使用公用账号时，前者才代表真实的
提出人和提出部门。二者都必须在正式提交时非空，草稿可以为空。

系统自动生成：`number`、`creator_id`、`creator_department` 快照、`created_at`、初始状态。

### 5.2 后续阶段字段

| 字段 | 类型 | 写入节点 |
| --- | --- | --- |
| `confirmation_comment` | text | 确认并流转（`route`）|
| `skill_group_id` | bigint | 问题流转 |
| `subsystem_owner_id` | bigint | 问题流转 |
| `temporary_measure` | text | 闭环计划 |
| `long_term_measure` | text | 闭环计划 |
| `planned_completion_at` | datetime | 闭环计划 |
| `plan_confirmation_comment` | text | 售前确认计划 |
| `initial_investigation` | text | 闭环计划 |
| `root_cause` | text | 分析验证 |
| `analysis_report` | text | 分析验证（界面名称：举一反三） |
| `actual_completion_at` | datetime | 分析验证提交时自动写入 |
| `verification_status` | enum | 质量评审（通过后进入批准人复核）|
| `verification_conclusion` | text | 质量评审 |
| `quality_review_result` | text | 质量评审 |

`verification_status` 固定值：`resolved`、`temporarily_resolved`、`pending_reproduction`、`unresolved`。

## 6. API 契约

保留统一前缀 `/api/v1`。后端先提供 OpenAPI，前端可以按本节先行开发 Mock。

### 6.1 工单 CRUD

| Method | Path | 用途 |
| --- | --- | --- |
| `POST` | `/tickets` | 新建或保存草稿；正式提交进入 `pending_approval` |
| `GET` | `/tickets` | 按状态、级别、分系统、责任人、逾期等查询 |
| `GET` | `/tickets/{id}` | 返回完整字段、当前允许动作、时间线及附件 |
| `PATCH` | `/tickets/{id}` | 仅修改当前状态允许编辑的字段，不承担状态流转 |
| `POST` | `/tickets/{id}/actions` | 所有状态动作统一入口 |
| `GET` | `/tickets/{id}/state-logs` | 流程时间线 |
| `POST` | `/tickets/{id}/attachments` | 上传附件 |
| `GET` | `/tickets/export` | 导出 POC 跟踪表 |

### 6.2 动作请求

```json
{
  "action": "submit_plan",
  "comment": "可选动作意见",
  "payload": {
    "temporary_measure": "临时绕行",
    "long_term_measure": "升级终端软件并补充回归测试",
    "planned_completion_at": "2026-09-20T18:00:00+08:00"
  }
}
```

成功统一返回完整 TicketDetail。失败规则：

- `400`：当前状态不支持该动作或缺少业务必填字段。
- `403`：角色、人员或分系统范围不匹配。
- `404`：工单、用户或分系统不存在。
- `409`：请求状态版本与数据库不一致；前端应刷新详情。
- `422`：字段格式或枚举错误。

### 6.3 TicketDetail 必备派生字段

```json
{
  "state": "planning",
  "current_responsible_role": "subsystem",
  "current_responsible_user_id": 123,
  "allowed_actions": ["submit_plan", "return"],
  "is_overdue": false,
  "state_version": 5
}
```

前端按钮权限只以 `allowed_actions` 控制显示；后端必须再次校验，不得信任前端。

### 6.4 人员与角色接口（多角色）

人员对象统一使用 `roles: string[]`（至少一个业务角色编码），不再有单值 `role` 字段。

| Method | Path | 用途 |
| --- | --- | --- |
| `POST` | `/auth/login` | 响应 `user.roles: string[]` |
| `GET` | `/users` | 支持 `role`（拥有该角色的用户）、`skill_group_id`、`keyword`、`include_inactive` |
| `POST` | `/users` | 请求体 `roles: string[]`（至少一个） |
| `PATCH` | `/users/{id}` | 同上；`roles` 全量替换 |

约束：

- `roles` 至少一个；非法编码返回 `422`。
- `roles` 含 `subsystem` 时才允许填写 `skill_groups`，否则忽略并清空分系统关联。
- 不允许移除最后一个启用状态 `admin` 的 `admin` 角色（`400`）。
- 流程时间线中的操作人角色以 `operator_roles: string[]` 返回。
- 非管理员调用 `GET /users` 仍只返回流程需要的最小字段，且不返回 `admin` 角色用户。

## 7. 附件契约

第一阶段允许：`jpg`、`jpeg`、`png`、`webp`、`pdf`、`doc`、`docx`、`xls`、`xlsx`、`txt`、`log`、`zip`。单文件上限沿用后端配置，建议默认 20 MB。
仅创建该问题的售前人员可在问题进入终态前上传附件；其他角色（含管理员、批准人、专项小组、分系统和质量）只能按数据权限查看或下载已有附件。

附件需要记录 `stage`，固定值与上传时工单状态一致。下载必须经过工单查看权限校验，禁止把存储目录直接公开为任意可猜 URL。

## 8. 联调顺序

1. 后端提交角色、状态、优先级常量和基础查询接口；前端同步常量。
2. 后端完成建单与详情；前端完成新建页、列表页和只读详情。
3. 后端逐个完成 `/actions`；前端按状态逐个接入操作卡片。
4. 联调附件。
5. 联调退回、撤销和并发冲突。
6. 联调导出、通知和逾期显示。

## 9. 完成定义

- 使用五个业务角色账号可以完整走通主流程。
- 页面及 API 返回中不存在旧业务角色和旧状态文案。
- 每一步越权操作均返回 `403`。
- 必填字段缺失无法流转。
- 每次动作记录操作人、时间、前后状态、意见和人员快照。
- 退回后能够修订并重新进入正确节点。
- 最终必须经质量评审并得到批准人复核批准才能闭环。
- 前后端构建、类型检查和自动化测试通过。
- 多角色用户可以在同一张工单上依次完成其拥有的角色的全部动作。

## 10. 变更记录

| 日期 | 变更 | 影响 |
| --- | --- | --- |
| 2026-09-12 | 建立 POC 契约（单角色） | 初版 |
| 2026-09-12 | 创建阶段新增必填字段 `proposer`（提出人）、`proposer_department`（提出部门） | 售前改用公用账号后需手填真实提出人与部门；列表/详情/导出与「POC 问题反馈表」一致。 |
| 2026-09-12 | 「普通用户只能拥有一个业务角色」→ 支持一人多角色 | `users.role` 单值列改为 `user_roles` 关联表；人员/登录/时间线接口的 `role` 改为 `roles: string[]`；数据范围与 `allowed_actions` 按角色并集计算；`GET /users?role=x` 语义改为「拥有该角色」。前后端同时改造。 |
| 2026-09-12 | 退回后改为「一步修订」 | `returned` 状态下按 `return_to_state` 放行对应节点的动作（`resubmit` / `submit_plan` / `submit_analysis` / `pass_review`），责任人可在同一次提交里修订字段并回到流程；此前必须先 `resubmit` 再执行节点动作，且退回态没有任何可改内容。 |
| 2026-09-12 | 删除「待缺陷入库」节点，质量评审后新增「待批准人复核」 | 删除状态 `pending_defect_registration` 与动作 `register_defect`：缺陷入库在 SVN 侧完成，不作为工单系统内的流转节点，工单也不再记录缺陷 ID / SVN 路径（数据库列一并删除）。`pass_review` 目标改为 `pending_final_approval`；新增 `approve_closure`（批准闭环，角色 `approver`、人员范围为该问题的 `approver_id`），批准即 `closed`；批准人可执行 `return` 驳回并退回 `pending_quality_review`。 |
| 2026-09-12 | 「待问题确认 / 待流转 / 待分系统接收」三步合并为一步 | 删除状态 `pending_confirmation`、`pending_acceptance` 与动作 `confirm_problem`、`accept`；`approve` 目标改为 `pending_routing`（展示名「待确认流转」）；专项小组用 `route` 一次完成确认与流转，目标改为 `planning`，必须填写 `confirmation_comment`；专项小组不通过时执行 `return`（界面显示「驳回」）回 `pending_approval`；`acceptance_comment` 不再产生。主流程由 10 步变为 8 步。 |
| 2026-09-12 | `taskforce` 数据范围由「全部未闭环问题」收紧为「批准人批准之后的未闭环问题」 | 待审批阶段问题归售前与批准人，专项小组不再可见（列表、详情、附件、导出、统计一致生效）；`pending_routing` 起可见。被批准人驳回退回售前（`returned` + 退回目标 `pending_approval`）的问题同样不可见。 |
