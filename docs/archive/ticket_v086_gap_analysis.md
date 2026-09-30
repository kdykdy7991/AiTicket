# V0.86 目标骨架 × 现有代码 Gap Analysis

> 对照口径：以人工提炼的《客户问题处理流程 V0.85》目标骨架为标尺（7 项核心能力 + SLA/Flow Log 横切 + 修改成本表），逐项对照 `docs/ticket_architecture_audit.md` 的代码事实。
> 不混 POC 分支，不迁就现状打分。判定只用三档：**满足 / 部分满足 / 不满足**。

---

## 一、逐能力对照

### 1. Ticket 工单主体 —— 部分满足

| 目标 | 现状 | 判定 |
|---|---|---|
| 只存稳定信息（客户/联系方式/描述/渠道/设备/分类/优先级/状态/归属/创建时间） | `models/ticket.py:14-47` 全部具备 | ✅ |
| 流程阶段数据不长在主体上 | **约 30 个阶段型可空列躺在 tickets**：SLA 4 组、`hold_until`、`closed_at/closed_duration_minutes`、`resolved/resolution/root_cause/solution`、`complaint_level`、`callback_required/callback_details/archive_notes/is_callbacked/satisfaction`、`urged_at/urged_by_id`、`has_addition/has_returned`、`returned_to_user_id` | ❌ |
| "流程图多一个框 ≠ tickets 加三列" | 历史演进正是加列模式：Phase 4 `handler_skill_group_id`（迁移 `g1a2b3d4e5f6`）、Phase 7 `root_cause/solution`（`h1b2c3d4e5f6`）、`has_returned`（`7c8d9e1f2a3b`）、`satisfaction`（`e2f3a4b5c6d7`） | ❌ 趋势已成惯性 |

**V0.86 影响**：新增阶段字段的默认路径仍是"加列 + 迁移 + schema + 序列化 + 前端"。
**最小动作**：不搬迁存量；立一条 Schema 政策（见 §3.5）——新增阶段数据落 Processing Result，不进 tickets。

---

### 2. Category —— 满足（留一个明确缺口）

| 目标 | 现状 | 判定 |
|---|---|---|
| 分类树、启用/排序、增删改全是配置 | `ticket_categories`（`category.py:11-23`：`parent_id/level/sort_order/is_active`）+ 管理端 CRUD（`common.py:411 create_category / :543 update_category / :630 delete_category`，含深树 level 重算 `_recompute_descendant_levels:600`） | ✅ |
| 新增"设备激活/网络覆盖/账单"= 加数据 | 分类行由 alembic 幂等播种 + `POST /categories` 即建 | ✅ |
| **某类问题是否需要特定字段** | **未发现**：无 per-category 字段要求机制，建单表单对所有分类同一套字段 | ❌（缺口，按"Schema + UI 小改"处理，不必配置化） |

**附带风险（非功能缺口）**：分类 id 与人名写死在种子/迁移/测试（`seed.py:327-335,412-431`、alembic `f2a3b4c5d6e7`、`tests/test_phase9_base_data.py:282-284`）；Phase 9 补丁已示范按 name 查 id（`seed.py:460-467`），应推广。

---

### 3. Routing / Assignment —— 满足（含"归谁 ≠ 怎么走"的正确分离）

| 目标 | 现状 | 判定 |
|---|---|---|
| 问题属性 → 路由规则 → 部门/对接人/负责人 | `category_routing_rules`（`routing.py:27`：`dispatcher_skill_group_id / dispatcher_id / handler_skill_group_id / owner_id / enabled / note`，`category_id` UNIQUE）+ `resolve_rule` 父链上溯（`services/routing.py:183`）+ 建单自动填（`tickets.py:830-850`）+ 管理端 CRUD（`common.py:1265-1375`） | ✅ |
| 某分类换部门 / 某部门换负责人 = 改配置 | `PATCH /routing-rules/{id}`；负责人 = `users` + `user_skill_groups` 数据 | ✅（代码零改动） |
| Routing 与 State Machine 严格分开 | 代码上确实是两个模块、互不引用：`services/routing.py`（归谁）vs `services/state_machine.py`（怎么走） | ✅ |
| 规则变更不污染历史工单 | `test_routing_rules.py:235 test_updating_rule_does_not_retroactively_change_tickets` | ✅（语义已定义清楚） |

