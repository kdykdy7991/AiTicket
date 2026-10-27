# 客服工单全链路业务流程说明（新建工单 → 最终归档）

> 本文以文字方式完整描述工单从新建到归档的全链路，包含所有分支、条件判断与循环。
>
> **事实来源（与代码逐条核对）**：
> - 规则与执行唯一入口：`backend/app/services/state_machine.py`
> - 建单 / 更新 / 批量 / 状态日志：`backend/app/api/v1/tickets.py`
> - 沟通记录（处理说明 / 追加 / 催办）：`backend/app/api/v1/articles.py`
>
> 本文不引入任何代码之外的规则；凡与前端的约定均以后端返回的 `allowed_actions` 为准。

---

## 1. 全景总览

**主链路（一条工单的正常生命线）**：

```
新建工单(正式) → 待受理 pending → 分派 → 处理中 open → 提交处理说明 → 已处理 resolved
     → 回访判定（满意 / 未评价 / 无需回访）→ 已归档 archived（终态）
```

**旁路与异常分支（从主链路分出）**：

| 分支 | 流转 | 触发条件 |
|---|---|---|
| 即时办结 | 建单直接 `None → archived` | `is_instant_resolve=true`（咨询类，免分派免回访） |
| 草稿 | 不写状态日志，提交后才进入 pending | `is_draft=true` |
| 暂缓 | `open → on_hold` | 处理人发起，需原因 |
| 恢复 | `on_hold → open` | 处理人发起，需原因 |
| 打回（处理人→团队） | `open → pending` | 处理人退回，需原因，`has_returned=true` |
| 退回（受理侧→创建人） | `pending → returned` | 部门对接人退回，需原因，`has_returned=true` |
| 重新提交 | `returned → pending` | 创建者发起，不需原因 |
| 退回重开 | `resolved → open` | 创建者或客服发起，需原因，满意度清零 |
| 撤销 | `pending/open/on_hold/returned → cancelled` | 仅创建者，需原因（终态） |
| 不满意拦截 | `archived` 被 422 拒绝 | `satisfaction=dissatisfied`，必须先重开 |

**三个循环（详见 §9）**：不满意闭环循环、退回—重提循环、暂缓—恢复循环。

---

## 2. 状态定义（7 个状态）

| 状态 | 中文 | 含义 | 是否终态 | 主要责任方 |
|---|---|---|---|---|
| `pending` | 待受理 | 已建单、尚未分派，无处理人 | 否 | 部门对接人 |
| `open` | 处理中 | 已分派，处理人正在跟进 | 否 | 处理人（owner） |
| `on_hold` | 暂缓处理 | 暂停位，等待外部条件，处理人不变 | 否 | 处理人 |
| `resolved` | 已处理 | 处理说明已提交，等待回访与归档 | 否 | 客服团队 |
| `returned` | 退回 | 已退回给创建人，等待重新提交 | 否 | 创建者 |
| `archived` | 已归档 | 闭环结束 | **是** | — |
| `cancelled` | 已撤销 | 主动终止 | **是** | — |

终态（`archived` / `cancelled`）没有任何出边：任何流转到终态之外的请求都会被 `validate_transition` 拒绝（422），终态工单也不再接受任何沟通记录（422）。

---

## 3. 阶段一：新建工单（三个入口）

建单入口 `POST /tickets` 按以下**条件判断顺序**分三条路（`create_ticket`）：

### 3.1 判断 1：`is_draft = true` → 草稿

- 不生成 `number`、不计算 SLA 截止时间、不做重复工单检查、校验放宽。
- **不写初始 Flow Log**（草稿没有生命周期审计）。
- 可通过 `PATCH /tickets/drafts/{id}` 修改、`DELETE` 删除、`POST /tickets/drafts/{id}/submit` 提交。
- 提交时：`is_draft=False` → `apply_initial_state(None → pending)`，Action = `create`，此后与正式工单无异。

