export interface Role {
  id: number
  name: 'admin' | 'agent' | 'customer'
  permissions: string[]
}

export interface Organization {
  id: number
  name: string
  domain?: string
  active: boolean
}

export interface Group {
  id: number
  name: string
  parent_id?: number | null
  active: boolean
}

export interface User {
  id: number
  email: string
  firstname: string
  lastname: string
  role: Role
  groups?: Group[]
  organization?: Organization | null
  active: boolean
}

// —— 客服组端到端工单需求补充（P7）新增类型 ——

export type CustomerType = 'personal' | 'enterprise'

export interface TicketCategory {
  id: number
  name: string
  parent_id: number | null
  sort_order: number
  active: boolean
  /** 建单表单可选的"判断终点"（V0.21 §4）；容器/分诊侧节点为 false */
  create_selectable?: boolean
  /** 通道：chain=按分派链自动落位；instant=建单即办结；manual=无链人工分派；none=容器 */
  channel?: string
}

export interface Region {
  id: number
  name: string
  parent_id: number | null
  level: 'province' | 'city' | 'district' | 'station'
}

export interface TicketRegion {
  province?: string
  city?: string
  district?: string
  station?: string
}

export interface TicketStateLog {
  id: number
  ticket_id: number
  from_state: TicketState | null
  from_state_key?: string
  to_state: TicketState
  to_state_key?: string
  entered_at: string
  left_at: string | null
  duration_seconds: number | null
  changed_by: User | null
  reason?: string | null
  /** 是否为退回/回退类流转 */
  is_return?: boolean
  /** Flow Log 动作类型（后端 state_logs 唯一事实来源）：dispatch/refine/transfer/... */
  action_type?: string | null
  operator_name?: string | null
  /** 写入 state_log 那一刻工单上的人员快照（创建者/对接人/处理人）。
   *  旧数据可能为空，为空时前端回退到工单当前值。 */
  creator_id_snapshot?: number | null
  creator_name_snapshot?: string | null
  dispatcher_id_snapshot?: number | null
  dispatcher_name_snapshot?: string | null
  owner_id_snapshot?: number | null
  owner_name_snapshot?: string | null
}

export interface DuplicateTicket {
  id: number
  number: string
  state: TicketState
  created_at: string
  customer_phone: string
  device_sn: string | null
}

export interface DuplicateCheckPayload {
  customer_phone: string
  device_sn?: string
  category_l1_id: number
}

export interface DuplicateCheckResult {
  has_duplicates: boolean
  candidates: DuplicateTicket[]
}

export interface ExportColumn {
  key: string
  label: string
  group: 'base' | 'customer' | 'category' | 'workflow'
}

export interface ExportPayload {
  format: 'csv' | 'xlsx'
  filters: TicketFilters
  columns: ExportColumn[]
}

// —— 结束 P7 新增 ——

export interface TicketState {
  id: number
  name: string
  state_type: 'new' | 'open' | 'pending' | 'closed' | 'merged'
}

export interface TicketPriority {
  id: number
  name: string
  ui_color: string
  ui_icon?: string
  customer_type_restriction?: CustomerType | null
}

export type TicketChannel = 'web' | 'email' | 'phone' | 'wechat' | 'app' | 'internal'

/** V0.86：后端生成的状态动作元数据（详情接口 allowed_actions，前端按钮唯一渲染依据） */
export interface AllowedAction {
  action: string             // dispatch/return/cancel/resolve/hold/resume/reopen/resubmit/archive
  target_state: string       // 执行后的目标状态（已含后端业务约束改写）
  requires_reason: boolean   // 必须填写原因
  requires_owner: boolean    // 前置要求：分派时先选择处理人
  label: string              // 中文按钮文案
}