**小注**：规则只在建单时快照到 ticket 字段——这与图上"分派"框一致（owner 不自动落，留给分派步骤，`tickets.py:845-846` 注释），不是缺陷。

---

### 4. State / Flow —— 规则定义满足，执行与表达不满足

**状态映射**（图 → 代码）：

| 图上阶段 | 现状承载 | 评价 |
|---|---|---|
| 受理 | `pending` | ✅ |
| 问题判断 | **无独立状态**，隐含在 `pending→open` 分派里 | ⚠️ 可接受（判断=分派的输入） |
| 工单分派 | `pending→open` + `owner_id` | ✅ |
| 问题处理 | `open` / 暂缓 `on_hold` / 退回 `returned` / 重新处理 `resolved→open` | ✅ |
| 确认 / 回访 | **无独立状态**，混在 `archived` 动作入参里 | ❌ 见能力 6 |
| 工单归档 | `archived`（终态）/ `cancelled`（终态） | ✅ |

**对照你的五要素抽象**：

| 要素 | 现状 | 判定 |
|---|---|---|
| 当前状态 | `tickets.state` 单字段 | ✅ |
| 允许去哪些状态 | 单一 `TRANSITIONS`（`state_machine.py:23`）+ `validate_transition` | ✅ **改一处生效（后端）** |
| 谁能执行 | 后端 `check_transition_permission`（`tickets.py:273`）**+ 前端 5 个 canXxx**（`TicketDetailView.vue:231-281`） | ❌ 两份，改一处 ≠ 生效一处 |
| 需要什么输入 | 后端 `requires_reason` 按 (from,to) 对（`state_machine.py:43-69`）**+ 前端各弹窗各自强制必填**（退回/撤销/暂缓弹窗各写一遍） | ⚠️ 半 |
| 执行后的副作用 | 散在 4 条路径：PATCH（`tickets.py:1088-1132`）、batch-update（:1242-1258，**缺权限/reason/solved_at/closed_at**）、reply（`articles.py:230-276` 自带一份）、建单终态（:876-932） | ❌ 行为已不一致 |
| 退回目标 | 决策在前端 `resolveReturnTarget`（`TicketDetailView.vue:499-519`），后端 `_enforce_business_constraints` 只兜底一种特例（`tickets.py:69-87`） | ❌ 后端不是权威 |
| 动作（action）概念 | **无**。日志只能靠 from→to+reason 反推 | ❌ |

**V0.86 影响**：新增"待确认"这类状态 = 8 个文件量级（见 §2 第 11 行）；新增/修改流转规则后端一处对了，前端按钮、权限、报表仍要人肉同步。

---

### 5. Processing Result —— 部分满足

| 目标 | 现状 | 判定 |
|---|---|---|
| 处理结果结构化、与状态分层 | 有 `root_cause / solution / resolution`（`ticket.py:73-76`）+ `Article(type=reply)` 挂 `state_key` 到状态节点（`articles.py:246-281`） | ⚠️ 有内容，但**载体混层** |
| 结果 ≠ 状态载体 | 结果字段直接在 `tickets` 主体上，与"状态"共用一张表 | ❌ |
| 新增"处理附件 / 寄修单号 / 检测报告"落结果层 | **reply 不收附件**（附件仅 `type=addition` 可传，`articles.py:288-291`）；无结果表 / 无 payload 落点 → 默认只能继续加 tickets 列 | ❌ |

**最小动作**：给结果一个落点（`ticket_results` 表或 `tickets.payload JSONB`，二选一即可）+ reply 放开附件；**不需要**因此引入 Task（结果不需要 assignee）。

---

### 6. Closure / Callback —— 不满足（图上最重要的两个判断没保住）