### 3.2 判断 2：`is_instant_resolve = true` → 即时办结咨询

- 仍然生成 `number`（YYYYMMDD-XXXX 日计数），但不生成 SLA 截止时间；保留完整审计。
- 构造期直接写入：`resolved=True`、`solved_at=now`、`resolution`（默认"即时办结咨询"）、`callback_required=False`（免回访）、`is_callbacked=True`。
- `closed_at` / `closed_duration_minutes` **不在构造期维护**，由 `apply_initial_state` 统一计算（终态副作用的唯一所有者）。
- 状态流转：`apply_initial_state(None → archived)`，reason = "即时办结咨询"，Action = `instant_resolve`。
- 结果：**一跳到终态**，免分派、免处理、免回访，之后不再有任何可执行动作。

### 3.3 判断 3：都不满足 → 正式建单

按顺序经过 6 个条件判断：

1. **路由规则自动匹配**（若给了 `category_id`）：`resolve_rule` 按分类路由规则补齐留空的对接部门 / 对接人字段（**body 显式值优先**）；不匹配只产生 warning，不拦截。注意：**处理人不在建单时分配**，留给"分派"步骤。
2. **生成工单号**：`YYYYMMDD-XXXX`，当日自增计数。
3. **计算解决时限**：按一级分类及其档位匹配策略，创建第一轮计时记录和 `solution_deadline`；线索工单不计 SLA。详见 [解决时限规则](sla-resolution-rules.md)。
4. **客服新建不判重**（2026-10-27 用户确认）：无论来电号码、分类是否与既有工单相同，都作为独立工单创建，不查询重复候选、不弹重复告警，也不因相同信息拦截。原 TC-WF-008 的重复告警预期作废，验收应为同号码、同分类可连续创建独立工单，原工单保持不变。
5. **部门对接人必填**：`dispatcher_id` 为空 → **422「建单时必须指定部门对接人」**（直指派分类例外，见 §3.5）。
6. **写初始状态**：`apply_initial_state(None → pending)`，Action = `create`，Flow Log 记录创建人/对接人快照。

> 建单后的工单固定为 `pending`：**无处理人（owner=None）**，等待分派。

### 3.5 直指派分类：建单即指定处理人（2026-10-26 定稿）

分类表布尔列 `ticket_categories.direct_assign` 打开时（语义：**自身或任一祖先为 True**，读时按父链上溯），该分类的工单**不走部门对接人分派**：

| 环节 | 直指派分类 | 其他分类 |
|---|---|---|
| 建单表单 | 必选**处理人**（从责任部门成员中选），对接部门/对接人只读带出 | 必选部门对接人，处理人留到分派时选 |
| 建单结果 | `pending` → 立即流转到 `open`，Flow Log = `create → direct_assign` | `pending`，Flow Log = `create`，等待分派 |
| 处理人打回 | 回到**建单人（客服）**：状态 `pending`、**处理人清空**，客服重新指派 | 回到部门对接人待分派 |
| 建单缺处理人 | 422「该分类由建单时直接指派处理人，请选择处理人」 | — |
| 处理人不在责任部门 | 422 | — |

- 状态机**无结构性改动**：`pending → open` 本就是既有边，只是 `action_type` 记为 `direct_assign`（区别于 `dispatch`）；权限矩阵新增一个与 `allow_sales_intake` 同族的场景豁免（建单人可直接推进）。
- 打回落点由 `return_checkpoints` 快照保证：`direct_assign` 分支在写快照前清空 `owner_id`，还原出来即"待受理、无处理人"。
- 规则是**分类级配置**，不是写死的分类 id；其他分类要采用同样通道只需把该列置 True。详见 [工单分派设计 §5.4](ticket_dispatch_design.md)。

### 3.4 问题分类口径（2026-09-29 定稿）

建单必选"一级分类 + 二级分类"，口径已按业务确认更新（开发库分类树同步完成，启用节点 21 个）：

