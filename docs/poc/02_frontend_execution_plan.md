# POC 问题闭环改造：前端开发任务书

## 1. 开发目标

将现有客服工单界面改造成 POC 问题闭环工作台。以 [开发总约定](./00_poc_workflow_development_contract.md) 为枚举和接口契约；后端接口未完成时使用本地 Mock 按相同响应结构开发，禁止继续围绕旧状态组件追加条件分支。

## 2. 交付边界

前端开发负责：

- 清除旧业务角色、状态、优先级及文案。
- 定义 POC TypeScript 类型和 API 客户端。
- 改造菜单、路由、登录后权限展示。
- 重写 POC 新建/草稿、列表、详情及阶段操作组件。
- 文件上传、流程时间线、退回交互。
- 用户管理中的新角色选项。
- POC 跟踪筛选和导出入口。
- 构建和主要人工验收。

前端不得仅靠按钮隐藏实现权限；后端 `allowed_actions` 是动作展示的直接依据，服务端负责最终鉴权。

## 3. 第一批：类型、枚举与 API

### FE-01 集中定义业务枚举

新增建议文件：`frontend/src/domain/pocWorkflow.ts`。

导出：

- `BUSINESS_ROLES`
- `POC_STATES`
- `POC_STATE_ORDER`
- `POC_PRIORITIES`
- `VERIFICATION_STATUSES`
- 标签、颜色和终态判断函数

要求：

- 编码完全采用总约定。
- 删除 `frontend/src/api/tickets.ts` 内重复的旧状态/优先级映射。
- 不再用数字 `state_id/priority_id` 在前端二次映射，直接使用字符串编码。
- `admin` 不放入业务责任人选择器；只在管理员用户管理中可见。

### FE-02 重写 TypeScript 类型

修改 `frontend/src/types/index.ts`，建议拆出 `frontend/src/types/poc.ts`：

```ts
export type BusinessRole =
  | 'presales'
  | 'approver'
  | 'taskforce'
  | 'subsystem'
  | 'quality'
  | 'admin'

export type PocState =
  | 'pending_approval'
  | 'pending_confirmation'
  | 'pending_routing'
  | 'pending_acceptance'
  | 'planning'
  | 'pending_plan_confirmation'
  | 'processing'
  | 'pending_quality_review'
  | 'pending_defect_registration'
  | 'closed'
  | 'returned'
  | 'cancelled'
```

补充总约定全部工单字段，并定义：

- `TicketBrief`
- `TicketDetail`
- `TicketCreatePayload`
- `TicketActionRequest`
- `TicketAction`
- `TicketAttachment`
- `AllowedAction`

删除或停止业务使用：`dispatcher`、`callback`、`satisfaction`、旧 `TicketChannel`、旧客服字段映射。

### FE-03 重写 API 适配层

修改 `frontend/src/api/tickets.ts`：

- 移除 `STATE_ID_TO_KEY`、`PRIORITY_ID_TO_KEY` 和旧 `adaptTicket` 兼容逻辑。
- API 响应尽量按 TypeScript 类型直接使用，只做日期和分页的轻量适配。
- 新增：

```ts
ticketApi.executeAction(id, request)
ticketApi.uploadAttachments(id, files, stage)
ticketApi.downloadAttachment(attachmentId)
```

- 收到 `409` 时提示“问题已被他人更新”，自动重新获取详情。
- 后端未就绪期间建立 `frontend/src/mock/poc/`，Mock 必须覆盖完整主流程及三条退回路径。

## 4. 第二批：路由、菜单与角色清理

### FE-04 路由守卫

修改：

- `frontend/src/router/index.ts`
- `frontend/src/stores/auth.ts`
- `frontend/src/layouts/TheSidebar.vue`
- `frontend/src/layouts/TheTopbar.vue`

要求：

- 售前可进入新建、草稿、本人问题。
- 批准人、专项小组、分系统、质量默认进入工单列表，并看到与本人相关的待办。
- 只有 `admin` 能进入用户、分系统及基础配置。
- 报表第一阶段仅 `quality/admin` 可见。
- 页面中不出现“客服组、处理人、部门对接人、回访、满意度”等旧业务名称。

