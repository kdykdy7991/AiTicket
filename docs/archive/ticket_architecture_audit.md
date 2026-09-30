# 工单流程架构审计报告

> 审计对象：当前工作区代码（分支 `main`，HEAD `0d59869`，含未提交工作区改动）
> 审计方式：只读代码走查，未修改任何业务代码，未创建 commit
> 目标骨架：Ticket / State Machine / Task / Routing Rule / Responsible System / SLA / Flow Log

**先说结论口径**：本报告严格区分两件事——
- 「业务上已经实现」= 现在真实可跑的流程（建单 → 分派 → 处理 → 归档/回访）。
- 「架构上已经抽象」= 是否存在独立、可配置、可替换的层。

当前项目**业务上**是一条"客服工单单责任人流程"，**架构上**已有状态校验、路由配置、SLA 配置、状态日志四块半成品抽象，但**任务（Task）层完全缺失**。需求中反复出现的"售前审批、五个责任系统并行判定、是/否判定、响应措施分别提交、售前确认"等能力——在当前检出分支中**全部未发现**（详见 §4/§7/§8）。仓库中另有一个并行分支 `poc/workflow-changes` 承载了另一套"质量问题闭环"状态机契约（见 §1.7），它不在当前工作区。

---

## 一、项目结构梳理（仅工单流程相关）

### 1.1 后端入口
- `backend/app/main.py` — FastAPI `app`；`lifespan` 内 `start_sla_scanner()/stop_sla_scanner()`；挂载 8 个 router（`auth / tickets / articles / users / groups / skill_groups / categories / regions / sla / stats / routing`，见 `main.py:107-117`）。

### 1.2 ORM / Model
- `backend/app/models/`，Base 来自 `backend/app/core/database.py`：
  - `ticket.py` — `Ticket`、`Article`、`ArticleAttachment`、`TicketStateLog`、`Reminder`
  - `group.py` — `Group`、`SkillGroup`、`UserSkillGroup`
  - `category.py` — `TicketCategory`、`Region`
  - `routing.py` — `CategoryRoutingRule`
  - `sla.py` — `SLAPolicy`
  - `complaint.py` — `ComplaintEscalationPolicy`
  - `audit.py` — `AuditLog`（**空壳，全仓无写入点**，见 §10）
  - `notification.py` — `DingtalkNotification`；`user.py` — `User`
- 全量注册见 `backend/app/models/__init__.py`（本文后续用它证明"没有 Task 模型"）。

### 1.3 API / Router
- `backend/app/api/v1/tickets.py`（1316 行）— 建单/列表/详情/PATCH 流转/批量/草稿/导出/state-logs。
- `backend/app/api/v1/articles.py`（343 行）— 处理说明(reply)/补充(addition)/催办(reminder)+附件。
- `backend/app/api/v1/common.py`（1388 行）— 内含 8 个 router：users、groups、skill_groups、categories、regions、**sla**、stats、**routing**。
- `backend/app/api/v1/auth.py` — 登录。

### 1.4 Service / 业务逻辑
- `backend/app/services/state_machine.py` — 流转规则与校验。
- `backend/app/services/routing.py` — 路由规则校验与 `resolve_rule`。
- `backend/app/services/sla_scanner.py` — SLA 超时扫描（lifespan 后台循环）。
- `backend/app/services/notification.py`、`category_utils.py`。
- **注意**：大量业务逻辑并不在 service 层，而是直接写在 router 里（`tickets.py` 的 `_calculate_sla_deadline`、`check_transition_permission`、`_enforce_business_constraints`、状态副作用 if/elif 链）。`backend/app/domain/` 目录**只剩 `__pycache__`，无源文件**（见 §1.7）。

### 1.5 前端页面与状态管理（Vue3 + Vite + Pinia）
- 入口：`frontend/src/main.ts`，路由 `frontend/src/router/index.ts`。
- 状态管理：`frontend/src/stores/ticket.ts`、`auth.ts`、`overview.ts`、`ui.ts`。
- 关键页面：`frontend/src/views/TicketDetailView.vue`（825 行）、`TicketCreateView.vue`、`TicketListView.vue`、`DashboardView.vue`、`admin/SLAView.vue`。
- 关键组件：`components/ticket/{StateLogTimeline, ReplyEditor, TicketInfoSidebar, ArticleTimeline, TicketTable}.vue`、`components/common/{StateTag, SLAIndicator, PriorityIcon}.vue`。
- **API 适配层（业务规则藏身处）**：`frontend/src/api/tickets.ts`（STATE_MAP / PRIORITY_MAP / STATE_ID_TO_KEY / isReturnTransition）。
- 类型：`frontend/src/types/index.ts`；`frontend/src/mock/` 为遗留 mock 数据。

### 1.6 Migration / Schema / 测试
- **迁移存在两套**：
  - 权威：`backend/alembic/versions/`（`deploy.sh:91,117` 与 `docker-entrypoint` 注释均执行 `alembic upgrade head`）。
  - 遗留 SQL：`backend/migrations/001_init_schema.sql … 012_add_ticket_urge_fields.sql`（**SLA 默认时长的 INSERT 只在这里**，见 §9）。
- 种子：`backend/scripts/seed.py`（`seed()` + `seed_phase9_base_data()`），CLI 由 `Makefile` 调用。
- 测试：
  - 单测/API 测：`backend/tests/`（`conftest.py` 重建独立库 `skdy_ticket_test` 并跑 alembic，`pytest.ini` asyncio auto）。
  - E2E：`e2e_tests/tests/`（真实 HTTP 打运行中的 API，`helpers.py` 全部按业务属性查 id）、`e2e_tests/scripts/`、报告 `e2e_tests/artifacts/`。
- 文档：`docs/00_overview.md … 07_requirements_supplement.md`、`docs/api_design_v2.md`、根目录 `责任部门与处理时效整理.md`、`责任部门与客户问题处理流程改造交付说明.md`（需求/交付说明，非代码）。

### 1.7 一个必须记录的事实：并行分支
- `git log --all -- backend/app/domain` 显示分支 `poc/workflow-changes`（`8812b20`）上存在 `backend/app/domain/poc_workflow.py`、`backend/app/services/poc_workflow.py`、`frontend/src/api/pocTickets.ts` 等，契约内容为"售前 presales / 批准人 approver / 专项小组 taskforce / 分系统 subsystem / 质量 quality"六角色 + `pending_approval → pending_routing → planning → … → closed` 十状态 + `TicketAction.ACTION_RULES`，优先级为 `p0_blocker…p3_low`。
- **当前检出分支 `main` 不含这些文件**（`app/domain/` 仅残留 `poc_workflow.cpython-312.pyc`）。因此：本报告对该套流程一律记为"当前分支未发现"，但把它列为**架构风险**（两套状态机、两套优先级体系 `p1..p4` vs `p0..p3` 并存于同一仓库的两个分支）。

---

## 二、Ticket 工单模型审计

**Model / 表**：`class Ticket`，`__tablename__ = "tickets"`（`backend/app/models/ticket.py:11-124`）。

### 2.1 核心字段（按代码分组）
- 标识：`id`、`number`（`YYYYMMDD-XXXX`，建单时生成）、`title`、`description`。
- **状态/优先级**：`state: String(30) default "pending"`（`ticket.py:20`）、`priority: String(20) default "p4_enterprise"`（:21）、`channel`。
  - **无 Python/DB 枚举**：state/priority 全部是裸字符串，取值集合散落在 `services/state_machine.py::TRANSITIONS`、`tickets.py::STATE_LABELS(:35)`、导出用 `state_labels(:581)`、前端 `api/tickets.ts::STATE_MAP` 等多处。