```
一级（4）        二级（14）
├─ 咨询          ├─ 即时办结咨询（→ 走 3.2 即时办结，一跳归档）
│                ├─ 品牌合作 / 产品使用/参数咨询 / 渠道/代理合作
├─ 服务投诉       ├─ 一般投诉 / 重要投诉 / 重大投诉（与"投诉等级"字段暂保留重复）
├─ 业务运营       ├─ 套餐查询 / 套餐变更 / 业财对账
└─ 业务保障       ├─ 应用平台 / 星座大系统 / 终端软件 / 硬件故障
                  └─ 星座大系统 →（三级：核心网系统 / 测运控系统 / 卫星系统）
```

- 建单表单只有"一级 / 二级"两个下拉，与该口径**正好匹配**；旧 38 个分类节点与"客户服务 / 即时 / 非即时"容器节点已隐藏（`is_active=false`，保留待删除）。
- **分类 → 路由**：`resolve_rule` 按分类自动带出对接部门 / 对接人（父级规则对子孙生效）；逐项对应关系见 `docs/问题对应表.md`。
- **星座大系统的特殊流转**：建单只选到二级"星座大系统"→ 分派给**星座大系统负责人**（先用占位账号，角色设计阶段统一整理）→ 负责人判断三级（核心网 / 测运控 / 卫星）并**回填到工单**（作为对工单的补充）；回填后是否按三级二次转派待业务确认。
- 角色与权限见 `docs/角色表.md`。

---

## 4. 阶段二：受理分派（pending → open）

**唯一动作：分派（dispatch）**

| 条件 | 判定 | 结果 |
|---|---|---|
| 合法性 | `pending → open` 在 TRANSITIONS 中 | 否则 422 |
| 身份 | 操作人是该工单 `skill_group` 的**部门对接人**（`is_dispatcher`）或 admin | 否则 403「只有该部门的对接人可分派工单」 |
| 输入要求 | 非 admin **必须指定处理人 `owner_id`** | 否则 422「分派时必须指定处理人」 |
| 原因 | 不必填 | — |

**状态副作用**：

- `first_owner_id` = 被指派的首任处理人（无人可退时记操作人）——只在 `pending→open` 这一次设置，之后永不变。
- 显式 `owner_id` / `dispatcher_id` 在副作用之后应用（显式值优先）。
- `has_returned` 被重置为 false（该边不属于退回动作）。

分派后进入 `open`，工单有了处理人，责任从"受理侧"转移到"处理侧"。

> **特例**：分类为"业务保障 > 星座大系统"的工单应分派给**星座大系统负责人**（占位账号），由其判断三级问题并回填工单（见 3.4）。

> **例外**：直指派分类（§3.5）的工单不进这一阶段——它在建单时由客服直接指定处理人，随即走同一条 `pending → open` 边，Flow Log 记 `direct_assign`；此后处理人打回时回到**建单人**而非对接人。

---

## 5. 阶段三：处理期（open ⇄ on_hold）

### 5.1 状态内动作

- **暂缓** `open → on_hold`：**处理人**专属、**原因必填**（缺 reason → 400），可附带 `hold_until`（暂缓截止时间，ISO 格式）。处理人保持不变。
- **恢复** `on_hold → open`：**处理人**专属、**原因必填**。
- 暂缓期间继续计入解决时限，截止时间不顺延。

### 5.2 沟通记录（不改变状态的分支动作）

所有沟通记录通过 `POST /tickets/{id}/articles`，先过两道总闸：

- 工单处于**终态** → 422「工单已结束，无法提交处理说明、补充或催办」；
- `internal_note` 类型已下线 → 422。

然后按类型分三条判断链：

