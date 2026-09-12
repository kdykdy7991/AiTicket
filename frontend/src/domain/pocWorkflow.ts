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
  { value: 'pending_confirmation', label: '待问题确认', type: 'warning' },
  { value: 'pending_routing', label: '待流转', type: 'warning' },
  { value: 'pending_acceptance', label: '待分系统接收', type: 'warning' },
  { value: 'planning', label: '闭环计划制定中', type: 'primary' },
  { value: 'pending_plan_confirmation', label: '待计划确认', type: 'warning' },
  { value: 'processing', label: '分析验证中', type: 'primary' },
  { value: 'pending_quality_review', label: '待质量评审', type: 'warning' },
  { value: 'pending_defect_registration', label: '待缺陷入库', type: 'warning' },
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
  | 'confirm_problem'
  | 'route'
  | 'accept'
  | 'submit_plan'
  | 'confirm_plan'
  | 'submit_analysis'
  | 'pass_review'
  | 'register_defect'
  | 'return'
  | 'resubmit'
  | 'cancel'

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
  return state ? STATE_LABELS[state as PocState] || state : '—'
}

export function priorityLabel(priority?: string | null): string {
  return priority ? PRIORITY_LABELS[priority as PocPriority] || priority : '—'
}
