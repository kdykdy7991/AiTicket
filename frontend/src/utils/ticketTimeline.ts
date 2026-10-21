import type { TicketStateLog } from '@/types'

const actionNames: Record<string, string> = {
  create: '创建工单', instant_resolve: '即办结归档', dispatch: '分派处理人',
  refine: '问题判断', transfer: '转派下一部门', hold: '暂缓处理',
  resume: '恢复处理', return: '退回', reopen: '退回重开',
  resubmit: '重新提交', resolve: '提交处理结果', archive: '归档', cancel: '撤销',
}

const stateNames: Record<string, string> = {
  pending: '进入待受理', open: '进入处理中', resolved: '进入已处理',
  on_hold: '进入暂缓处理', returned: '进入已退回', archived: '归档',
  cancelled: '撤销', awaiting_callback: '进入待回访', callbacked: '回访完成',
}

export function timelineActionName(log: TicketStateLog, submissions: any[] = [], logs: TicketStateLog[] = []): string {
  const form = submissions.find(entry => entry.state_log_id === log.id)
  if (form?.form_code === 'after_sales_triage') return '初步判断依据'
  if (log.action_type === 'dispatch' && log.reason === '指派售后人员') return '指派售后人员'
  if (log.action_type === 'dispatch') {
    const previous = [...logs].filter(entry => entry.id < log.id).sort((a, b) => b.id - a.id)[0]
    if (previous?.action_type === 'transfer' && previous.reason?.includes('售后致电反馈')) {
      return '指派售后致电反馈人'
    }
  }
  if (log.action_type === 'transfer' && log.reason?.includes('售后致电反馈')) return '流转至售后致电反馈'
  return actionNames[log.action_type || ''] || stateNames[log.to_state_key || ''] || '状态变更'
}