| 类型 | 条件判断（按顺序） | 副作用 |
|---|---|---|
| **处理说明 reply** | ① 必须是**当前处理人**（否则 403）② 状态 ∈ {open, on_hold}（否则 422） | **提交即流转**：`apply_transition → resolved`（Action=`resolve`）；同一 resolved 节点下只能有一条处理说明，重复 → **409** |
| **追加信息 addition** | ① 角色 ∈ {admin, agent}（否则 403）② 状态 ∈ {pending, open, on_hold, returned}（否则 422「仅在已处理之前的状态可补充」）③ **必须填补充原因**（否则 422） | `has_addition=True`，允许附截图 |
| **催办 reminder** | ① 角色 ∈ {admin, agent}（否则 403）② 状态 ∈ {pending, open, on_hold}（否则 422）③ **整单只能催办一次**：`urged_at is None`（否则 422「该工单已催办」）④ 内容非空且不超长（否则 422） | `urged_at` / `urged_by_id` 记录，触发通知扩展点 |

> 这三类动作**不改 `ticket.state`**，状态机的状态只由 §3/§4/§5.1/§6/§8 中的流转边改变。

---

## 6. 阶段四：办结（open / on_hold → resolved）

两条入口，结果完全同源（都走 `apply_transition`）：

1. **处理人提交"处理说明"**（articles reply）→ 自动流转到 resolved；
2. **直接标记已处理**（`PATCH /tickets/{id}`，`state=resolved`，Action=`resolve`）。

条件与副作用：

| 项 | 内容 |
|---|---|
| 权限 | **当前处理人**（owner）专属，否则 403「只有当前处理人可执行此操作」 |
| 原因 | 不必填 |
| 副作用 | `solved_at=now`、`resolved=True`；最后处理节点返回客服时结束当前 SLA 轮次，超时则记录该轮及工单超时 |
| Flow Log | Action = `resolve`，记录上一状态停留时长与人员快照 |

进入 `resolved` 后，工单回到**客服侧**：等待回访、可能被退回、最终归档。

---

## 7. 阶段五：回访闭环与归档（resolved → archived）

### 7.1 回访字段

| 字段 | 含义 |
|---|---|
| `callback_required` | **流程配置**：这张单是否要求回访 |
| `is_callbacked` | 是否已完成回访 |
| `callback_details` | 回访记录内容 |
| `satisfaction` | 满意度：`satisfied / average / dissatisfied / unrated` |

### 7.2 归档的条件判断（同一份判定，双卡生效）

执行归档时 `apply_transition` 按顺序检查；`allowed_actions` 用同一函数推导，因此**按钮不出现的地方，硬调接口也一定被拒**：

1. **合法性**：`resolved → archived` ∈ TRANSITIONS；
2. **权限**：操作人角色必须是 `agent`（客服团队）或 admin，否则 403「只有客服团队可执行归档操作」；
3. **业务前置**：`satisfaction == "dissatisfied"` → **422「客户满意度为「不满意」，需退回重新处理并完成回访后才能归档」**，同时 `compute_allowed_actions` 直接把归档按钮过滤掉。

归档请求可在同一请求里携带 `archive_notes` / `callback_details` 等闭环字段（**闭环字段先于状态流转应用**，保证前置校验看到的是"应用后"的值，堵死同请求绕过）。

### 7.3 回访事实保护规则（防止配置抹掉事实）

- `callback_required=false`（改成不需回访）**不会**清除已产生的回访事实；`is_callbacked`、`satisfaction`、`callback_details` 全部保留 → dissatisfied 依然被归档前置拦截。
- `is_callbacked=false` 同理，且当 `satisfaction=dissatisfied` 时绝不清除满意度。
- 把 `satisfaction` 从 `dissatisfied` 改成其他值 → **422「客户不满意：需退回重新处理并完成新一次回访后才能变更评价」**。
- **唯一合法的重置路径**：`resolved → open` 重开（见 §8.4），其副作用清空 `satisfaction`（`callback_details` 保留为历史）。

### 7.4 归档副作用与终局

- `closed_at = now`，`closed_duration_minutes = (now - created_at)` 分钟数；
- Flow Log：Action = `archive`；
- 状态变为 `archived`（**终态**）：无出边、无沟通记录、无任何 `allowed_actions` —— 全链路结束。