export interface Ticket {
  id: number
  number: string | null
  state: TicketState
  priority: TicketPriority
  group: Group
  owner: User | null
  /** 所属部门（后端优先返回工单当前责任部门，其次其任一所属部门） */
  owner_department: string | null
  customer: User
  organization: Organization | null
  channel: TicketChannel
  escalation_at: string | null
  close_at: string | null
  article_count: number
  created_at: string
  updated_at: string
  // —— P7 客服组需求补充新增字段 ——
  customer_type: CustomerType
  customer_phone: string
  device_sn: string | null
  contact_name: string | null
  contact_phone: string | null
  industry?: string | null
  customer_email?: string | null
  satellite_number?: string | null
  is_opportunity?: boolean | null
  expected_result?: string | null
  fault_occurred_at?: string | null
  fault_recurrence?: string | null
  fault_location?: string | null
  is_batch_fault?: boolean | null
  region: TicketRegion | null
  region_name: string | null
  category_l1: TicketCategory | null
  category_l2: TicketCategory | null
  /** 完整分类路径 root→leaf，如 "客户服务 / 业务保障 / 星座大系统 / 核心网系统" */
  category_path: string | null
  /** 问题判断组（按判断先后排序）；空数组 = 客服组建单时已完成判断 */
  judgement_departments: string[]
  /** 流转节点（处理链中间环节，线性推进）；空数组 = 无需流转 */
  transit_departments: string[]
  /** 问题处理部门（处理链最后一环）；判断节点未分诊时为 null */
  handling_department: string | null
  symptom: string | null
  is_duplicate: boolean
  duplicate_reason: string | null
  duplicate_of: { id: number; number: string } | null
  first_owner: User | null
  skill_group: Group | null
  sla_breached: boolean
  resolved: boolean
  resolution: string | null
  archive_notes: string | null
  is_callbacked: boolean
  callback_required?: boolean  // 是否需要回访（false=无需回访）；仅详情接口返回
  callback_details?: string | null  // 回访详情/不满意原因（V0.86 贯通）
  satisfaction?: string | null      // 满意度：satisfied/average/dissatisfied/unrated
  customer_satisfaction_score?: number | null  // V0.15 独立的 1～10 分评分
  customer_recognized?: boolean | null
  closure_result?: string | null
  unsatisfied_reason?: string | null  // 不认可或历史四档不满意时填写
  hold_until?: string | null  // 后端详情的 ISO 时间；未暂缓时为 null
  // 追加信息
  has_addition: boolean
  // 退回历史
  has_returned: boolean
  is_draft: boolean
  // 终态操作人：执行了 resolved→archived 或 *→cancelled 流转的人
  archived_by_id?: number | null
  archived_by_name?: string | null
  cancelled_by_id?: number | null
  cancelled_by_name?: string | null
  // —— V0.86 后端动作/能力元数据（仅详情接口返回；前端不再自算业务规则）——
  allowed_actions?: AllowedAction[]
  is_terminal?: boolean
  can_reply?: boolean
  can_addition?: boolean

  // —— V0.21 分派链快照与分诊能力位（仅详情接口返回）——
  dispatch_chain_steps?: { order: number; department_code: string; stage?: 'judgement' | 'phone_feedback' }[] | null
  dispatch_step_index?: number | null
  can_refine?: boolean
  refine_options?: { id: number; name: string; level?: number; next_department?: string | null }[]
  refine_denied_reason?: string | null
  /** 后端从当前工单事实和该用户权限即时推导；前端不可提交 node_type。 */
  node_context?: {
    ticket_id: number
    node_type: 'intake' | 'triage' | 'processing' | 'phone_feedback' | 'closure' | 'sales_opportunity' | null
    category_id: number | null
    department_id: number | null
    department_code: string | null
    dispatch_step_index: number | null
    dispatch_stage: string | null
    operator_id: number
    owner_id: number | null
    dispatcher_id: number | null
    allowed_actions: AllowedAction[]
  } | null
}

export interface ArticleAttachment {
  id: number
  filename: string
  original_filename: string
  content_type: string
  size: number
  url: string
  created_at: string
}

export interface Article {
  id: number
  ticket_id: number
  origin_by: User
  sender_type: 'agent' | 'customer' | 'system'
  article_type: 'note' | 'email' | 'web' | 'phone'
  type?: 'note' | 'reply' | 'addition' | 'return'
  subject?: string
  body: string
  content_type: 'text/plain' | 'text/html'
  state_key?: string
  created_at: string
  // —— P7 追加记录字段 ——
  is_addition: boolean
  append_reason: string | null
  attachments: ArticleAttachment[]
}

export interface TicketDetail extends Ticket {
  /** 原始建单字段在详情适配器中保留，供草稿回填。 */
  customer_name?: string | null
  customer_company?: string | null
  skill_group_id?: number | null
  priority_key?: string
  root_cause?: string | null
  solution?: string | null
  node_submissions?: Array<{
    id: number
    node_type: string
    form_code?: string | null
    form_name?: string | null
    operator_name?: string | null
    form_version: number
    data: Record<string, unknown>
    article_id: number | null
    article_body: string | null
    attachments: Array<{ id: number; filename: string; url: string }>
    field_snapshot: Array<{ key: string; label: string; storage_type: string; storage_key?: string; submitted_value?: unknown }>
  }>
  current_form?: {
    code: string
    name: string
    form_definition_id: number
    version: number
    fields: Array<{
      field_key: string
      label: string
      field_type: string
      sort_order: number
      required: boolean
      visible: boolean
      options: string[]
      value: string | number | boolean | null
      option_labels?: Record<string, string>
      boolean_labels?: { true?: string; false?: string }
      min?: number | null
      max?: number | null
      visibility_condition?: { field_equals?: { field: string; value: unknown } } | null
      required_condition?: { field_equals?: { field: string; value: unknown } } | null
    }>
  } | null
  creator_username?: string | null
  creator_group_name?: string | null
  articles: Article[]
  links: TicketLink[]
  state_logs?: TicketStateLog[]
}