| 你的闭环模型 | 现状代码 | 判定 |
|---|---|---|
| 处理结果提交 → **是否解决？**（独立事实） | **"处理完成"与"问题解决"共用同一事实**：reply 提交即 `state=resolved + solved_at + resolved=True`（`articles.py:272-276`），没有独立的"是否解决"记录 | ❌ 两个事实不能单独保存 |
| 是 → 回访 → **是否满意？**（独立事实） | 满意度 `satisfaction` 独立字段 ✅，但**没有回访阶段**：`is_callbacked / callback_required / satisfaction` 全部是 `archived` 动作的入参（`TicketDetailView.vue:379-390 submitArchive`） | ❌ 回访不是一个阶段 |
| 不满意 → **收集原因** → 重新处理 | **`callback_details` 是死字段**：模型有列（`ticket.py:87`）、schema 有字段（`schemas/ticket.py:53`）、详情会返回（`tickets.py:162`），但 **`update_ticket` 从不应用 `body.callback_details`**（PATCH 处理段 `tickets.py:1154-1198` 无此项），**前端也从不发送**（`frontend/src` 仅类型声明一处）。E2E 发送了该字段但从不断言回读（`test_business_support.py:96`），所以一直没被发现 → **"不满意原因"根本写不进去** | ❌ 断链 |
| 不满意 → 必须重新处理 | `satisfaction=dissatisfied` **可以直接归档**：前端仅必填校验（`TicketDetailView.vue:120`），后端无任何阻断规则 | ❌ 闭环不强制 |
| （投诉等级的角色门槛） | `complaint_escalation_policies.required_role` 有列、有播种（`complaint.py:28`、`test_complaint_routing.py:54-62`），但 **`backend/app` 内 0 处使用** → "重要投诉需 manager"是**假配置** | ❌ |

**结论**：这是 7 项能力里与目标骨架差距最大、且是"客服工单区别于普通 issue tracker"的那一层。好消息是修复都在"Schema + UI 小改 / 改一处动作规则"量级，不需要动结构。

---

### 7. Archive / Review —— 满足（复盘正确地没长在工单上）

| 目标 | 现状 | 判定 |
|---|---|---|
| 工单归档后主状态机结束 | `archived/cancelled` 为 `TERMINAL_STATES`（`state_machine.py:52`），终态不可流转（`test_instant_resolve.py:141`） | ✅ |
| 复盘**不**在 Ticket 上加 `reviewed / knowledge_updated / product_feedback_sent` | **正确地没有长出这些字段**；复盘=统计接口消费历史数据：`/stats/dashboard`（`common.py:768`）、`/stats/report`（:862）、`/stats/trend`（:1154） | ✅ |
| 聚合分析可用 | 大部分可用；两个接线尾巴：`avg_resolution_per_group` 前端置空（`overviews.ts:36` "后端暂未提供"）、导出"回访时间"列恒空（`tickets.py:627` 注释"暂无独立回访时间字段"） | ⚠️ 小尾巴 |

---

### 横切：SLA —— 参数满足，语义不满足

- ✅ 规则配置化：`sla_policies`（部门×优先级→分钟）+ `complaint_escalation_policies.sla_resolution_multiplier`，admin CRUD（`common.py:687-756`）+ 前端 `admin/SLAView.vue`。"8h 改 6h = 改配置"成立。
- ❌ 语义写死：起点=建单（`tickets.py:204`）、`on_hold` 不停表（`tickets.py:1102`、`sla_scanner.py:32` 两处 TODO）、无回访阶段计时概念、首响 SLA 死字段（`common.py:722` 注释"已废弃"）。
- ❌ 超时判定重复 3 处（update_ticket / reply / scanner），breach 标记不入日志。

### 横切：Flow Log —— 状态链满足，动作表达不满足

- ✅ `ticket_state_logs` 覆盖全部状态变更，带 from/to/operator/reason/duration/人员快照（`ticket.py:170-191`），4 条路径都会写。
- ❌ 无 `action_type`（分派/打回/归档/回访无法直接区分）、非状态字段变更不记日志、回访与 SLA 事件不入日志、`AuditLog` 空壳未用（`audit.py:12`）。
- ⚠️ 状态中文标签硬编码 6-7 份（后端 `tickets.py:35,581`；前端 `api/tickets.ts:17,114,128` + `STATE_ID_TO_KEY` + `isReturnTransition` 权重表）——"状态展示名称"目标是配置化，现状不是。

---

## 二、修改成本表逐行打分（这把尺子的实测结果）