---

## 8. 旁路与异常分支（逐条）

### 8.1 退回 pending → returned（受理侧打回给创建人）

- **权限**：该部门的对接人（或 admin），否则 403「只有部门对接人可退回待受理工单」；**原因必填**（400）。
- **副作用**：`returned_to_user_id = creator_id`、`owner_id = creator_id`（退回给创建工单的客服）；`has_returned = true`。
- Flow Log Action = `return`。

### 8.2 重新提交 returned → pending

- **权限**：仅创建者（或 admin），否则 403「只有创建者可处理已退回工单」；**不必填原因**。
- **副作用**：`owner_id=None`、`returned_to_user_id=None` —— 回到无处理人状态，等待再次分派。
- Flow Log Action = `resubmit`；`has_returned = false`（新动作覆盖旧标记）。

### 8.3 打回 open → pending（处理人退回给团队）

- **权限**：当前处理人；**原因必填**。
- **副作用**：`owner_id=None`（等待重新分派）；因属于退回动作，`has_returned = true`。
- Flow Log Action = `return`（与 §8.1 共用同一 action 类型，靠 `from_state/to_state` 区分方向）。

### 8.4 退回重开 resolved → open

- **权限**：工单**创建者**或**客服团队（agent）**，否则 403「只有创建者或客服团队可退回已处理工单」；**原因必填**。
- **副作用**：`satisfaction = None`（上一轮回访结果随本轮失效，等待再次回访；`callback_details` 保留）。
- Flow Log Action = `reopen`。
- 这是**不满意工单走出 422 拦截的唯一通路**。

### 8.5 业务约束改写：resolved → on_hold 自动变成 resolved → open

- `enforce_business_constraints`：请求 `resolved → on_hold` 时自动改写为 `resolved → open`（on_hold 是暂停位，没人主动 unpause 会永久卡住；客服本意是"打回让处理人重做"）。
- 执行时记一条 warning 日志；`allowed_actions` 推导时静默改写并去重（前端看到的永远是 `reopen → open`）。
- 权限不受影响（两条边权限规则一致）。

### 8.6 撤销 → cancelled（终态）

- **来源状态**：`pending` / `open` / `on_hold` / `returned` 四选一；**archived 不可撤销**。
- **权限**：仅**创建者**（或 admin），否则 403「只有工单发起人可撤销工单」；**原因必填**（400）。
- **副作用**：`closed_at` / `closed_duration_minutes` 结案记录；Flow Log Action = `cancel`。
- 终局：`cancelled`，无出边。

### 8.7 has_returned 的统一规则

`has_returned` 始终跟随**最新一次动作**：`ticket.has_returned = (from, to) ∈ {("pending","returned"), ("open","pending")}`。即只有这两种"退回"动作置 true，其余任何动作（含 resubmit、分派）都会把它刷回 false。

---

## 9. 三个循环

### 9.1 不满意闭环循环（核心业务循环）

```
resolved --(回访判定 dissatisfied)--> 归档被 422 拦截 / 归档按钮不下发
   ↑                                      |
   |                                      v（唯一通路）
   +--------- reopen（创建者或客服，需原因，满意度清零）--------- open
                open --(处理人重新处理并提交说明)--> resolved --(再次回访)--> ...
                                                                    |
                                            满意 / 未评价 / 无需回访
                                                                    v
                                                                archived ✓
```

1. `resolved` 想归档，但 `satisfaction=dissatisfied` → 422，按钮也不出现；
2. 只能退回重开：`resolved → open`（需原因，`satisfaction` 清零、回访记录保留）；
3. 处理人重新处理 → 再次 `open → resolved`；
4. 重新回访 → 只要不再是 dissatisfied（或确认无需回访）→ `resolved → archived` 完成闭环。

> 配置类字段（`callback_required=false` 等）**不能**打断这个循环的门槛——见 §7.3。

### 9.2 退回—重提循环