- 客户：`customer_type / customer_name / customer_phone / customer_phone_type / contact_phone / customer_company / customer_level / device_sn / region_id / region_name / symptom`。
- **分类与归属**：`category_id`（FK `ticket_categories`）、`group_id`（客服组）、`skill_group_id`（**协调部门**）、`handler_skill_group_id`（**专业处理部门**）、`owner_id`（**专业处理人**）、`creator_id`、`first_owner_id`、`dispatcher_id`（部门对接人）、`returned_to_user_id`（退回目标人）。
- 升级/重复：`is_draft / is_duplicate / is_escalated / duplicate_reason / linked_ticket_id`。
- **SLA 列（直接躺在 tickets 上）**：`first_response_deadline / solution_deadline / first_response_at / solved_at / sla_first_response_breached / sla_solution_breached`。
- 暂缓：`hold_until`。
- 结案：`closed_at / closed_duration_minutes`。
- **解决信息（业务结果）**：`resolved: bool`、`resolution`、`root_cause`、`solution`（`ticket.py:72-76`，Phase 7 由迁移 `h1b2c3d4e5f6` 加入）。
- 投诉：`complaint_level`（一般/重要/重大）。
- 回访/归档：`callback_required / callback_details / archive_notes / is_callbacked / satisfaction`。
- 催办：`urged_at / urged_by_id`；追加/退回标记：`has_addition / has_returned`。

### 2.2 针对性回答
- **是否直接保存责任系统处理结果**：**没有"责任系统级"结果**。全表只有**一套**结果字段（`resolution` / `root_cause` / `solution`），归属单一 `owner_id`。并行分支的交付说明也明确决策："**不引入多 owner，一单一 owner，单责任人模型**"（`责任部门与客户问题处理流程改造交付说明.md` §0 决策表）。
- **根因/方案/响应措施/判定说明**：
  - 根因 → `root_cause`（有）；方案 → `solution` / `resolution`（有）；
  - **"响应措施"字段：未发现**（语义最接近 `solution`）；**"判定说明"字段：未发现**；**"判定结果（是/否）"字段：未发现**。
- **大量 nullable 字段承载不同阶段数据**：是。统计上 `tickets` 约 **30+ 个 nullable/可空阶段列**：SLA 4 组、暂缓 1、结案 2、回访 4、催办 2、退回 1、解决 3、投诉 1、重复升级 4……这些是"各阶段状态快照"而非工单主体属性。
- **判断**：Ticket **不是纯工单主体**。它同时承担了：工单描述 + 客户档案 + 归属路由结果 + SLA 计时器 + 退回目标 + 回访问卷 + 催办状态 + 归档结论。每新增一个流程阶段，当前模式都是"往 tickets 加一列"（Phase 4 `handler_skill_group_id`、Phase 7 `root_cause/solution`、`has_returned`、`satisfaction` 均是此路径，见 alembic `g1a2b3c4d5e6`、`h1b2c3d4e5f6`、`7c8d9e1f2a3b`、`e2f3a4b5c6d7`）。

---

## 三、状态机审计

### 3.1 工单状态（7 个）
来源：`backend/app/services/state_machine.py:23-33`
```
pending 待受理 / open 处理中 / on_hold 暂缓 / resolved 已处理
returned 已退回 / archived 已归档(终态) / cancelled 已撤销(终态)
TRANSITIONS = {
  pending:   [open, cancelled, returned],
  open:      [resolved, on_hold, pending, cancelled],
  on_hold:   [resolved, open, cancelled],
  resolved:  [archived, open, on_hold],
  returned:  [pending, cancelled],
  archived:  [], cancelled: [],
}
```
初始态校验 `validate_initial_state`：`None→pending`（默认）与 `None→archived`（即时办结，`state_machine.py:36-39`）。

### 3.2 逐问回答
1. **状态有哪些**：上列 7 个（docstring 写"8 状态"，与实际 7 个不符——`state_machine.py:1` 注释写 7 状态、:22 注释又写"8 状态流转规则"，注释本身已漂移）。
2. **是否有统一状态枚举**：**没有 Enum**。只有字符串常量集合 `TRANSITIONS` / `TERMINAL_STATES` / `STATES_REQUIRE_REASON_FROM`。同样的字符串在**后端至少 3 份**（`state_machine.py`、`tickets.py::STATE_LABELS:35`、`tickets.py::state_labels:581`、`articles.py` 的 `*_ALLOWED_STATES:25-31`）、**前端至少 4 份**（`api/tickets.ts::STATE_MAP:17`、`stateLogStrToObj:114`、`stateStrToObj:128`、`STATE_ID_TO_KEY:36`、`isReturnTransition` 权重表:50-58；`TicketDetailView` 的 `TERMINAL_STATES:221`；`ReplyEditor:185-187`）。
3. **是否有统一 transition 函数/service**：**部分**。有统一**校验**（`validate_transition`），**没有统一"执行流转"的 service**——状态赋值与副作用分散在 4 条路径（见下）。
4. **是否校验 from→to**：是。`validate_transition(from, to)` 抛 `StateTransitionError`（`core/exceptions.py:39`），被 3 处调用：`tickets.py:1075`（PATCH）、`tickets.py:1246`（batch）、`articles.py:232`（reply）。另有 `requires_reason` 校验必填原因（`tickets.py:1081`）——**但只在 PATCH 这一条路径生效**。
5. **是否可能被多个接口直接修改**：**是，4 处**：
   | 路径 | 位置 | validate | 权限校验 | reason 校验 | 副作用(solved_at/closed_at/first_owner…) |
   |---|---|---|---|---|---|
   | `PATCH /tickets/{id}` | `tickets.py:1069-1153` | ✅ | ✅ `check_transition_permission` | ✅ | ✅ 完整 if/elif 链 |
   | `POST /tickets/batch-update` | `tickets.py:1242-1258` | ✅ | ❌ **无** | ❌ **无** | ❌ **只写 state+log+has_returned**（不写 `solved_at`/`closed_at`/`first_owner_id`） |
   | `POST /tickets/{id}/articles` type=reply | `articles.py:230-276` | ✅ | 仅"必须是 owner" | 不适用 | ✅ 自己复刻一份（`solved_at/resolved/sla_breach`） |
   | 建单（即时办结 None→archived / 正常 None→pending） | `tickets.py:876-932, 1020-1025` | `validate_initial_state` 在 create 流程未被显式调用，直接赋 `state="archived"` | 创建者角色 `require_role("admin","agent")` | — | ✅ 自己写一套 |
   - 结论：`batch-update` 是**绕过权限矩阵与副作用逻辑**的口子（admin/agent 角色即可把任意工单改成任意合法目标态，且 `resolved` 不会写 `solved_at`）。
6. **支持回退/重新处理/重开**：**支持**，且是纯状态表驱动：
   - 退回：`pending→returned`、`open→pending`、`on_hold→open`、`resolved→open/on_hold`；`RETURN_TRANSITIONS` 集合用于同步 `has_returned`（`tickets.py:45-48`）。
   - 重新提交：`returned→pending`（`tickets.py:1095-1099` 清 owner）。
   - 重开/重新处理：`resolved→open`（允许客服重新打回）。
   - 终态不可逆：`TERMINAL_STATES`（`state_machine.py:52`），单测 `backend/tests/test_instant_resolve.py:141 test_archived_ticket_cannot_be_transitioned` 验证。
   - 业务约束改写：`_enforce_business_constraints` 把 `resolved→on_hold` 强制改成 `resolved→open`（`tickets.py:69-87`）——**同一规则前端也实现了一遍**（`TicketDetailView.resolveReturnTarget:499-519`，还额外实现"跳过 on_hold 找上一个状态"），后端这版只兜底不决策。
7. **状态变化是否自动写日志**：**是**，4 条路径都 `db.add(TicketStateLog(...))`（`tickets.py:711,927,1021,1147,1248`；`articles.py:246`）。**但**：
   - 非状态的字段变更（改 priority/owner/部门/分类）**不写任何日志**；
   - `articles.py:246` 的 reply 先 flush 拿 id 当 `state_key`，日志与业务动作通过 `state_key` 关联（仅 reply/reminder 使用）；
   - `AuditLog` 无写入点（§10）。

