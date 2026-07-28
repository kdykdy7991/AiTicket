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

export type TicketChannel = 'web' | 'email' | 'phone' | 'wechat' | 'app'

export interface Ticket {
  id: number
  number: string | null
  state: TicketState
  priority: TicketPriority
  group: Group
  owner: User | null
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
  region: TicketRegion | null
  region_name: string | null
  category_l1: TicketCategory | null
  category_l2: TicketCategory | null
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
  // 催办
  urged_at: string | null
  urged_by: User | null
  // 追加信息
  has_addition: boolean
  // 退回历史
  has_returned: boolean
  is_draft: boolean
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
  type?: 'reply' | 'addition' | 'reminder' | 'return'
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

export interface TicketFilters {
  state_id?: number | null
  priority_id?: number | null
  group_id?: number | null
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
  resolved?: boolean
  resolution?: string
}

export interface ArticleCreatePayload {
  type: 'reply' | 'addition' | 'reminder'
  body: string
  content_type?: 'text/plain' | 'text/html'
  article_type?: 'note' | 'email' | 'web'
  append_reason?: string
  attachments?: File[]
}