| V0.86 的变化 | 理想成本 | 现状实际成本 | 结论 |
|---|---|---|---|
| 新增一个问题分类 | 配置 | `POST /categories` + 需要时 `POST /routing-rules` | ✅ 满足 |
| 分类改名 | 配置 | `PATCH /categories/{id}` | ✅ 满足 |
| 某分类换责任部门 | 配置 | `PATCH /routing-rules/{id}`（历史工单不回溯 by design） | ✅ 满足 |
| 某部门换负责人 | 配置 | `users` + `user_skill_groups` + 对应 routing rule，两处配置、零代码（种子需推广按 name 查 id，`seed.py:460-467` 已示范） | ✅ 满足 |
| SLA 从 8h 改 6h | 配置 | `PATCH /sla-policies/{id}` | ✅ 满足 |
| 新增投诉等级 | 优先配置 | 等级+倍率=配置生效 ✅；**`required_role` 是假配置**（0 使用）；分级标签前后端写死 | ⚠️ 部分 |
| 增加一个合法状态流转 | 改一处状态规则 | 后端 `TRANSITIONS` 一处 ✅，但还要：前端按钮/权限 computed、报表状态字面量（`common.py:807-1020`）、导出 labels（`tickets.py:581`）→ **3-4 处** | ❌ 超标 |
| 修改退回目标 | 改一处后端规则 | 前端 `resolveReturnTarget` + 后端特例兜底 = **2 处，且后端不是权威** | ❌ 超标 |
| 修改谁能执行某动作 | 改一处权限规则 | 后端 `check_transition_permission` 一处 ✅ + 前端 5 个 canXxx + ReplyEditor 允许集 → **约 6 处** | ❌ 超标 |
| 某动作新增必填原因 | 改一处动作规则 | 后端 `requires_reason` 一处 ✅ + 前端各弹窗各自写死必填 → **约 3 处**（且按 (from,to) 而非按 action） | ⚠️ 部分 |
| 新增"待确认"业务阶段 | 状态机小改 | 实测 **8 个文件**：`state_machine.py`、`tickets.py`（副作用+权限+导出 labels）、`articles.py`、`common.py` 报表、`schemas/ticket.py`、前端 `api/tickets.ts` + `TicketDetailView` + `ReplyEditor`、E2E | ❌ **最大超标** |
| 新增一个处理结果字段 | Schema + UI 小改 | tickets 加列 + 迁移 + schema + 序列化 + 前端（历史 4 次演进皆此路径）；**若先立落点政策则回到"小改"** | ⚠️ 部分 |
| 回访新增一个判断项 | 回访模型小改 | 后端 schema + `update_ticket` 应用 + 前端归档卡片——**当前连已有项都接不通**（`callback_details` 死字段） | ❌ 超标 |
| 多部门并行处理 | 结构变化，才考虑 Task | 现状确实做不到（单 `owner_id`，无 Task） | ✅ 与预期一致 |
| 多人分别提交结果 | 结构变化，考虑 Task | 同上（reply 仅 owner + 同节点唯一，`articles.py:177,257-270`） | ✅ 与预期一致 |
| 会签 | 结构变化，考虑 Task | 同上 | ✅ 与预期一致 |

**汇总：16 行里 5 行满足、3 行部分、5 行超标、3 行（并行类）本就需要结构变化。**
超标的 5 行全部指向同一个根因：**状态执行与业务规则没有单入口、且前后端各存一份**。

---

## 三、为了让 V0.86 好改，最少需要改什么

排序沿用已确认的优先级（状态收口 → allowed_actions → Flow Log），外加 Closure 两个小修与一条政策。

### 3.1 状态流转执行收口（解成本表第 7/8/9/10 行的执行侧）
- 唯一入口 `apply_transition(db, ticket, to_state, operator, reason, body)` 放进 `services/state_machine.py`；
- PATCH（`tickets.py:1069-1153`）、batch-update（:1242-1258）、reply（`articles.py:230-276`）、建单终态（:876-932）四条路径全部改为调用；
- **顺带修 batch-update 三缺口**：补 `check_transition_permission`、补 `requires_reason`、补 `solved_at/closed_at/first_owner_id` 副作用。

