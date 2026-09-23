# 客服工单 V0.86 最小架构改造 — 实施结果报告

> 范围：`main` 分支客服工单流程（不含 POC）。严格按 Phase 0→9 顺序实施，
> 每个 Phase 独立修改、独立测试、独立提交，全程未混入无关工作区改动、
> 未 force push、未 rebase、未触碰 POC 分支与容器。

## 一、完成情况总览

| Phase | 内容 | 提交 | 结果 |
| --- | --- | --- | --- |
| 0 | 流转基线测试（收口前固化现状契约） | `30a27dc` test(ticket): add transition baseline coverage | 27 用例（含 5 个已知缺陷 xfail） |
| 1 | 单条 PATCH 状态流转执行收口 | `515a242` refactor(ticket): centralize single-ticket transition execution | 3 个失败修复为通过（first_owner 等） |
| 2 | 批量流转走同一执行入口 | `8d650c0` refactor(ticket): route batch transitions through executor | 4 个 xfail 转正 |
| 3–4 | 初始状态（建单/即时/草稿）与文章回复统一 | `be51196` refactor(ticket): unify reply and initial state transitions | 通过 |
| 5 | Flow Log `action_type`（目标④） | `77b21e8` feat(ticket): add transition action type to flow logs | 迁移已应用（测试库+dev 库） |
| 6 | 后端 `allowed_actions` / 能力位（目标②） | `c48521c` feat(ticket): expose allowed actions from backend rules | 通过 |
| 7 | 前端渲染后端动作元数据（去规则副本） | `712cedd` refactor(frontend): render ticket actions from backend metadata | vue-tsc 与基线一致 |
| 8 | 客户闭环规则（目标③）：`callback_details` + 不满意禁归档 | `07eb826` fix(ticket): enforce customer callback closure rules | 通过 |
| 9 | 全量回归 + 闭环链路测试 + 本报告 | `0c41867` test(ticket): complete workflow architecture regression | 112 passed / E2E 18:18 |
| 收尾 | 关闭 callback 绕过、即时办结终态副作用收口、Phase 编号修正、本报告更新 | 本报告所在提交 | 113 passed / E2E 18:18 |

四项目标达成情况：

1. **状态流转执行收口**：✅ `ticket.state` 全仓仅剩 2 处赋值，均在
   `backend/app/services/state_machine.py` 的 `apply_transition` /
   `apply_initial_state`；`TicketStateLog` 也仅由这两处构造。
2. **后端唯一事实来源**：✅ `TRANSITIONS / validate_transition /
   requires_reason / enforce_business_constraints / 权限矩阵 /
   TRANSITION_ACTIONS / 能力位规则` 全部收在 `state_machine.py` 一处；
   详情接口下发 `allowed_actions/is_terminal/can_reply/can_addition/can_remind`，
   前端按钮可见性与提交目标状态均读后端。
3. **客服闭环规则**：✅ `callback_details` 贯通（写入/读取/展示）；
   `satisfaction=dissatisfied` 禁止归档（执行入口 422 + 动作不下发，
   单条 PATCH 与批量同源拦截）；重开时满意度失效避免闭环死锁。
4. **Flow Log action_type**：✅ 迁移 + 模型 + 全映射（create / instant_resolve /
   dispatch / return / hold / resume / resolve / reopen / resubmit / archive / cancel）+
   历史 NULL 行接口按 `action_for(from,to)` 推导兜底。

## 二、核心文件

| 文件 | 职责 |
| --- | --- |
| `backend/app/services/state_machine.py` | **唯一事实来源与唯一执行入口**：流转表/合法性/原因规则/业务约束改写（resolved→on_hold→open，`log_rewrite` 可静默）、人员快照、权限判定（`transition_permission_error` + `check_transition_permission`）、动作映射 `TRANSITION_ACTIONS/action_for/ACTION_LABELS`、闭环前置 `transition_precondition_error`、能力位 `compute_allowed_actions/compute_article_actions`、执行器 `apply_transition/apply_initial_state` |
| `backend/app/api/v1/tickets.py` | PATCH/批量/建单/即时办结/草稿提交全部改调执行器；回访闭环字段**先于**状态流转应用；`get_ticket` 挂载 allowed_actions 与能力位；state-logs 端点下发 `action_type`（含历史兜底） |
| `backend/app/api/v1/articles.py` | 回复 → `apply_transition(resolved)`；常量迁至 state_machine（仅 `URGE_MAX_LENGTH` 留本地） |
| `backend/app/schemas/ticket.py` | 新增 `AllowedAction`；`TicketDetail` 增 `allowed_actions/is_terminal/can_reply/can_addition/can_remind` |
| `backend/app/models/ticket.py` | `TicketStateLog.action_type: String(30) NULL` |
| `backend/alembic/versions/j2d3e4f5g6h7_add_state_log_action_type.py` | head（`down_revision=i1c2d3e4f5g6`，`sa.inspect` 列守卫幂等） |
| `backend/tests/test_transition_baseline.py` | 47 用例：单条流转契约 + Phase5/6/8 扩展 + 收尾回访回归 (a)(c)（sections 1–14） |
| `backend/tests/test_workflow_regression.py` | 4 用例：标准闭环链 / 异常分支链 / 不满意闭环(b) / 即时办结副作用分工 |
| `frontend/src/types/index.ts` | `AllowedAction` + Ticket 元数据字段（含 `callback_details/satisfaction`） |
| `frontend/src/api/tickets.ts` | 删 `isReturnTransition`；`is_return` 改由后端 `action_type` 决定 |
| `frontend/src/views/TicketDetailView.vue` | 5 个 canXxx 角色/状态判断 → `allowed_actions` 查找；`resolveReturnTarget` 删除；归档表单接入回访详情与不满意分支 |
| `frontend/src/components/ticket/ReplyEditor.vue` | 3 个状态数组 + isOwner 判断 → `can_*` 能力位；暂缓按钮读 `hold` 动作与 target_state |
| `frontend/src/components/ticket/TicketInfoSidebar.vue` | 新增「回访」区块（状态/满意度/回访详情展示） |

