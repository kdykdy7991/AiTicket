# 07 需求补充：客服组端到端工单模块

> 来源：客户提供的 `客服组端到端工单模块需求补充.docx`
> 状态：**待评审** — 与现有 `01_requirements.md` 并列，作为 MVP 范围调整的参考
> 最后更新：2026-06-04

本文档梳理了 docx 中**未被现有需求/数据模型覆盖**的字段和功能点，并给出补充建议。详见对应的实施任务见 `06_implementation_plan.md` P7 阶段。

---

## 1. 文档结构对照

| docx 章节 | 内容 | 对应现状 |
|---|---|---|
| 一、工单创建 | 用户信息 / 工单来源 / 重投 / 重复提醒 | 部分缺失（P0） |
| 二、工单流转 | 客服组确认 / 政企标记 / 批量处理 / 节点时长 / 追加 / 超时底色 | 多数缺失（P0-P1） |
| 三、工单报表 | 多筛选批量导出 / 新增量 / 闭环量 / 各组平均时长 / 超时率 / 一次解决率 / 故障分类 | 字段不全（P2） |
| 补充：导出字段 | 4 大块字段清单（基础/用户/分类/流转） | 全部新增（P2） |

---

## 2. 字段补充清单（按 P0/P1/P2 分级）

> **P0 = 数据模型层必加；P1 = 前端表单/视图必改；P2 = 报表/导出**

### 2.1 P0 — 数据模型层（`03_data_model.md` §2.8 tickets 表 + 新表）

| 字段 / 表 | 类型 | 说明 | 关联需求 |
|---|---|---|---|
| `customer_type` | ENUM('personal','enterprise') | 个人 / 政企 | 一.用户信息 |
| `customer_phone` | VARCHAR(20) | 客户手机号（创建时锁定冗余） | 一.用户信息 |
| `device_sn` | VARCHAR(64) | 终端 / 设备 SN | 一.用户信息 |
| `contact_name` | VARCHAR(100) | 联系人（可与客户不同）| 一.用户信息 |
| `contact_phone` | VARCHAR(20) | 联系电话 | 一.用户信息 |
| `region` | JSONB | `{"province":"","city":"","district":"","station":""}` | 一.用户信息 |
| `category_l1_id` | INT FK | 一级问题分类 | 三.分类标签 |
| `category_l2_id` | INT FK | 二级问题细分标签 | 三.分类标签 |
| `symptom` | TEXT | 故障现象描述（与 title 区分）| 三.分类标签 |
| `is_duplicate` | BOOL | 是否重投工单 | 一.重投 |
| `duplicate_reason` | TEXT | 重投原因 | 一.重投 |
| `duplicate_of_id` | INT FK → tickets.id | 重投自哪条工单 | 一.重投 |
| `first_owner_id` | INT FK → users.id | 首次受理坐席（与 owner 区分）| 四.处理流转 |
| `skill_group_id` | INT FK → groups.id | 归属技能组（技术/市场/售后） | 四.处理流转 |
| `sla_breached` | BOOL | SLA 是否达标 | 四.处理流转 |
| `resolved` | BOOL | 是否解决 | 四.处理流转 |
| `resolution` | TEXT | 处理备注 / 解决方案 | 四.处理流转 |
| **新表** `ticket_categories` | — | 树状分类（id/parent_id/name/sort_order） | 三.分类标签 |
| **新表** `regions` | — | 省/市/区县/站点树 | 一.用户信息 |
| **新表** `ticket_state_logs` | — | `(id,ticket_id,from_state,to_state,entered_at,left_at,duration_seconds)` | 二.流转节点 |
| **articles 表扩展** | `is_addition BOOL` + `append_reason TEXT` | 追加记录 + 追加原因 | 二.追加 |

### 2.2 扩展现有枚举

**`ticket_states` 新增种子：**

| name | state_type | 说明 |
|---|---|---|
| `awaiting_callback` | `pending` | 待回访（客服组确认）|
| `callbacked` | `closed` | 已回访 |

**`ticket_priorities` 新增种子：**

| name | ui_color | sort_order | 说明 |
|---|---|---|---|
| `enterprise_critical` | `#7c2d12` | 5 | 政企特急 |

**`ticket_priorities` 扩展字段：** `customer_type_restriction`（仅 personal/仅 enterprise/NULL）— 用于前端按用户类型过滤可选优先级。

**`channel` 扩展：**

```ts
// types/index.ts Ticket.channel
channel: 'web' | 'email' | 'phone' | 'wechat' | 'app'
```

### 2.3 P1 — 前端表单/视图