```
pending ⇄ returned（pending→returned 对接人退回需原因；returned→pending 创建者重提）
   |
   +→ open（分派）→ ... 可再次 open→pending→returned，循环任意次
```

- 每次退回 `has_returned=true`，每次重新提交刷回 false；
- 典型异常链（回归测试走查）：`create → dispatch → hold → resume → return → return → resubmit → cancel`。

### 9.3 暂缓—恢复循环

```
open ⇄ on_hold（hold：处理人需原因；resume：处理人需原因，同样需原因）
on_hold → resolved（处理人确认，可直接办结） ；on_hold → cancelled（创建者撤销）
```

- 处理人不变，暂缓期间解决时限继续计时；
- 循环可重复任意次，每次都在 Flow Log 留痕并记录停留时长。

---

## 10. 横切规则汇总

### 10.1 全部合法流转（17 条边，唯一事实来源 `TRANSITIONS`）

| from \ to | pending | open | on_hold | resolved | returned | cancelled | archived |
|---|---|---|---|---|---|---|---|
| **(建单 None)** | create | | | | | | instant_resolve |
| **pending** | — | dispatch | | | return | cancel | |
| **open** | return | — | hold | resolve | | cancel | |
| **on_hold** | | resume | — | resolve | | cancel | |
| **resolved** | | reopen* | (改写) | — | | | archive |
| **returned** | resubmit | | | | — | cancel | |
| **archived / cancelled** | （终态，无出边） | | | | | | |

\* `resolved → on_hold` 表面合法但会被改写为 `resolved → open`，实际不可达。

**原因必填的边**（缺 reason → 400）：`open→pending`、`open→on_hold`、`on_hold→open`、`resolved→open`、`pending→returned`、全部 4 条 `→cancelled`。
**其余边**（dispatch / resolve / archive / resubmit / 建单）不必填原因。

### 10.2 权限矩阵（唯一定义处 `transition_permission_error`）

| 流转 | 谁可以执行 | 否则 |
|---|---|---|
| `pending → open` 分派 | 该部门对接人 | 403；且非 admin 必须指定处理人（422） |
| `open → resolved` / `open → on_hold` / `on_hold → resolved` / `open → pending` / `on_hold → open` | **当前处理人** | 403「只有当前处理人可执行此操作」 |
| `resolved → open` / `resolved → on_hold` | 创建者 或 agent | 403「只有创建者或客服团队可退回已处理工单」 |
| `→ cancelled`（pending/open/on_hold/returned） | **创建者** | 403「只有工单发起人可撤销工单」 |
| `resolved → archived` | **agent**（客服团队） | 403「只有客服团队可执行归档操作」 |
| `pending → returned` | 该部门对接人 | 403「只有部门对接人可退回待受理工单」 |
| `returned → pending / cancelled` | 创建者 | 403「只有创建者可处理已退回工单」 |
| 其他 | — | 403「无权执行此状态变更」 |

**admin 全权限**（除个别输入要求外，任何合法边都能执行）。

### 10.3 执行收口顺序（`apply_transition` 八步，任何入口都不旁路）

1. 业务约束改写（`resolved→on_hold` → `open`）→ 目标等于当前状态则 no-op 返回；
2. 合法性 `validate_transition` → 非法 **422**；
3. 权限 `check_transition_permission` → **403**（分派缺处理人为 **422**）；
4. 原因必填 `requires_reason` → 缺 reason **400**；
5. 业务前置 `transition_precondition_error`（不满意不可归档）→ **422**；
6. 状态副作用（first_owner / solved_at / resolved / SLA breach / owner 清理 / returned_to_user / closed_at / hold_until / 满意度重置）；
7. 应用调用方显式人员字段（显式值优先于副作用）；
8. `has_returned` 同步 + 写 Flow Log（上一状态停留时长 + 人员快照 + action_type）。

建单/草稿提交/即时办结走 `apply_initial_state`（初始态合法性 → 终态副作用 → Flow Log），与上表共享同一套规则。