## 三、数据库迁移

- 新增1个：`j2d3e4f5g6h7`（`add_ticket_state_logs.action_type`，nullable，带列存在性守卫可重复执行）。
- 测试库：pytest 每次 `alembic upgrade head` 自动应用。
- dev 库：通过 `docker cp` 迁移文件进 `skdy-ticket-dev-api-1` 后容器内
  `alembic upgrade head` 应用（alembic 目录未挂载），已验证列存在、
  `alembic_version` 打戳、历史日志读取正常；迁移带守卫，镜像重建后重跑幂等。
- 历史行 `action_type` 保持 NULL，**不回填**；接口层按流转表推导。

## 四、测试与验证结果

| 层 | 结果 |
| --- | --- |
| 相关回归（两份流程测试文件） | **51 passed**（baseline 47 + workflow 4） |
| 后端 pytest 全量 | **113 passed**（存量 62 + 本次新增 51），0 failed |
| E2E（live dev API :8001） | **18/18 PASS**，rc=0（收尾批 `20260924-073348`；Phase9 批 `20260923-172623`/`172132` 亦 18/18），alembic head `j2d3e4f5g6h7` |
| 前端 vue-tsc | **58 个错误，与改造前基线逐条一致（无新增）**（58 为既有问题，不在本次范围） |
| 前端构建 | `npx vite build` ✓ built（`npm run build` 被既有 vue-tsc 错误挡住，非本次引入） |
| 冒烟链路 | 标准闭环（建单→分派→处理说明→回访满意→归档）、异常分支（暂缓/恢复/打回/退回/重新提交/撤销）、不满意拦截→重开→再处理→满意归档、即时办结、批量跳过非法流转 —— 均由 `test_workflow_regression.py` 与基线用例覆盖并通过 |

链路 `action_type` 断言示例：
- 标准闭环 = `[create, dispatch, resolve, archive]`
- 异常分支链 = `[create, dispatch, hold, resume, return, return, resubmit, cancel]`
- 不满意闭环 = `[create, dispatch, resolve, reopen, resolve, archive]`

`action_type` 写入机制核验（收尾，无代码改动）：
- **唯一写入点**：全仓 `TicketStateLog(` 构造仅 `state_machine.py` 两处
  （`apply_initial_state` / `apply_transition`）；业务调用如带显式
  `action_type` 则 `action_for(from, to, override)` **override 优先**，
  未显式时在**写入时点**按唯一映射 `TRANSITION_ACTIONS` 落库（新数据恒为非 NULL，
  由闭环链路用例逐条断言 `in ACTION_TYPES`）。
- **读取端兜底**：`get_state_logs` 仅对迁移前的 NULL 行执行
  `log.action_type or action_for(...)` 展示推导（测试
  `test_action_type_nullable_for_history` 断言 DB 仍为 NULL、接口推导为
  `resolve`）——`action_for` 不参与新数据生成。

## 五、保留的既有语义（兼容性）

- 批量：非法流转跳过该工单；403/400/422 整批拒绝并回滚（`get_db` 事务语义）。
- admin 分派可不选处理人（`check_transition_permission` 中 admin 早退保留原422豁免）。
- resolved→on_hold 静默改写为 open（`enforce_business_constraints`，日志/动作生成时静默，带 `log_rewrite` 标记）。
- reopen 保留 `solved_at/resolved=True`（语义=曾解决时间）。
- `callback_required` 是"是否要求回访"的流程配置：**仅在尚未产生回访事实
  （`is_callbacked=true` / 不满意）时**才同步标记并清空满意度；已回访事实
  （含 `dissatisfied`、`callback_details`）不可被配置字段抹掉（收尾闭环）。
