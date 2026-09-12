import type { PocPriority, PocState, TicketAction, VerificationStatus } from '@/domain/pocWorkflow'

export interface PocUserRef {
  id: number
  name: string
  role?: string
}

export interface PocAttachment {
  id: number
  ticket_id: number | null
  original_filename: string
  content_type: string
  size: number
  stage: string | null
  uploader_id: number | null
  uploader_name: string | null
  download_url: string
  created_at: string
}

/** 附件展示项：服务端附件或本地待上传文件，统一给附件列表组件渲染 */
export interface PocAttachmentItem {
  /** 列表渲染 key；图片预览/下载的对象 URL 按 File 身份或附件 id 缓存，不依赖此值 */
  key: string
  name: string
  size?: number
  /** 附加说明，例如「待上传」「已上传 · 待审批」 */
  hint?: string
  /** 已提交到服务端的附件：预览/下载时按需带鉴权拉取 */
  attachment?: PocAttachment
  /** 本地待上传文件：直接用 File 生成对象 URL */
  file?: File
  /** 是否展示「移除」按钮 */
  removable?: boolean
}

export interface PocStateLog {
  id: number
  action: string | null
  from_state: string | null
  to_state: string
  operator_id: number | null
  operator_name: string | null
  operator_roles: string[]
  comment: string | null
  payload: Record<string, unknown> | null
  responsible_role_snapshot: string | null
  responsible_user_id_snapshot: number | null
  responsible_user_name_snapshot: string | null
  state_version: number | null
  created_at: string
}

export interface PocTicketBrief {
  id: number
  number: string | null
  title: string | null
  proposer: string | null
  proposer_department: string | null
  product_line: string | null
  customer_name: string | null
  priority: PocPriority
  problem_type: string | null
  state: PocState
  state_version: number
  is_draft: boolean
  return_to_state: PocState | null
  current_responsible_role: string | null
  current_responsible_user_id: number | null
  current_responsible_user_name: string | null
  creator_id: number | null
  creator_name: string | null
  creator_department: string | null
  approver_id: number | null
  approver_name: string | null
  skill_group_id: number | null
  skill_group_name: string | null
  subsystem_owner_id: number | null
  subsystem_owner_name: string | null
  planned_completion_at: string | null
  actual_completion_at: string | null
  is_overdue: boolean
  verification_status: VerificationStatus | null
  defect_id: string | null
  created_at: string
  updated_at: string
}

export interface PocTicketDetail extends PocTicketBrief {
  closure_requirement: string | null
  occurred_at: string | null
  location: string | null
  longitude: number | null
  latitude: number | null
  device_info: string | null
  description: string | null
  confirmation_comment: string | null
  acceptance_comment: string | null
  temporary_measure: string | null
  long_term_measure: string | null
  plan_confirmation_comment: string | null
  initial_investigation: string | null
  root_cause: string | null
  analysis_report: string | null
  verification_conclusion: string | null
  quality_review_result: string | null
  defect_repository_path: string | null
  defect_registered_at: string | null
  defect_registered_by_id: number | null
  defect_registered_by_name: string | null
  closed_at: string | null
  allowed_actions: TicketAction[]
  attachments: PocAttachment[]
  state_logs: PocStateLog[]
}

export interface PocTicketForm {
  title: string
  proposer: string
  proposer_department: string
  product_line: string
  customer_name: string
  priority: PocPriority
  problem_type: string
  closure_requirement: string
  occurred_at: string
  location: string
  longitude: number | null
  latitude: number | null
  device_info: string
  description: string
  approver_id: number | null
}

export interface PocTicketFilters {
  state?: PocState[]
  priority?: PocPriority[]
  skill_group_id?: number
  responsible_user_id?: number
  verification_status?: VerificationStatus
  is_overdue?: boolean
  keyword?: string
  date_from?: string
  date_to?: string
  sort?: 'updated_desc' | 'created_desc' | 'planned_asc'
}

export interface PocTicketActionRequest {
  action: TicketAction
  comment?: string | null
  payload?: Record<string, unknown>
  expected_version: number
}

export interface PocPaginatedResponse<T> {
  data: T[]
  pagination: { page: number; page_size: number; total: number; total_pages: number }
}