### 3.3 定性结论
**选 B：有统一状态流转服务，但还不是完整状态机。**

证据：
- 偏 A 的部分：单一规则表 `TRANSITIONS` + 单一 `validate_transition` + `requires_reason` + `TERMINAL_STATES`，且主要 PATCH 路径带权限矩阵 `check_transition_permission`（`tickets.py:273-344`，admin 全权限 + 按 (from,to) 分派给 dispatcher/owner/creator/agent）。
- 偏 C 的部分：**状态赋值与副作用不是单入口**——`batch-update` 无权限/无 reason/无副作用（`tickets.py:1242-1258`）、`articles` reply 自带一份副作用（`articles.py:272-276`）、建单路径直接字面量赋值；退回目标状态由前端 `resolveReturnTarget` 决定。
- 没有 action 概念：状态变更的"动作名"（分派/打回/暂缓/归档）没有进入日志，只能靠 (from,to,operator,reason) 反推。

---

## 四、Task / 待办任务模型审计（本次最重要项）

### 4.1 是否存在 task/todo/assignment/work_item 表或 Model
**未发现。**
- `backend/app/models/__init__.py:1-22` 列出全部模型：`Group / SkillGroup / UserSkillGroup / User / TicketCategory / Region / Ticket / Article / TicketStateLog / Reminder / SLAPolicy / DingtalkNotification / AuditLog / CategoryRoutingRule` —— **没有任何 Task 类**。
- 全仓 `grep "class .*(Task|Todo|Assignment|WorkItem|Decision|ResponseAction|Judgment)"` → 0 命中。
- `grep -rn "task|todo|assignment|work_item" backend/app` 只命中 `sla_scanner.py` 的 `asyncio.Task`（技术实现，非业务）。
- 最接近的两个既有概念都不是 task：
  - `Article`（`ticket.py:127-148`）：沟通记录，字段 `type/sender_id/body/state_key/append_reason`——**没有 assignee、没有 status、没有 completed_at、没有 result**。
  - `Reminder`（`ticket.py:194-203`）：催办留言，只是 article 的兄弟表。

### 4.2 逐问回答
1. **task 表/Model**：**未发现**。
2. **一张 ticket 对应多个 task**：**做不到**，因为没有 task。当前模型是"一单一 owner"：`tickets.owner_id` 单值（`ticket.py:44`）；交付说明 §0 明确"**不引入多 owner，一单一 owner，单责任人模型**"。
3. **task 的 type/assignee/status/created_at/completed_at/result**：**6 个字段全部未发现**。
4. **五个责任系统并行判断时的实现方式**：
   - **创建 5 个独立 task：未发现**
   - **创建 5 条关联记录：未发现**
   - **Ticket 上写 5 组字段：未发现**
   - **其他实现：也未发现**——当前代码里根本不存在"多责任系统并行判定"这个环节。与之最接近的现有结构只有**一组**归属字段：`skill_group_id`（协调部门）+ `handler_skill_group_id`（专业处理部门）+ `dispatcher_id` + `owner_id`（见 §2）。
   - 佐证：`grep -rn "责任系统|响应措施|售前|判定"` 在 `backend/`、`frontend/` 的源码中 0 命中（仅命中根目录需求/交付文档与测试数据里的"测运控系统"等分类名）。
5. **一个系统认领后，响应措施是否生成新任务**：**未发现该环节**。现存最接近链路是：对接人 `pending→open` 指定唯一 `owner_id` → owner 提交 `type=reply` 的 Article → 工单直接 `resolved`（`articles.py:230-276`）。**不生成任何新任务，只是修改原 ticket 的字段**。
6. **多系统共同处理如何表示**：**未发现**。现有唯一"并行"是通知语义而非数据结构：需求文档 `责任部门与处理时效整理.md:108` 描述"售后牵头 + 协同部门并行抄送"，但代码里**没有对应表**——所谓"并行"目前只能靠人工把多个人塞进 `skill_group`/`group`，或发多个钉钉 webhook。

### 4.3 判断
- **业务上**：单责任人流程已实现（建单→分派→处理→归档）。
- **架构上**：**Task 层基本缺失**。这是距离目标骨架最远的一块：一旦要支持"5 个系统并行判定 / 分别提交响应措施 / 全否退回"，当前**没有可复用的抽象**，只能继续往 `tickets` 加字段（重演 `root_cause/solution/has_returned` 的加列模式），或新建实体。

---

## 五、责任系统 / 部门配置审计

### 5.1 各层对应物
| 目标概念 | 当前实现 | 位置 |
|---|---|---|
| 责任系统 | **无独立实体**；最接近的是 `SkillGroup`（专业/协调部门，如"测运控组"） | `models/group.py:23-32 class SkillGroup`（字段仅 `name / dingtalk_webhook_url`） |
| 部门（客服侧） | `Group` | `models/group.py:11-20` |
| 负责人 | `User` + 关联表 `UserSkillGroup(user_id, skill_group_id, is_dispatcher)` | `models/group.py:35-40` |
| 部门→工单 | `tickets.skill_group_id`（协调）、`tickets.handler_skill_group_id`（专业） | `ticket.py:40-43` |
| 部门→分类路由 | `CategoryRoutingRule.dispatcher_skill_group_id / dispatcher_id / handler_skill_group_id / owner_id` | `models/routing.py:27-88` |
| enabled/active/sort | `CategoryRoutingRule.enabled`（:64）、`TicketCategory.is_active/sort_order`（`category.py:18-19`）、`User.is_active`、**SkillGroup 无 enabled/sort 字段** | — |

### 5.2 是否通过业务属性查找
- **代码层**：按 id 外键关联（正常）。
- **种子层**：`seed.py` 两条路线并存——`V2_SKILL_GROUPS/V2_USERS/V2_ROUTING_RULES` **写死数字 id**（100-106 / 200-214，`seed.py:339-401`），而 Phase 9 补丁 `V2_MISSING_LEAF_RULES` 特意**按 name 查 id**，注释原话："用业务属性查 id，避免写死 dispatcher_id=10/12/11 这类数字"（`seed.py:457-467, 605-630`）。
- **测试层**：`e2e_tests/tests/helpers.py` 全部按业务属性查找（`find_user_by_name / find_skill_group_by_name / find_category_by_name / find_dispatcher_user`，:271-335），设计原则写明"避免硬编码 id"。而后端单测/E2E 大量写死 category id：`2311/2312/2313`（`e2e_tests/tests/test_business_support.py:157-176`）、`1202/1203/1204`（`backend/tests/test_phase9_base_data.py:282-284`，连人名"钟梦茜/张朝娟/谢志鹏"也写死在 `seed.py:461-466` 与测试断言里）。

### 5.3 硬编码搜索结果
| 搜索项 | `backend/app` 业务代码 | 种子/迁移/测试 |
|---|---|---|
| 系统总体 / 交付售后 / 终端系统 / 应用平台 / 测运控 | **未发现**（无一处写死系统名） | `seed.py:333,424,427`、alembic `f2a3b4c5d6e7:68,73`、测试 `test_v2_categories.py:31,34` 写死为**分类数据** |
| `owner_id` / `dispatcher_id` 特定数值 | **未发现**（都是变量/请求体） | `seed.py:391-400` 写死 210/211/212/213/214 |
| `department_id` / `system_id` | **字段都不存在**（用 `skill_group_id` 表达部门） | — |

### 5.4 "从 5 个责任系统改成 6 个，只改配置即可吗？"
分两种含义：

**(a) 只是新增一个部门/责任方（单责任人路由语义）→ 基本只改数据，不改代码。**
需做的只是数据操作，且三条路都有现成能力：
1. `POST /skill-groups` 建组（`common.py:333 create_skill_group`）；
2. `POST /users` + `skill_groups:[{skill_group_id, is_dispatcher}]` 建负责人（`common.py:94 create_user`）；
3. `POST /routing-rules` 挂分类规则（`common.py:1310 create_routing_rule`，服务层 `services/routing.py:107 create_rule` 带校验）；
4. `resolve_rule` 按父链上溯自动覆盖子孙 leaf（`routing.py:183-259`），无需每个叶子配规则。
唯一代码侧成本：种子里写死的 id 映射（`V2_SKILL_GROUPS` 等）如果不按 name 维护会漂移——但这是种子脚本而非业务代码。