### FE-05 用户管理

修改 `frontend/src/views/admin/UsersView.vue`：

- 角色为多选，只显示六个新编码（一人可多角色，至少一个）。
- `roles` 含 `subsystem` 时显示分系统多选，否则隐藏并清空。
- 其他业务角色不显示旧客服组/技能组互斥文案。
- `admin` 标注为“系统管理员（不参与业务流程）”。
- 用户列表使用新角色中文名。

分系统管理可继续复用 SkillGroup API，但页面统一显示“分系统”，不显示“技能组”。

## 5. 第三批：创建页和列表页

### FE-06 重写 POC 新建页

目标文件：`frontend/src/views/TicketCreateView.vue`。

按以下区块展示：

1. 基本信息
   - 问题名称
   - 提出人（必填，售前组公用账号时必须手填）
   - 提出部门（必填）
   - 产品线
   - 客户名称
   - 问题级别
   - 问题类型
   - 闭环要求
   - 批准人
2. 问题现象
   - 发生时间
   - 地点
   - 经度、纬度
   - 设备信息
   - 问题现象概述
3. 现场材料
   - 图片及附件上传

交互要求：

- “保存草稿”和“提交审批”两个动作。
- 正式提交前执行必填校验。
- 问题级别默认 P2 一般。
- 批准人列表只请求 `role=approver`。
- 提交成功跳转详情并显示“已提交，等待批准人审批”。
- 失败保留用户已填内容，不清空表单。

### FE-07 改造列表页

修改：

- `frontend/src/views/TicketListView.vue`
- `frontend/src/components/ticket/TicketFilters.vue`
- `frontend/src/components/ticket/TicketTable.vue`
- `frontend/src/components/common/StateTag.vue`
- `frontend/src/components/common/PriorityIcon.vue`

快捷标签：

- 全部
- 我的待办
- 待审批
- 待问题确认
- 待分系统接收
- 闭环计划
- 分析验证
- 待质量评审
- 待缺陷入库
- 已闭环
- 已退回

表格默认列：

- 编号
- 问题名称
- 客户名称
- 产品线
- 级别
- 当前阶段
- 分系统
- 当前责任人
- 计划完成时间
- 是否逾期
- 更新时间

筛选项：状态、级别、分系统、当前责任人、验证状态、是否逾期、创建时间、关键词。

## 6. 第四批：详情页和流程动作

### FE-08 重构详情页框架

目标文件：`frontend/src/views/TicketDetailView.vue`。

建议拆分：

```text
components/poc/PocSummaryCard.vue
components/poc/PocFieldSections.vue
components/poc/PocWorkflowStepper.vue
components/poc/PocActionPanel.vue
components/poc/PocAttachmentList.vue
components/poc/PocStateTimeline.vue
components/poc/actions/ApprovalForm.vue
components/poc/actions/ProblemConfirmationForm.vue
components/poc/actions/RoutingForm.vue
components/poc/actions/AcceptanceForm.vue
components/poc/actions/ClosurePlanForm.vue
components/poc/actions/PlanConfirmationForm.vue
components/poc/actions/AnalysisForm.vue
components/poc/actions/QualityReviewForm.vue
components/poc/actions/DefectRegistrationForm.vue
```

详情结构：

- 顶部：编号、名称、状态、级别、当前责任人、是否逾期。
- 中部左侧：问题信息和各阶段已填写数据。
- 中部右侧：流程步骤条和当前动作卡片。
- 底部：附件、操作记录、退回记录。

不要继续扩大现有详情页中的状态 `v-if` 集合；每个动作做独立组件，由 `allowed_actions` 选择渲染。

### FE-09 各节点表单