- 一条 resolved 节点仅一条处理说明的 409 守卫原样保留。
- API 兼容：`allowed_actions/is_terminal/can_*` 均为**新增字段**，请求/响应既有结构未变。

## 六、绕过点核验记录

1. **`callback_required=false` 绕过：已彻底关闭（收尾）**。规则改为
   "已产生的客户回访事实不可被流程配置抹掉"：`callback_required=false`、
   显式 `is_callbacked=false` 都不再清空既有 `satisfaction`（尤其
   `dissatisfied`）与 `callback_details`；`dissatisfied` 也不可原地改写为
   满意 —— 唯一合法重置路径是 `reopen`（退回重开副作用清空满意度）。
   归档前置继续拦截 → 必须重开→重新处理→新一次回访→归档。
   回归覆盖：
   - (a) `test_callback_config_cannot_erase_callback_facts`（dissatisfied →
     callback_required=false → 仍 422；含同请求组合与 `is_callbacked=false` 变体）
   - (b) `test_dissatisfied_closure_loop`（拦截 → reopen → 再处理 → 满意 → 归档）
   - (c) `test_no_callback_config_behavior_unchanged`（无回访时原行为不回归）
2. **即时办结终态副作用重复：已最小收口（收尾）**。构造期不再写
   `closed_at/closed_duration_minutes`，两者与 `TicketStateLog` 唯一归属
   `apply_initial_state`（执行入口）；`resolved/solved_at/resolution/
   回访标志/solution_deadline` 属建单初始化数据（执行入口对该路径不产生
   这些字段），保持现状。SLA breach 标记不被即时办结触碰。
3. **SLA 领域**（非目标，未改）：`sla_scanner` 不豁免 on_hold；
   批量修改 priority 不重算 `solution_deadline`（单条 PATCH 会重算）；
   `ComplaintEscalationPolicy.required_role` 无消费方。

## 七、剩余的前端规则副本（均为展示层，非业务判定）

前端已**无权限/流转/目标状态类规则副本**（全部经 `allowed_actions`/`can_*`）；
残留字面量仅用于展示与兜底：

- `TicketTable.vue`：终态行样式（`archived/cancelled`）、各状态显示哪个人员列。
- `StateLogTimeline.vue`：时间线文案、归档区块、各状态图标。
- `api/overviews.ts`：看板计数分组键。
- `target_state || 'open'/'archived'/...`：仅后端字段缺失时的防御性默认值。
- `STATE_MAP/stateStrToObj`（展示映射）、`STATE_ID_TO_KEY/PRIORITY_ID_TO_KEY`
  （列表筛选查询编码，纯参数翻译）。

## 八、已知未处理 / 有意行为差异

1. **回访满意度随重开失效（本次新增规则）**：`resolved→open` 时
   `satisfaction=None`（`callback_details` 保留为历史）。否则不满意会永久
   隐藏归档动作导致闭环死锁。UI 流程：不满意 → 归档卡片内「保存回访结果」
   （不归档）→ 警告提示走「退回」→ 重开处理 → 再回访 → 归档。
2. **不满意时归档卡片消失**：`allowed_actions` 不下发 `archive`
   （前置不满足的候选被过滤），执行侧另有 422 兜底；提示文案出现在
   「保存回访结果」提交时的 warning 消息中。
3. **时间线 resume 不再显示「退回」徽标**：旧 `is_return` 把"恢复处理"也标成
   退回（把 `hold/resume` 推导为 return 类型）；现按后端 `action_type`
   （`return/reopen`）判定，属有意修正。
4. **文章回复409守卫为死代码**：状态门禁（仅 `open/on_hold` 可回复文章）已使
   "resolved 下第二条回复"不可达；按"不修复范围外问题"原则原样保留。
5. **E2E 覆盖边界**：E2E 套件覆盖分类路由/投诉/即时办结/归档主链路
   （18 场景），不直接覆盖 退回/on_hold/reopen/cancelled/批量 —— 这些由
   后端 pytest 链式用例（`test_workflow_regression.py` + 基线文件）覆盖。
6. **前端58个既有 vue-tsc 错误**未修（非本次引入，见 `/tmp` 基线对照）。
7. dev 容器热加载仅 `app/`：迁移需容器内执行（本次已处理，见第三节）。

## 九、验证复现命令

```bash
# 相关回归
cd backend && .venv/bin/pytest -q tests/test_transition_baseline.py tests/test_workflow_regression.py   # 期望51 passed

# 后端全量
.venv/bin/pytest -q                                 # 期望113 passed

# E2E（需 dev 栈 :8001）
python3 e2e_tests/scripts/run_e2e.py              # 期望 rc=0,18/18

# 前端
cd frontend && npx vue-tsc -b                     # 期望58 errors（与基线一致）
npx vite build                                    # 期望 ✓ built
```