**(b) 是指"6 个系统并行判定"流程 → 不是改配置能解决的，必须改代码。**
因为该流程的载体（Task/Decision 层）不存在（§4）。必须动的地方：
1. 新建实体（表 + `models/__init__.py` 注册 + alembic 迁移）；
2. 状态机：`services/state_machine.py::TRANSITIONS` 要插入判定阶段状态；
3. `tickets.py:update_ticket` 的副作用 if/elif 链（:1088-1132）与 `check_transition_permission`（:273-344）要加新动作与新权限；
4. `TicketDetail` 响应体（`_ticket_to_detail:132-165`）与 `schemas/ticket.py`；
5. 前端：`api/tickets.ts` 的 STATE_MAP/权重表、`TicketDetailView` 的 5 个 canXxx computed、`ReplyEditor` 的允许状态集；
6. 报表/导出的 `state_labels`（`tickets.py:581`）、`common.py` 统计里的状态硬编码（`common.py:807-1020` 多处 `Ticket.state == "pending"` 等字面量）；
7. E2E 场景与报告生成。

---

## 六、Routing Rule 路由规则审计

### 6.1 逐问回答
1. **是否有独立 rule/routing/dispatcher 机制**：**有**。
   - 表/Model：`category_routing_rules`（`models/routing.py:27`，`category_id` UNIQUE）；
   - 服务：`services/routing.py` — `validate_rule_payload / create_rule / update_rule / resolve_rule`；
   - API：`common.py:1265 list_routing_rules / :1310 create_routing_rule / :1332 update_routing_rule / :1359 delete_routing_rule / :1375 resolve_routing_rule`（`POST /api/v1/routing-rules/resolve`）；
   - 消费点：`tickets.py:830-850 create_ticket` 开头调用 `resolve_rule`，命中则填 `skill_group_id / handler_skill_group_id / dispatcher_id`（显式传参优先，未命中回 `auto_match_warning`）。注意 **owner_id 不在建单时自动落**（`tickets.py:845-846` 注释：留给对接人"分派"步骤）。
2. **还是大量 if/elif**：路由本身**不是** if/elif。`grep` 命中的 11 处 `elif` 全部集中在 `tickets.py` 的**状态副作用链**（:1088-1114）与建单分支，属于状态机问题（§3），不属于路由问题。**`backend/app` 里没有任何按 category_id / 分类名的条件分支。**
3. **分类 → 责任系统的关系存在哪里**：**数据库表** `category_routing_rules`，一条规则 = 协调部门 + 协调人 + 专业部门 + 默认处理人 + enabled。
4. **category_id 是否写死**：**业务代码未写死**；写死的只有种子/迁移/测试（`seed.py:327-335 V2_CAT`、alembic `f2a3b4c5d6e7:50-73`、`backend/tests/test_v2_categories.py:19-34`）。
5. **1202/1203/1204 特殊规则如何实现**：**纯数据实现，无特殊代码**。
   - 分类行：alembic `f2a3b4c5d6e7_seed_v2_categories.py:50-52`（品牌合作/产品使用/渠道代理）；
   - 路由行：`seed.py:460-467 V2_MISSING_LEAF_RULES` + `:602-640`（按 name 查 id 后 INSERT，`ON CONFLICT DO NOTHING`）；
   - 为什么当初需要补：注释写明"1202/1203/1204 没被 `V2_ROUTING_RULES` 覆盖，父链上溯也找不到祖先 rule"（`seed.py:589-590`）——即**规则覆盖率依赖人工配置**，不是机制问题；
   - 验证：`backend/tests/test_phase9_base_data.py:271-284`（resolve matched=True）+ `e2e_tests/tests/test_consultation_routing.py:87-106`。
6. **新增一种分类要改数据库还是改代码**：**改数据**。建分类（`common.py:493 create_category`）+ 建/复用规则即可；父链上溯意味着挂在 level-2 的规则自动覆盖新 leaf。
7. **新增一种"处理路径"要改多少处代码**：当前**没有"处理路径"概念**（规则只决定"归谁"，不决定"怎么流转"）。若新增一条路径（如：售前审批 → 并行判定 → 响应措施），至少要改：
   1. `services/state_machine.py`（状态与流转表）
   2. `tickets.py:update_ticket` 副作用链 + `check_transition_permission`
   3. `articles.py` 或新增 router
   4. `schemas/ticket.py`
   5. `common.py` 统计/报表中的状态字面量（`:807-1020`）
   6. `tickets.py` 导出 labels（`:581-591`）
   7. 前端 `api/tickets.ts`（4 份映射）+ `TicketDetailView`（5 个 canXxx + resolveReturnTarget）+ `ReplyEditor`（3 个允许集）
   8. E2E 用例
   **合计 8 个文件量级，且前后端必须同步改。**

### 6.2 关键函数清单
`resolve_rule`（`services/routing.py:183`，父链上溯+enabled 开关+停用人告警）、`create_rule/update_rule`（校验 dispatcher 必须 `is_dispatcher=true`、owner 必须属于 handler 部门，`:47-104`）、`create_ticket` 的 auto-match 段（`tickets.py:830-850`）、`POST /routing-rules/resolve`（`common.py:1375`）。
规则与历史工单解耦（改规则不回溯改老工单）有专门测试：`backend/tests/test_routing_rules.py:235 test_updating_rule_does_not_retroactively_change_tickets`。

---

## 七、责任系统"是/否判定"逻辑审计

### 7.1 结论先行
**该流程在当前分支未发现（代码事实为零）。**

搜索证据（全仓源码，排除文档）：
- `责任系统 / 响应措施 / 售前 / 判定 / 测运控(仅作分类名) / 系统总体 / 交付售后` → `backend/**.py`、`frontend/src/**` **0 命中**；
- `审批 / approval / approve / presale` → `backend/**.py` **0 命中**（仅 `test_auto_match.py:8` 注释里的 "dispatcher must approve" 指分派确认）；
- 无 decision 表、无"是/否"字段、无图片判定附件流程（附件上传仅 `type=addition` 时允许，`articles.py:288-291`）。
- 对应能力只存在于**根目录需求文档**（`责任部门与处理时效整理.md`、`责任部门与客户问题处理流程改造交付说明.md`）与**未合入的 `poc/workflow-changes` 分支**。

### 7.2 逐问回答（按"未发现 + 现存最接近链路"给出）
- **判定结果存在哪里**：未发现。最接近的是 `Ticket.resolution/root_cause/solution`（处理结论，单套字段）与 `Article(type=reply)`（处理说明正文）。
- **是否存在统一 decision record**：**未发现**（无 decision 表，`AuditLog` 也未启用）。
- **"是"以后如何进入响应措施**：未发现该分支。现存链路是提交 reply 即 `open→resolved`。
- **是否立即启动 SLA**：SLA **在建单时就启动**（`_calculate_sla_deadline` 于 `tickets.py:966` 调用，`now + solution_minutes`），与任何判定动作无关；**没有"判定后启动"的钩子**。
- **其他责任系统是否仍可继续判断**：概念不存在——`tickets.owner_id` 单值，第二个"系统"没有可写的位置。
- **全部为否以后如何退回**：未发现"全否退回"逻辑。现存退回是人工动作：对接人 `pending→returned`、处理人 `open→pending` 等（§3.1 表）。
- **是否写死五系统数量**：**没有写死 5**——因为整个流程未实现；当前也不存在任何"系统数量"变量。
- **前端/后端分别承担的判断**：
  - 后端（现存链路）：`validate_transition` + `check_transition_permission` + `requires_reason` + 副作用；
  - 前端：**重复实现了一套**（见 §11），并且**退回目标状态由前端裁决**（`resolveReturnTarget`）。