**入口全景**（都收口到执行入口，无第二条写 `ticket.state` 的路径）：
`POST /tickets`（正式建单 / 即时办结）、`POST /tickets/drafts/{id}/submit`（草稿提交）、`PATCH /tickets/{id}`（单条，闭环字段先应用）、`POST /tickets/batch-update`（批量）、`POST /tickets/{id}/articles` 的 reply（→ resolved）。

### 10.4 批量更新语义（batch-update）

- 状态流转与单条 PATCH 同源（同一执行入口）；
- **非法流转**：跳过该工单（保留批量接口容错语义），继续处理其余；
- **无权限 / 缺 reason**：整批拒绝（403 / 400），事务回滚，**不做部分提交**。

### 10.5 Flow Log 的 action_type

- 新写入的日志**必有**业务动作类型：`action_type = 显式覆盖值 或 action_for(from, to)`，映射表覆盖全部 17 条边（create / instant_resolve / dispatch / return / cancel / resolve / hold / resume / reopen / resubmit / archive）；
- **动作覆盖**：`direct_assign`（建单直指派，§3.5）与 `refine` / `transfer`（域动作）不属于任何流转边，靠显式 `action_type` 覆盖写入；
- 接口读取时 `log.action_type or action_for(from, to)` —— 后者**仅**作为迁移前 NULL 历史行的展示兜底；
- `duration_minutes` = 该日志到上一条日志之间的停留分钟数（首条为 None）。

### 10.6 按钮可见性与执行结果永远一致

前端只渲染后端返回的 `allowed_actions`（每项含 `action / target_state / requires_reason / requires_owner / label`），点击后直接调用后端。`allowed_actions` 与 `apply_transition` 共用同一套：TRANSITIONS、业务约束改写、权限矩阵、前置校验 —— **可见即可执行，不可见必被拒**，前端不自行判断任何状态规则。

### 10.7 HTTP 状态码速查

| 码 | 触发场景 |
|---|---|
| 400 | 需要原因的流转缺 `reason` |
| 403 | 权限不足（矩阵任一不满足） |
| 409 | 同一 resolved 节点重复提交处理说明 |
| 422 | 非法流转 / dissatisfied 归档 / 分派缺处理人 / 建单缺对接人 / 直指派建单缺处理人或处理人不在责任部门 / 沟通记录状态或角色不符 / 催办重复 / satisfaction 取值非法等输入与前置问题 |

---

## 11. 端到端场景走查（Flow Log action 序列）

| 场景 | action 序列 | 说明 |
|---|---|---|
| 标准闭环 | `create → dispatch → resolve → archive` | 最短正常路径 |
| 直指派分类 | `create → direct_assign → resolve → archive` | 建单即指定处理人，免分派（§3.5） |
| 即时办结咨询 | `instant_resolve` | 一跳到终态，免分派免回访 |
| 草稿转正 | （草稿无日志）`create → dispatch → …` | 提交瞬间记 create |
| 不满意闭环 | `create → dispatch → resolve → reopen → resolve → archive` | reopen 清满意度后再回访 |
| 异常全链 | `create → dispatch → hold → resume → return → return → resubmit → cancel` | 暂缓/恢复/打回/退回/重提/撤销全覆盖 |
| 退回重派 | `create → dispatch → return → return → resubmit → dispatch → resolve → archive` | open→pending→returned→pending 循环后归档 |

---

## 12. 与前端的分工（一句话版）

- **后端**：规则（TRANSITIONS）、权限、前置、副作用、日志 —— 全部在 `state_machine.py` 一处定义，所有入口收口执行；
- **前端**：只负责按 `allowed_actions` 画按钮、按 `requires_reason` 画原因输入框、按 `requires_owner` 画处理人选择框，提交后照单显示错误信息；
- **审计**：每次状态变化必有一条 Flow Log（含动作类型、原因、停留时长、人员快照），全链路可回放。
