export const BUSINESS_ROLE_OPTIONS = [
  { value: 'presales', label: '售前' },
  { value: 'approver', label: '批准人' },
  { value: 'taskforce', label: '专项小组' },
  { value: 'subsystem', label: '分系统' },
  { value: 'quality', label: '质量' },
] as const

export const SYSTEM_ROLE_OPTIONS = [
  ...BUSINESS_ROLE_OPTIONS,
  { value: 'admin', label: '系统管理员' },
] as const

export type BusinessRole = typeof SYSTEM_ROLE_OPTIONS[number]['value']

export const ROLE_LABELS: Record<BusinessRole, string> = Object.fromEntries(
  SYSTEM_ROLE_OPTIONS.map(item => [item.value, item.label]),
) as Record<BusinessRole, string>

export const POC_STATE_OPTIONS = [
  { value: 'pending_approval', label: '待审批', type: 'warning' },
  { value: 'pending_routing', label: '待确认流转', type: 'warning' },
  { value: 'planning', label: '闭环计划制定', type: 'primary' },
  { value: 'pending_plan_confirmation', label: '待计划确认', type: 'warning' },
  { value: 'processing', label: '分析验证', type: 'primary' },
  { value: 'pending_quality_review', label: '待验证确认', type: 'warning' },
  { value: 'pending_final_approval', label: '待批准人复核', type: 'warning' },
  { value: 'closed', label: '已闭环', type: 'success' },
  { value: 'returned', label: '已退回', type: 'danger' },
  { value: 'cancelled', label: '已撤销', type: 'info' },
] as const

export type PocState = typeof POC_STATE_OPTIONS[number]['value']

export const STATE_LABELS: Record<PocState, string> = Object.fromEntries(
  POC_STATE_OPTIONS.map(item => [item.value, item.label]),
) as Record<PocState, string>

export const MAIN_FLOW_STATES: PocState[] = POC_STATE_OPTIONS
  .map(item => item.value)
  .filter(state => state !== 'returned' && state !== 'cancelled')

export const TERMINAL_STATES = new Set<PocState>(['closed', 'cancelled'])

export const POC_PRIORITY_OPTIONS = [
  { value: 'p0_blocker', label: 'P0 阻断', color: '#dc2626' },
  { value: 'p1_critical', label: 'P1 严重', color: '#ea580c' },
  { value: 'p2_normal', label: 'P2 一般', color: '#2563eb' },
  { value: 'p3_low', label: 'P3 低', color: '#64748b' },
] as const

export type PocPriority = typeof POC_PRIORITY_OPTIONS[number]['value']

export const PRIORITY_LABELS: Record<PocPriority, string> = Object.fromEntries(
  POC_PRIORITY_OPTIONS.map(item => [item.value, item.label]),
) as Record<PocPriority, string>

export const VERIFICATION_STATUS_OPTIONS = [
  { value: 'resolved', label: '已解决' },
  { value: 'temporarily_resolved', label: '临时解决' },
  { value: 'pending_reproduction', label: '待复现' },
  { value: 'unresolved', label: '未解决' },
] as const

export type VerificationStatus = typeof VERIFICATION_STATUS_OPTIONS[number]['value']

export type TicketAction =
  | 'approve'
  | 'reject'
  | 'route'
  | 'submit_plan'
  | 'confirm_plan'
  | 'submit_analysis'
  | 'pass_review'
  | 'approve_closure'
  | 'return'
  | 'resubmit'
  | 'cancel'

/** 动作展示文案；流程记录里的首条日志 action 为 null，表示提交审批 */
export const ACTION_LABELS: Record<TicketAction, string> = {
  approve: '审批通过',
  reject: '驳回',
  route: '确认并流转',
  submit_plan: '提交闭环计划',
  confirm_plan: '确认闭环计划',
  submit_analysis: '提交分析验证',
  pass_review: '通过质量评审',
  approve_closure: '批准闭环',
  return: '退回',
  resubmit: '重新提交',
  cancel: '撤销',
}

/** 流程合并前出现过的动作编码：不再产生，仅用于渲染历史日志 */
export const HISTORICAL_ACTION_LABELS: Record<string, string> = {
  confirm_problem: '确认问题（旧）',
  accept: '确认接收（旧）',
  register_defect: '登记缺陷并闭环（旧）',
}

/** 流程合并前出现过的状态编码：不再产生，仅用于渲染历史日志 */
export const HISTORICAL_STATE_LABELS: Record<string, string> = {
  pending_confirmation: '待问题确认（旧）',
  pending_acceptance: '待分系统接收（旧）',
  pending_defect_registration: '待缺陷入库（旧）',
}

export function actionLabel(action?: string | null): string {
  if (!action) return '提交审批'
  return ACTION_LABELS[action as TicketAction]
    || HISTORICAL_ACTION_LABELS[action]
    || action
}

/** 状态标签色（el-tag type / 流程记录状态胶囊共用） */
export function stateType(state?: string | null): string {
  return POC_STATE_OPTIONS.find(item => item.value === state)?.type || 'info'
}

export function roleLabel(role?: string | null): string {
  return role ? ROLE_LABELS[role as BusinessRole] || role : '—'
}

/** 多角色：把角色编码数组拼成展示文案 */
export function roleLabels(roles?: string[] | null): string {
  if (!roles?.length) return '—'
  return roles.map(role => roleLabel(role)).join('、')
}

/** 是否拥有其中任一角色 */
export function hasAnyRole(roles: string[] | undefined | null, ...expected: BusinessRole[]): boolean {
  if (!roles?.length) return false
  return expected.some(role => roles.includes(role))
}

export function stateLabel(state?: string | null): string {
  if (!state) return '—'
  return STATE_LABELS[state as PocState] || HISTORICAL_STATE_LABELS[state] || state
}

export function priorityLabel(priority?: string | null): string {
  return priority ? PRIORITY_LABELS[priority as PocPriority] || priority : '—'
}