### 7.3 现存最接近的两条调用链（真实代码）

**A. "认领/分派"链（最接近"某系统接手"）**
```
PATCH /api/v1/tickets/{id}  body={state:"open", owner_id}   (frontend TicketDetailView.confirmDispatch:325)
  → update_ticket (tickets.py:1053)
  → _enforce_business_constraints (tickets.py:69, 本例 no-op)
  → validate_transition("pending","open")          (services/state_machine.py:55)
  → check_transition_permission: 需 is_dispatcher=true 且必须带 owner_id (tickets.py:295-301)
  → requires_reason? 本转换不要求
  → 副作用: ticket.first_owner_id = owner (tickets.py:1088-1091)
  → ticket.state = "open"; TicketStateLog(from=pending,to=open, operator, snapshot) (tickets.py:1133,1147)
  → commit (core/database.py get_db)
  无 Task 创建 / 无 SLA 动作（SLA 已在建单时写入 solution_deadline）
```

**B. "提交结果"链（最接近"判定/响应措施提交"）**
```
POST /api/v1/tickets/{id}/articles  form{type="reply", body}   (frontend ReplyEditor.onSubmit:311)
  → create_article (articles.py:143)
  → 终态拦截 (articles.py:160) / type=reply: 必须 user.id == ticket.owner_id (177) / state ∈ {open,on_hold} (182)
  → validate_transition(old_state,"resolved") (232)
  → TicketStateLog(from, to="resolved") flush → reply_log.id 作为 state_key (246-255)
  → 同一 resolved 节点只允许一条 reply (257-270)  ← 409
  → ticket.state="resolved"; solved_at=now; resolved=True; 超期则 sla_solution_breached=True (272-276)
  → Article(type="reply", state_key=log.id) (278)
  → 附件: 仅 type=addition 才存 (288-291)
  无 decision 记录 / 无 per-system 结果 / SLA 不因本动作启动或停止（只在 resolved 时比对 deadline）
```

---

## 八、响应措施审计

### 8.1 结论
**选 A：Ticket 上只有一套字段**（外加 Article 正文），**不是** B（每系统一套），**不是** C（独立 response_action 表），**不是** D（Task result——无 Task）。

具体承载：
| 需求字段 | 当前对应 | 位置 |
|---|---|---|
| 初步排查结论 | `Ticket.root_cause`（最接近） | `models/ticket.py:75`，迁移 `h1b2c3d4e5f6` |
| 响应措施 | `Ticket.solution` / `Ticket.resolution` | `ticket.py:73,76` |
| 提交状态 | **无独立字段**，用 `Ticket.state` / `resolved` 代替 | `ticket.py:20,72` |
| 提交时间 | `Ticket.solved_at`（reply 时写，`articles.py:273`）、`updated_at` | `ticket.py:60,107` |
| 附件 | `ArticleAttachment`（**仅 `type=addition` 可传**，reply 不收附件） | `models/ticket.py:151-167`、`articles.py:288-291` |
| 责任系统 | `Ticket.handler_skill_group_id`（单一） | `ticket.py:41` |
| 负责人 | `Ticket.owner_id`（单一） | `ticket.py:44` |

### 8.2 多个责任系统同时认领后能否分别提交？
**不能。** 两道硬约束：
1. 数据模型：`owner_id` 单值 + `handler_skill_group_id` 单值，第二个人没有写入位置（`ticket.py:41,44`；交付说明 §0 "不引入多 owner"）。
2. 接口：`articles.py:177` —— `if ticket.owner_id is None or user.id != ticket.owner_id: 403 仅当前处理人可提交处理说明`；`articles.py:257-270` —— **同一 resolved 节点下只能有一条处理说明**（409）。

因此"分别提交各自的响应措施"在底层**没有实现机制**：既不是 5 行表记录，也不是 5 组字段。现状是"一个 owner 提交一次，工单直接 resolved；其他人想补充只能走 `type=addition`（客服/admin 专属，`articles.py:189-199`）且不算响应措施"。

---

## 九、SLA 审计

### 9.1 逐问回答
1. **SLA 规则存在哪里**：
   - 主规则表 `sla_policies`（`models/sla.py::SLAPolicy`：`skill_group_id`(可空=全局)、`priority`、`first_response_minutes`、`solution_minutes`）；
   - 投诉倍率表 `complaint_escalation_policies.sla_resolution_multiplier`（`models/complaint.py:27`，三档 1.0/0.75/0.5，见交付说明 Phase 8）。
2. **P0/P1/P2/P3 时长是否写死**：
   - **业务代码没有写死**：查询在 `_calculate_sla_deadline`（`tickets.py:168-204`），按 `skill_group_id+priority` 先查部门策略、再回退全局；
   - **初始数据写在迁移 SQL**：`backend/migrations/001_init_schema.sql:409-414`：
     ```
     p1_urgent     15 / 120   (首响15分钟 / 解决2小时)
     p2_high       30 / 240
     p3_normal    120 / 480
     p4_enterprise 10 / 60    ← 注意 P4 反而最快，语义存疑
     ```
   - 运行期可通过管理端改：`GET/POST/PATCH/DELETE /sla-policies`（`common.py:687,705,731,749`）+ 前端 `views/admin/SLAView.vue`；
   - **注意优先级体系**：当前分支是 `p1_urgent…p4_enterprise`（**无 P0**）；并行 POC 分支是 `p0_blocker…p3_low`——两套并存。
   - 前端残留写死值：`SLAView.vue:95,124` 默认 `solution_minutes: 480`；`SLAIndicator.vue:24` 兜底 `240` 分钟。
3. **SLA 起点**：**建单时刻**。`_calculate_sla_deadline` 返回 `datetime.now(timezone.utc) + timedelta(minutes)`（`tickets.py:204`），在 `create_ticket`（:966）、即时办结（:891）、草稿提交（:706）、**priority 变更且未解决时**（:1175-1179）写入 `tickets.solution_deadline`。
4. **SLA 终点**：`solution_deadline` 与实际 `solved_at` 比对——
   - 流转到 resolved 时判：`tickets.py:1104-1108`；
   - reply 提交时判：`articles.py:275-276`；
   - 后台兜底扫：`sla_scanner.py:38-49`（每 60s，非终态 + `solved_at IS NULL` + `deadline < now` → 置 `sla_solution_breached=True`）。
5. **started_at / deadline / completed_at**：
   - `started_at`：**无**（用 `tickets.created_at` 代替）；
   - `deadline`：`tickets.solution_deadline`（有）；
   - `completed_at`：`tickets.solved_at`（有），闭环另有 `closed_at`；
   - `first_response_deadline / first_response_at / sla_first_response_breached`：**字段存在但已死**——`common.py:722` 注释 `first_response_minutes=0, # 已废弃，保留字段兼容旧数据`，全仓无写入/扫描逻辑。
6. **pause / resume**：**不支持**。`tickets.py:1102` `TODO(sla-policy): SLA 策略未定，暂不在进/出 on_hold 时调整 solution_deadline`；`sla_scanner.py:32-36` 明确"on_hold 暂不排除，超时仍会标记"，并列出三种待定方案。`hold_until` 字段存了但**不影响计时**。
7. **一个 Ticket 一个 SLA，还是每系统一个**：**一个工单一个解决 SLA**（deadline 是 `tickets` 的列）。规则粒度可以是"部门+优先级"，但**实例粒度只有工单级**；每系统 SLA **未发现**。
8. **是否由统一 SLA service 管理**：**否**。计算在 API 层（`tickets.py::_calculate_sla_deadline`），扫描在 `services/sla_scanner.py`，超时判定在**三处重复**（update_ticket / articles reply / scanner），breach 标志回写没有事件日志。
9. **改 SLA 规则是否需要改代码**：
   - 改**时长**（部门/优先级 → 分钟数）：不改代码（admin API + 前端页面）；
   - 改**倍率**（投诉分级）：不改代码（`complaint_escalation_policies` 表）；
   - 改**语义**（on_hold 暂停、按系统计时、首响 SLA、起点改为"判定后"）：**必须改代码**（三处 TODO 就是证据）。