### 3.2 后端统一输出 `allowed_actions` + 状态元数据，前端只渲染（解第 7/8/9/10 行的展示侧）
- 详情接口返回 `allowed_actions:[{action, target_state, need_reason, fields_required}]`；
- 状态元数据（key/label/order/terminal/需 reason）由 `GET /meta/states` 下发；
- 前端删除：`canReturn/canCancel/canDispatch/canResubmit/canArchiveFromResolved`、`resolveReturnTarget`、`ReplyEditor` 三组允许集、`api/tickets.ts` 四份映射与 `isReturnTransition` 权重表；
- 后端删除导出重复 `state_labels`（`tickets.py:581`）。
- **退回目标决策进后端**：`state_machine.return_target(ticket, logs)`（含"跳过 on_hold"规则），`_enforce_business_constraints` 升级为唯一裁决。

### 3.3 Flow Log 补"业务动作"表达（让以后每次流程变化日志仍然可还原）
- `ticket_state_logs` 加 `action_type`（dispatch / assign / hold / return / resubmit / resolve / reopen / callback / archive / cancel）；
- 在 `apply_transition` 单点写入 → 顺带解决"4 条路径各自 `db.add`"的埋点分散；
- 回访事件、SLA breach 标记入日志；字段级变更**暂不做**（先动作级，避免过度工程）。

### 3.4 Closure 两个小修（成本表最后两个 ❌，都是小改量级）
1. **接通 `callback_details`**：`update_ticket` 应用 `body.callback_details`（`tickets.py:1154` 段补一行分支）+ 前端在 `callbackChoice==='call_backed' && satisfaction==='dissatisfied'` 时必填并发送 —— "不满意→收集原因"恢复。
2. **不满意不能直接闭环**：一条动作规则——归档（resolved→archived）时 `satisfaction=dissatisfied` 则拒绝并要求先 `resolved→open` 重新处理（写进 `apply_transition` 的动作前置校验，不是前端 if）。
3. *（可选，V0.86 真出现需求再做）* 把"是否解决"与"处理完成"拆开：回访独立状态或 `is_solved_confirmed` 字段——属"回访模型小改"，不阻塞前两条。

### 3.5 一条不是代码的改动：Schema 政策
> 新增阶段数据 → 落 Processing Result（`ticket_results` / `payload JSONB`），**不进 `tickets` 列**；
> 新增业务阶段 → 只允许改 `state_machine.py`（状态表 + 规则 + action），**前端靠 `allowed_actions` 自动适配**。

这条政策落地后，成本表里"新增处理结果字段""新增业务阶段"两行才真正回到理想成本。

---

## 四、明确不做（与目标骨架一致）

| 不做 | 理由 |
|---|---|
| 通用 Task 层 | 触发条件未出现（独立待办/多责任方并行/会签/多人各自提交）；当前单责任人串行主流程不需要（成本表后 3 行本就标注"结构变化才考虑"） |
| 工作流引擎 / 规则 DSL | 7 状态 14 条转换，`TRANSITIONS` 字典足够 |
| per-system SLA / SLA pause | SLA 策略未定（`tickets.py:1102`、`sla_scanner.py:32` 两处 TODO），等策略 |
| `AuditLog` 双写 | 先把 `action_type` 补进 state_log，双日志互相稀释 |
| 搬迁 tickets 存量阶段列 | 存量不拆，只拦增量（§3.5 政策） |
| 复盘状态（reviewed 等） | 目标骨架明确：复盘消费数据，不进主状态机——现状已正确，不要手痒加字段 |
| 对齐 `poc/workflow-changes` | 另一套状态机与优先级体系（p0..p3），先做分支决策 |

---

## 五、一页纸结论

- **已满足（放心改配置）**：Category 全部、Routing 全部（含归谁≠怎么走的分离）、SLA 参数、状态**规则定义**、归档终态与复盘解耦、状态日志管道。
- **部分满足（小改即回到理想成本）**：State 的输入/原因规则（需 reason 单源下发）、Processing Result（缺落点与 reply 附件）、Closure 的"是否解决/是否满意"两个事实（字段在、链路断）、投诉等级（`required_role` 假配置）、SLA 语义、Flow Log 动作表达。
- **不满足（成本表 5 个 ❌ 的共同根因）**：状态执行散 4 路径、权限/退回目标/允许集前后端双份、无 action 概念、回访不是独立阶段且不满意可直接归档。
- **最少改动**：§3.1 收口 + §3.2 单源下发 + §3.3 action_type + §3.4 两个 closure 小修 + §3.5 一条政策。
- **Task 依旧按需**：触发条件出现前不引入。