| 动作 | 表单内容 |
| --- | --- |
| `approve` | 审批意见；通过按钮 |
| `reject` | 驳回原因必填 |
| `confirm_problem` | 确认意见；确认按钮 |
| `route` | 分系统、分系统负责人必填 |
| `accept` | 接收意见可选 |
| `submit_plan` | 临时措施、长期措施、计划完成时间 |
| `confirm_plan` | 确认意见；确认或退回 |
| `submit_analysis` | 初步排查、根因、分析报告、附件 |
| `pass_review` | 验证状态、验证结论、质量评审结果 |
| `register_defect` | 缺陷 ID、SVN 路径 |
| `return` | 退回原因必填，目标由当前节点固定决定 |
| `resubmit` | 展示被退回原因，修改后重新提交 |
| `cancel` | 撤销原因必填 |

共同要求：

- 请求中携带详情返回的 `state_version`。
- 提交中禁用按钮，防止重复点击。
- 成功后重新获取详情和列表缓存。
- 后端字段错误显示在对应表单项。
- `403` 提示权限已变化并刷新页面。
- `409` 提示数据已更新并刷新详情。

### FE-10 流程时间线

改造或替换 `StateLogTimeline.vue`：

- 按 POC 状态显示中文名称。
- 展示动作、操作人、所属角色、时间、意见、前后状态。
- 退回记录使用醒目样式，但不能改写原始状态含义。
- 隐藏管理员的业务角色标签；如果管理员代操作，展示“系统管理员代操作”。
- 不再展示创建者/部门对接人/处理人的旧快照名称。

## 7. 第五批：附件、跟踪和导出

### FE-11 附件

- 新建页支持上传现场照片和材料。
- 分析节点支持上传日志、录屏、Word/PDF/Excel/ZIP。
- 上传前显示格式和大小限制。
- 展示上传人、阶段、时间、文件大小。
- 通过鉴权 API 下载，不直接拼接服务器文件路径。

### FE-12 质量跟踪视图

第一阶段可复用列表页，通过 `quality` 角色默认筛选全部未闭环问题，不必新建复杂仪表盘。

增加：

- 临期和逾期标识。
- 计划完成时间排序。
- 导出“POC 问题跟踪表”按钮。
- 质量角色快捷筛选“待我评审”和“待我入库”。

## 8. 前端清理清单

全局搜索并移除页面展示和业务判断：

```text
agent
handler
dispatcher
客服/客服组
处理人/部门对接人
待受理/处理中/已处理/暂缓/已归档
回访/满意度
p1_urgent/p2_high/p3_normal/p4_enterprise
```

重点文件：

- `frontend/src/api/tickets.ts`
- `frontend/src/types/index.ts`
- `frontend/src/views/TicketCreateView.vue`
- `frontend/src/views/TicketDetailView.vue`
- `frontend/src/views/TicketListView.vue`
- `frontend/src/components/ticket/*`
- `frontend/src/components/common/StateTag.vue`
- `frontend/src/layouts/*`
- `frontend/src/stores/auth.ts`
- `frontend/src/views/admin/UsersView.vue`
- `frontend/src/mock/*`

允许保留技术层面的历史迁移说明，但用户可见界面不得出现旧角色或旧流程。

## 9. 前端验收场景

至少人工走通：

1. 售前保存草稿、继续编辑、提交审批。
2. 批准人只看到本人待审批问题，并可通过/驳回。
3. 专项小组确认问题并选择分系统负责人。
4. 非对应分系统人员看不到接收和填写计划按钮。
5. 分系统提交计划后，售前确认或退回。
6. 分系统提交分析验证和附件。
7. 质量选择四种验证状态之一并填写结论。
8. 未填缺陷 ID 或 SVN 路径时不能提交入库。
9. 完整闭环后页面只读。
10. 三条退回路径均能看到原因并重新提交。
11. 管理员可以代操作，但不会出现在业务角色选择器中。
12. 所有页面不出现旧角色、旧状态、旧优先级和回访文案。

执行：

```bash
cd frontend
npm run build
```

## 10. 前端交付检查

- `npm run build` 通过。
- 与后端 OpenAPI 字段和枚举一致。
- 不使用 `any` 绕过新增核心业务类型。
- 所有动作由 `allowed_actions` 驱动展示。
- 对 `400/403/409/422` 有明确提示。
- 提供主流程和三个退回路径的截图或录屏。