---

## 十、Flow Log / History 审计

### 10.1 存在的记录设施
| 设施 | 状态 | 位置 |
|---|---|---|
| `ticket_state_logs` | **启用，核心流转日志** | `models/ticket.py:170-191 class TicketStateLog` |
| `articles`（reply/addition/reminder） | 启用，沟通记录，`state_key` 指向 state_log id | `models/ticket.py:127-148`；`state_key` 由 `articles.py:246-281` 写入 |
| `audit_logs` | **表存在但全仓无 `AuditLog(` 实例化 → 未使用** | `models/audit.py:12`；grep 仅命中定义行 |
| `operation_logs` / `history` / `timeline` 表 | **未发现**（`StateLogTimeline.vue` / `ArticleTimeline.vue` 是前端组件名，不是表） | — |
| `reminders` / `dingtalk_notifications` | 启动通知留痕 | `models/ticket.py:194`、`models/notification.py` |

### 10.2 `TicketStateLog` 字段对照
- `from_state` ✅、`to_state` ✅、`operator_id` ✅、`created_at` ✅、`reason` ✅（兼作 comment）、`duration_minutes` ✅（上一状态停留时长）、人员快照 `creator_id_snapshot / dispatcher_id_snapshot / owner_id_snapshot` ✅（迁移 `d1e2f3a4b5c6`）。
- **缺失**：`action_type`（分派/打回/暂缓/归档/重开 无法直接区分，只能靠 from→to+reason 推断）、独立 `comment`、字段级变更记录、IP/来源。

### 10.3 关键操作覆盖核查
| 操作 | 是否入日志 | 证据 |
|---|---|---|
| 审批 | **能力未发现** | — |
| 责任系统判定 | **能力未发现** | — |
| 响应措施提交 | ✅ 部分：reply 时写 `to_state=resolved` 日志 + Article 挂 `state_key` | `articles.py:246-281` |
| 售前确认 | **能力未发现** | — |
| 分派（pending→open） | ✅ 日志 | `tickets.py:1147` |
| 退回 | ✅ 日志含 `reason`（`requires_reason` 强制）+ `has_returned` 标记 | `state_machine.py:43-49`、`tickets.py:1132` |
| 重新处理（resolved→open） | ✅ 日志 | 同 PATCH 路径 |
| 关闭（archived/cancelled） | ✅ 日志 + `closed_at/closed_duration_minutes`；操作人可从日志反查（`_get_terminal_operators:234-270`，注释明确"state_log 才是真实来源"） | `tickets.py:1114-1118,234` |
| 回访/满意度填写 | ⚠️ **不单独记日志**——与 archived 一起提交，前端 `submitArchive` 未传 `reason`（`TicketDetailView:384-390`） | — |
| SLA 超时标记 | ⚠️ **不记日志**（UPDATE 直接置位，`sla_scanner.py:38-49`） | — |
| 字段变更（priority/owner/部门/分类） | ❌ **不记日志**（`update_ticket` 仅在 state 变化时写 log，`tickets.py:1069`） | — |
| 催办 | ✅ Article(reminder) + `urged_at/urged_by_id` | `articles.py:297-302` |

**能否从日志还原完整流程**：**状态链可以**（E2E 直接断言 `transition_chain`，如 `test_business_support.py:112-115`），**业务动作粒度不行**——无 action_type、无字段级审计、回访与 SLA 事件缺席。要完整还原"谁在什么时候因为什么把工单从 A 改成 B 并顺手改了哪些字段"，当前日志不够。

---

## 十一、前端耦合审计

### 11.1 业务流程逻辑被放在前端的清单（应由后端决定）
| # | 业务规则 | 前端位置 | 后端对应 | 风险 |
|---|---|---|---|---|
| 1 | **退回目标状态决策**（含"resolved 退回时跳过 on_hold 找上一状态"） | `TicketDetailView.vue:499-519 resolveReturnTarget` | `tickets.py:69-87 _enforce_business_constraints`（**只兜底 resolved→on_hold→open，不实现完整规则**） | **高**：绕过前端直接调 API 可得到不同退回目标 |
| 2 | **操作权限矩阵**（谁可退回/撤销/指派/归档/重提） | `TicketDetailView.vue:231-281` 5 个 computed（canDispatch/canReturn/canCancel/canArchiveFromResolved/canResubmit） | `tickets.py:273-344 check_transition_permission` | **高**：两份矩阵手工同步（如"resolved 退回=创建者或 agent"两边各写一遍） |
| 3 | **允许操作的状态集合**（处理说明/补充/催办/暂缓） | `ReplyEditor.vue:185-187`（`allowedAdditionStates/replyAllowedStates/reminderAllowedStates`）、`canHold:222`、`TicketDetailView:221 TERMINAL_STATES` | `articles.py:25-33 ADDITION_ALLOWED_STATES 等`、`state_machine.py:52` | 中 |
| 4 | **"当前状态只能一条处理说明"判断** | `ReplyEditor.vue:198-207 hasSummary`（用 state_log id 反推） | `articles.py:257-270` | 中（前后端都在算 state_key） |
| 5 | **"是否回退"的语义判定**（状态顺序权重表） | `api/tickets.ts:47-64 isReturnTransition`（returned=0…archived=4） | 后端无对应概念，`RETURN_TRANSITIONS` 只认 2 个转换 | 中 |
| 6 | **状态/优先级枚举与标签** | `api/tickets.ts:17-44 STATE_MAP/PRIORITY_MAP/STATE_ID_TO_KEY` | `tickets.py:35 STATE_LABELS`、`:581 state_labels`、`:586 priority_labels` | 中（新增状态要改 ≥5 处） |
| 7 | **归档时的业务字段打包**（callback_required/is_callbacked/satisfaction 与 state 同一 PATCH） | `TicketDetailView.vue:379-400 submitArchive` | `tickets.py:1154-1174`（有满意度校验，✅ 后端兜底） | 低-中 |
| 8 | **SLA 展示时长推算** | `TicketInfoSidebar.vue:188-192`（由 `created_at→deadline` 反推总时长）、`SLAIndicator.vue:24` 兜底 `240` 分钟 | 后端不下发 policy 时长 | 中（前端改规则会显示错） |
| 9 | **优先级默认值按中文名匹配** | `TicketCreateView.vue:253,322`（`name === 'P4 一般事件'`） | 无 | 低（改名即失效） |

### 11.2 属于 UI、可以留在前端的
颜色/图标（`PriorityIcon.vue`、`StateTag.vue` 的 state_type 分组 `new/open/pending/closed`）、时间格式化、头像、布局。`StateTag` 本身只是渲染器（无业务判断）。

### 11.3 搜索项核对
- **责任系统名称写死**：**未发现**（部门列表走 `metaApi.getSkillGroups()` → `GET /skill-groups`）。
- **5 个系统循环写死**：**未发现**（不存在该流程）。
- **状态码写死**：**存在**（见表 #5/#6）。
- **P0/P1 SLA 时间写死**：**未发现 SLA 分钟数写死**（只有兜底 240/默认 480 展示值）；优先级枚举 `p1_urgent…p4_enterprise` 写死在 `PRIORITY_MAP`。
- **"是/否"对应后续流程写在前端**：**未发现**（无该流程）。
- **不同角色大量 if/else 控制业务流程**：**存在**——`authStore.isAdmin/isAgent` 出现在 `TicketDetailView` 5 处 computed 与 `ReplyEditor` 2 处 computed 中，与后端 `user.role` 判断重复。