export interface TicketLink {
  id: number
  source_ticket: { id: number; number: string; title: string }
  target_ticket: { id: number; number: string; title: string }
  link_type: 'parent' | 'child' | 'related'
}

export interface Overview {
  id: number
  name: string
  conditions: Record<string, unknown>
  order_by: string
  order_direction: 'asc' | 'desc'
  prio: number
  active: boolean
}

export interface GroupAvgResolution {
  group_id: number
  group_name: string
  minutes: number
}

export interface CategoryCount {
  category_l1: string
  count: number
}

export interface DashboardStats {
  tickets_by_state: Array<{ state: string; count: number }>
  tickets_by_priority: Array<{ priority: string; count: number }>
  escalated_count: number
  avg_resolution_minutes: number | null
  created_today: number
  resolved_today: number
  // —— P7 新增 ——
  in_progress: number
  sla_breach_rate: number
  first_contact_resolution_rate: number
  avg_resolution_per_group: GroupAvgResolution[]
  tickets_by_category: CategoryCount[]
}

export interface Pagination {
  page: number
  per_page: number
  total: number
  total_pages: number
}

export interface PaginatedResponse<T> {
  data: T[]
  pagination: Pagination
}

/** 日期区间筛选值，from / to 为 YYYY-MM-DD，一端为空表示开放区间 */
export interface DateRangeValue {
  from: string | null
  to: string | null
}

export interface TicketFilters {
  state_id?: number | null
  priority_id?: number | null
  group_id?: number | null
  creator_id?: number | null
  owner_id?: number | null
  customer_type?: CustomerType | null
  category_l1_id?: number | null
  category_l2_id?: number | null
  is_duplicate?: boolean | null
  is_callbacked?: boolean | null
  resolved?: boolean | null
  date_from?: string | null
  date_to?: string | null
  escalated?: boolean | null
  is_overdue?: boolean | null
  keyword?: string
}

export interface BatchUpdatePayload {
  ticket_ids: number[]
  state_id?: number
  priority_id?: number
  owner_id?: number | null
  group_id?: number
}

export interface LoginPayload {
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface TicketCreatePayload {
  group_id: number
  priority_id: number
  article: {
    body: string
    content_type: 'text/plain' | 'text/html'
  }
  // —— P7 新增 ——
  customer_type: CustomerType
  customer_phone: string
  customer_phone_type?: 'mobile' | 'landline' | null
  device_sn?: string | null
  contact_name?: string | null
  contact_phone?: string | null
  customer_company?: string | null
  region_name?: string | null
  category_l1_id?: number | null
  category_l2_id?: number | null
  is_duplicate?: boolean
  duplicate_reason?: string | null
  duplicate_of_id?: number | null
  channel: TicketChannel
  skill_group_id?: number | null
  dispatcher_id?: number | null
  is_draft?: boolean
}

export interface TicketDraftPayload {
  group_id?: number | null
  priority_id?: number | null
  customer_type: CustomerType
  customer_phone: string
  contact_name?: string | null
  contact_phone?: string | null
  customer_company?: string | null
  device_sn?: string | null
  region_name?: string | null
  category_l1_id?: number | null
  category_l2_id?: number | null
  channel: TicketChannel
  skill_group_id?: number | null
  dispatcher_id?: number | null
  body?: string
}

export interface TicketUpdatePayload {
  state?: string
  category_id?: number
  state_id?: number
  priority?: string
  priority_id?: number
  owner_id?: number | null
  group_id?: number | null
  skill_group_id?: number | null
  dispatcher_id?: number | null
  reason?: string | null
  hold_until?: string | null
  callback_details?: string | null
  archive_notes?: string | null
  is_callbacked?: boolean | null
  callback_required?: boolean | null
  resolved?: boolean
  resolution?: string
}

export interface ArticleCreatePayload {
  type: 'reply' | 'addition'
  body: string
  content_type?: 'text/plain' | 'text/html'
  article_type?: 'note' | 'email' | 'web'
  append_reason?: string
  attachments?: File[]
}