| 需求点 | 涉及文件 | 改动 |
|---|---|---|
| 用户信息完整录入（手机号/终端SN/用户类型/联系人/电话/区域）| `views/TicketCreateView.vue` | 新增 6-7 个表单项；区域用级联 `el-cascader` |
| 工单来源扩展 | `views/TicketCreateView.vue` + `components/ticket/TicketInfoSidebar.vue` | 改 `channel` 选项 + 渠道 chip 颜色映射 |
| 重投工单 + 重复检测 | `views/TicketCreateView.vue` + 新组件 `DuplicateTicketWarning.vue` | 开关 + 原因输入；输入手机号/SN 触发后端查重接口，弹窗"疑似重复 N 条" |
| 政企加急标识 | `types/index.ts` + `components/common/StateTag.vue`（或新 `CustomerTypeChip.vue`）| 全局 chip |
| 批量处理 | `components/ticket/TicketTable.vue` + `views/TicketListView.vue` | `type="selection"` + 工具栏（批量改状态/分配/组/优先级） |
| 即将超时/超时底色 | `components/ticket/TicketTable.vue` | `row-class-name` hook：根据 `escalation_at` 距 now 的差值加 `el-table__row--warning/danger` |
| 流转节点时长 | 新组件 `components/ticket/StateLogTimeline.vue` | 工单详情新增 tab 或侧栏区块 |
| 回访状态流转 | `components/ticket/TicketInfoSidebar.vue` 状态 select | `awaiting_callback` / `callbacked` 加入选项 |
| 追加原因 | `components/ticket/ReplyEditor.vue` | 加 `is_addition` checkbox + `append_reason` 输入 |

### 2.4 P2 — 报表 / 导出

**`DashboardStats` 扩展（`types/index.ts`）：**

```ts
interface DashboardStats {
  // 已有省略...

  // 新增
  in_progress: number                    // 处理中量
  sla_breach_rate: number                // 超时率（百分比 0-100）
  first_contact_resolution_rate: number  // 一次解决率
  avg_resolution_per_group: Array<{      // 各组平均处理时长
    group_id: number
    group_name: string
    minutes: number
  }>
  tickets_by_category: Array<{           // 故障分类统计
    category_l1: string
    count: number
  }>
}
```

**导出字段（4 大块，22 列）：**

| 大块 | 列名 |
|---|---|
| 基础核心 | 工单编号 / 创建时间 / 结案时间 / 关闭时长 / 当前状态 / 工单来源 |
| 用户信息 | 用户姓名 / 联系手机号 / 设备SN / 所属区域 / 用户类型 |
| 分类标签 | 一级问题分类 / 二级细分标签 / 故障现象描述 / 是否重复 / 优先级 |
| 处理流转 | 首次受理坐席 / 归属技能组 / 流转记录 / 首次响应时间 / SLA是否达标 / 处理备注或解决方案 / 是否解决 |

**新 API：** `GET /api/v1/tickets/export?format=csv|xlsx&...filters` — 复用列表 filters，支持按筛选条件批量导出。

---

## 3. 业务规则补充

### 3.1 重投工单检测规则

后端在创建工单前自动检查（前端仅做交互提示）：

```
SELECT id, number, title, created_at
FROM tickets
WHERE customer_phone = :phone
  AND device_sn = :device_sn       -- 同一设备
  AND category_l1_id = :cat_l1     -- 同一问题类型
  AND state_type NOT IN ('closed', 'merged')
  AND created_at > now() - INTERVAL '30 days'
ORDER BY created_at DESC
LIMIT 5;
```

- 命中 ≥ 1 条 → 标记 `is_duplicate=true`，并弹窗让客服确认是否关联到 `duplicate_of_id`
- 命中 0 条 → 直接创建

### 3.2 SLA 超时底色规则

| 距 `escalation_at` 时间 | 底色 class | 状态语义 |
|---|---|---|
| > 20% 剩余 | 无 | 正常 |
| 0% – 20% 剩余 | `el-table__row--warning` | 即将超时 |
| < 0%（已过） | `el-table__row--danger` | 已超时 |

### 3.3 批量处理权限

- 批量改状态/分配/组：要求当前用户是工单所属 group 的 agent 或 admin
- 批量删除：仅 admin
- 单次批量上限：100 条（防止误操作）

### 3.4 流转节点时长记录

- 每次状态变更（手动或 Trigger）写一条 `ticket_state_logs`
- 工单详情页"流转时间线"展示：状态名 / 进入时间 / 离开时间 / 停留时长
- 用于"各组平均处理时长"统计

---

## 4. 与现有模型的兼容性

✅ 现有 `tickets` 表所有字段**不需要废弃**，新字段都是**增量添加**（除 `title` 不再兼任故障描述，建议新增 `symptom` 字段）。

✅ `ticket_states` 和 `ticket_priorities` 是可配置表，新增值只需插入种子数据，无需改结构。

✅ `articles` 表已支持 `internal` 模式，"追加原因"作为 article 的两个新字段，避免新建表。

✅ `organizations` 当前只用于客户归属，**复用并扩展字段**（`customer_type/address/region`）比新建表更简洁。

⚠️ `regions` 是新表，需要 seed 初始化中国行政区数据（≈ 3500 行，可从国家统计局公开数据导入）。

⚠️ 引入"客服组确认 / 待回访"流程后，状态机需扩展，建议放在 P7 子任务 `T-P7-04`。

---

## 5. 验收用例补充

**场景 C：政企加急工单端到端**

1. 政企客户（王五）通过服务号提交工单，附手机号 + 设备 SN
2. 系统检测到该设备 30 天内有同分类未关闭工单 → 标记 `is_duplicate=true`，弹窗关联到 TKT-00007
3. 创建后 Trigger 自动分配到"VIP 客服组"，优先级升级为 `enterprise_critical`
4. 张三（VIP 组）处理，状态 new → open → awaiting_callback
5. 张三联系客户确认问题已解决，状态变为 `callbacked`
6. 工单结案；报表中"政企工单"分类 +1，超时率 -0