**总结**：业务流程决策（退回目标 + 权限 + 允许状态）当前是"**前端主导、后端校验**"的格局，而后端校验并不完整（batch-update 无权限校验、退回目标只兜底一种情况）。

---

## 十二、测试覆盖审计（看测试逻辑，不看文件名）

### 12.1 E2E（`e2e_tests/tests/`，全部走真实 API）
| 目标能力 | 覆盖 | 证据（实际断言） |
|---|---|---|
| 售前审批 | ❌ **未覆盖（功能不存在）** | 全目录无 approval/presale |
| 五责任系统并行判定 | ❌ **未覆盖（功能不存在）** | — |
| 第一系统认领 | ❌ **未覆盖** | — |
| 后续系统继续判定 | ❌ **未覆盖** | — |
| 多系统共同认领 | ❌ **未覆盖** | — |
| 全部系统判否退回 | ❌ **未覆盖** | — |
| 响应措施分别提交 | ❌ **未覆盖** | — |
| SLA 启动 | ⚠️ **E2E 无 deadline 断言**（grep `deadline|sla_` 在 e2e/tests 0 命中）；**单测有**：`backend/tests/test_complaint_routing.py:80,104` 断言创建时 `solution_deadline` 按倍率缩短 | |
| 售前确认 | ❌ **未覆盖（功能不存在）** | — |
| 回退 / 重新处理 | ❌ **E2E 未覆盖**（grep `returned/on_hold/退回` 在 e2e/tests 0 命中）；后端单测也**没有**退回/暂缓/reopen 用例（`backend/tests` 12 个文件的 test 列表里无 return/hold/reopen） | |
| 工单关闭 | ✅ **覆盖** | `test_business_support.py:101-102`（archived + `closed_at` 非空）、`:112-115` 断言完整 `transition_chain`（None→pending→open→resolved→archived） |
| 路由（分类→部门/人） | ✅ **覆盖广** | `test_consultation_routing.py`（1202/1203）、`test_business_support.py`（2311/2312/2313/2321 父链上溯）、`test_routing_inheritance.py`（L4 直配、L3 上溯到 L2） |
| 即时办结直落终态 | ✅ | `test_instant_consultation.py:37-44`（archived + `None→archived` 日志） |
| 投诉分级 × SLA 倍率 | ✅ | `test_complaint.py:99-112` + `:180-205`（0.75/0.5 策略播种校验） |

E2E 场景清单：01 即时办结 / 02-03 咨询路由 / 04-05 业务运营 / 06-09 业务保障 / 10-13 投诉分级 / 14 父链上溯（见 `e2e_tests/docs/local_ticket_test_workflow.md:39-44`）。

### 12.2 后端单测（`backend/tests/`）
- 覆盖较好：路由规则（11 例，含规则校验/停用/停用人告警/不回溯历史 `test_routing_rules.py:105-266`）、建单自动匹配（5 例）、投诉 SLA（6 例）、即时办结（6 例，含终态不可流转 `test_instant_resolve.py:141`）、专业部门字段（5 例）、结构化字段（4 例）、分类树（9 例）、Phase 9 种子（4 例）。
- **空白**：
  - `services/state_machine.py` 本身（`validate_transition` / `requires_reason` / 终态）**无直接单测**；
  - `update_ticket` 的状态副作用链（first_owner/closed_at/has_returned/`_enforce_business_constraints`）**无单测**；
  - `batch-update` **无测试**（其权限/副作用缺口因此无人发现）；
  - 权限矩阵 `check_transition_permission` **无系统性测试**（只有 e2e 用 admin 跑通 happy path）；
  - SLA 扫描器 `sla_scanner` **无测试**。

---

## 十三、架构矩阵

| 能力 | 当前实现 | 成熟度 | 是否写死 | 后续变更风险 | 关键代码 |
|---|---|---|---|---|---|
| **Ticket** | `tickets` 表单表承载全生命周期：状态、SLA 计时、归属、退回目标、回访、催办、归档、投诉分级、根因/方案共 60+ 列（约 30 个阶段型可空列）；单 owner | **已具备**（作为工单主体完整可用） | 部分写死：state/priority 为裸字符串，取值集合在后端 ≥3 份、前端 ≥4 份 | **中**：每加一个流程阶段都倾向"加列"，schema 面积持续膨胀 | `backend/app/models/ticket.py:11`；`schemas/ticket.py:8,43` |
| **State Machine** | 单一 `TRANSITIONS` 表 + `validate_transition/requires_reason/TERMINAL_STATES` + `check_transition_permission` 权限矩阵；支持退回/重开/终态；状态写入却分散在 4 条路径，`batch-update` 无权限与副作用 | **部分具备** | 写死：状态集合、标签、退回目标（前后端各一份）、"resolved→on_hold→open" 特例 | **高**：改一次流转要同步 8 个文件；batch-update 是越权/数据不一致口子 | `services/state_machine.py:23,55`；`api/v1/tickets.py:1069,1242,273,69`；`api/v1/articles.py:230`；`frontend/views/TicketDetailView.vue:499` |
| **Task** | **未发现**任何 task/todo/assignment/work_item 实体；Article/Reminder 是沟通记录，缺 assignee/status/completed_at/result；一单一 owner 无并行位点 | **基本缺失** | —（缺失即最大写死：流程结构=Ticket 字段结构） | **按需求触发**：当前单责任人串行主流程不阻塞；一旦出现并行待办/会签/多人各自提交，即变为高（届时只能给 tickets 加列或新建实体） | `models/__init__.py:1-22`（无 Task）；`models/ticket.py:41,44,127`；交付说明 §0"不引入多 owner" |
| **Routing Rule** | 独立表 `category_routing_rules`（UNIQUE category + enabled + note）+ `resolve_rule` 父链上溯 + 建单自动填 + 管理端 CRUD；但只解决"归谁"，不含"怎么流转" | **部分具备** | 否（业务代码无分类 id 写死）；种子/迁移/测试写死 category id 与人名 | **低-中**：加分类/改归属=改数据；新增"处理路径"仍需改 8 处代码 | `models/routing.py:27`；`services/routing.py:183`；`api/v1/tickets.py:830`；`api/v1/common.py:1265-1375`；`scripts/seed.py:386-401,460-467` |
| **Responsible System / Department** | 无"责任系统"实体；`SkillGroup`（部门）+ `UserSkillGroup.is_dispatcher`（对接人标记）+ `CategoryRoutingRule`（部门/人 × 分类）+ 单值 `handler_skill_group_id/owner_id` | **部分具备**（单责任人路由可用，多责任方无模型） | 业务代码未写死系统名/人 id；**种子写死 id 组（100-106/200-214）与人名**（Phase 9 补丁已示范按 name 查 id，可推广） | **中高**：加第 6 个"部门"=改数据即可；改成"多责任方并行"=必须新建实体并改前后端 | `models/group.py:23,35`；`models/routing.py:43-62`；`scripts/seed.py:339-401,450-467` |
| **SLA** | 规则表 `sla_policies`（部门×优先级→分钟，admin CRUD）+ 投诉倍率表；实例=工单列 `solution_deadline/solved_at/sla_solution_breached`；60s 扫描兜底 | **部分具备** | 规则数据化（001_init SQL 播种 P1-P4=120/240/480/60 分钟）；**语义写死**：起点=建单、on_hold 不停表、无首响、无 per-system；前端兜底 240/480 分钟 | **高**：SLA 策略未定（3 处 TODO），超时判定逻辑重复 3 处，改 pause/粒度要动 API+扫描+前端 | `models/sla.py:11`；`api/v1/tickets.py:168-204,1104-1108,1175`；`services/sla_scanner.py:25-56`；`migrations/001_init_schema.sql:409`；`views/admin/SLAView.vue` |
| **Flow Log** | `ticket_state_logs`（from/to/operator/reason/duration/人员快照）+ `articles`（state_key 挂靠）+ 终态操作人反查；`audit_logs` 表空壳未启用 | **部分具备** | 缺 action_type；日志写入点靠 4 条路径各自 `db.add`（无统一埋点） | **中高**：非状态字段变更、回访、SLA 事件不入日志，流程还原不完整；一旦加动作类型需回填 | `models/ticket.py:170`；`api/v1/tickets.py:51,1147,1248,234`；`api/v1/articles.py:246`；`models/audit.py:12`（未用） |

---

## 十四、最小改造建议（保留现状，小幅改动）

### 14.1 当前最值得保留的架构（不要动）
1. **单一流转规则表 `TRANSITIONS` + `validate_transition` + `StateTransitionError`**（`services/state_machine.py`）——已经是最接近目标骨架的抽象，方向正确，问题只是"执行侧没收口"。
2. **`category_routing_rules` + `resolve_rule` 父链上溯 + enabled 开关**——配置化最成功的一块：加分类/改归属零代码，且有"改规则不回溯历史工单"的测试保护（`test_routing_rules.py:235`）。
3. **`ticket_state_logs` 带人员快照与停留时长**，并已确立"日志才是终态操作人的真来源"（`tickets.py:234-270` 注释）——这是 Flow Log 的正确地基。
4. **幂等种子 + alembic 权威迁移 + E2E 按业务属性查 id**（`helpers.py` 设计原则）——数据层演进方式健康。

### 14.2 必须解耦的 4 个点（结合代码事实）
1. **状态写入口收口**：新建唯一入口（如 `services/state_machine.py` 内 `apply_transition(db, ticket, to_state, operator, reason, body)`），把 `update_ticket`（`tickets.py:1069-1153`）、`batch_update_tickets`（:1242-1258）、`articles` reply（`articles.py:230-276`）、建单终态（:876-932）四条路径都改为调它；**顺带修掉 batch-update 的权限/reason/副作用三个缺口**。
2. **退回目标决策从前端移到后端**：把 `TicketDetailView.resolveReturnTarget`（:499-519，含"跳过 on_hold"）移植成 `state_machine.return_target(ticket, logs)`，由详情接口返回 `allowed_actions:[{action,target_state,need_reason}]`；前端 5 个 canXxx 改为读该列表。后端 `_enforce_business_constraints` 升级为唯一裁决而非兜底。
3. **Flow Log 补"业务动作"表达**：`ticket_state_logs` 增加 `action_type`（dispatch / return / resolve / archive / callback …），并把回访、SLA 超时、字段级变更纳入记录——先统一"动作"概念，日志才能在流程变化后保持可还原（§10.2 现状：只能靠 from→to+reason 反推）。
4. **枚举/标签单源下发**：后端提供 `GET /meta/states`（key/label/order/terminal/需 reason）与 `GET /meta/priorities`，删掉前端 `STATE_MAP`、`stateLogStrToObj`、`STATE_ID_TO_KEY`、`isReturnTransition` 权重表（`api/tickets.ts:17-64`）与后端导出里的重复 `state_labels`（`tickets.py:581`）。
5. **Ticket 与阶段数据解耦 → 最小 Task 表（触发条件式，非当前必做）**：`ticket_tasks(id, ticket_id, type, responsible_skill_group_id, assignee_id, status, result, payload JSONB, created_at, completed_at)`。**当前客服主流程是单责任人串行**，短期只调分类/部门/状态/回访/归档并不需要它；**触发条件**见 §14.4。

### 14.3 应该配置化的东西（现在就该数据化/集中化）
- ✅ 已配置化：SLA 时长（`sla_policies`）、投诉倍率、分类→路由、分类树、部门与对接人。
- 🔧 待配置化/集中：状态集合与"需 reason 的转换对"（现为代码常量两处：`TRANSITIONS` + `STATES_REQUIRE_REASON_FROM`，可留代码但必须只留一份）、归档必填规则（回访单选+满意度必填目前在前端表单硬编码 `TicketDetailView:104-125`）、种子中的部门/人/规则（推广 `V2_MISSING_LEAF_RULES` 的按 name 查 id，替换 `V2_SKILL_GROUPS/V2_USERS/V2_ROUTING_RULES` 的写死 id）、优先级与状态中文标签、SLA 暂停策略（等策略定稿后落表）。

### 14.4 暂时不要抽象的东西
- **不要做通用工作流引擎 / 规则 DSL**：当前状态只有 7 个、转换 14 条，`TRANSITIONS` 字典足够；引擎化收益远小于迁移成本。
- **不要重构 `CategoryRoutingRule` 为通用 dispatch engine**：它只做"归组"，语义稳定；先让它继续只做归组。
- **不要先做 per-system SLA 实例**：SLA 策略本身未定（`tickets.py:1102`、`sla_scanner.py:32` 两处 TODO），先等策略，避免白做。
- **不要急着启用 `AuditLog` 通用审计**：先把 `ticket_state_logs` 补上 action_type 即可，双日志体系会互相稀释。
- **不要在本次合并/清理双迁移体系**：只需明确"alembic 是唯一权威，`backend/migrations/*.sql` 仅作历史参考"（因为 SLA 默认数据只在 001 里，贸然删除会丢播种源）。
- **不要在 main 上直接改造来对齐 `poc/workflow-changes`**：那是另一套状态机与优先级体系（`p0..p3`），先做分支级决策再动代码。
- **不要现在就引入通用 Task 层**：当前客服主流程是单责任人串行，短期流程图只调分类/责任部门/状态/回访/归档都不需要它。**引入触发条件**：出现 ①独立待办 ②多责任方并行 ③会签 ④多人各自提交结果 之一（见 §14.5 第 4 条）。

### 14.5 改造优先级（校正后）
1. **状态流转执行收口**（最确定、收益最高）——规则定义本身已集中，但真正改 `state` 与副作用散在 PATCH（`tickets.py:1069-1153`）、batch-update（:1242-1258）、reply（`articles.py:230-276`）、建单终态（:876-932）多条路径，**已经出现行为不一致**（batch-update 无权限/无 reason/无 solved_at、closed_at）。收口为唯一 `apply_transition` 并补缺口。
2. **后端统一输出 `allowed_actions` / 状态元数据，前端只负责渲染**——把 `canReturn`、`canArchive`、退回目标（`resolveReturnTarget`）、允许状态集合（`ReplyEditor` 三组）从前端逐步拿掉，消灭"一条业务规则维护两份"（§11 表 #1-#6）。
3. **增强 Flow Log 的业务动作表达**——状态链能还原，但 `action_type`、字段级变更、回访/SLA 事件不完整；先补统一动作概念（dispatch / return / resolve / archive / callback），以后流程变化时日志才真正稳定。
4. **`ticket_tasks`（第四优先级，按需求触发，不立即做）**——只有当流程出现**独立待办、多责任方并行、会签、多人各自提交结果**时才引入；当前单责任人串行主流程不必先建通用 Task，避免把客服工单过早做成通用工作流引擎。

> 一句总结：**当前客服工单已经具备稳定的"分类归属、组织配置、SLA 参数、状态规则定义和状态日志"基础；真正易碎的是"状态执行、权限判断、前后端重复规则和流程副作用"。先把这些收口，只有当流程出现并行待办/多人协同时，再补 Task 层。**

---

## 附：审计方法与边界
- 全部结论基于当前工作区文件内容（`read`/`grep`/`git log`），未根据文件名推断实现，未修改代码、未建 commit。
- 明确"未发现"的能力：Task/待办表、Decision/判定记录、响应措施独立实体、售前审批、五责任系统并行判定与计数、是/否判定流、售前确认、每系统 SLA、pause/resume、action_type 级日志、`AuditLog` 写入点、前端责任系统硬编码。
- 需求口径参考（非代码）：`责任部门与处理时效整理.md`、`责任部门与客户问题处理流程改造交付说明.md`、`docs/01_requirements.md`。
- 仓库分支事实：`main`（本报告对象）与 `poc/workflow-changes`（含 `app/domain/poc_workflow.py` 六角色十状态契约）为两套并行实现，未合流。
