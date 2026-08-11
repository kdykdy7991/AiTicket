import api from './index'
import type {
  TicketFilters, TicketCreatePayload, TicketUpdatePayload,
  ArticleCreatePayload, Ticket, TicketDetail, Article, PaginatedResponse,
  TicketStateLog, DuplicateCheckPayload, DuplicateCheckResult,
  BatchUpdatePayload, ExportPayload,
} from '@/types'

interface ListResponse<T> {
  data: T[]
  pagination: { page: number; page_size: number; total: number; total_pages: number }
}

// ── 枚举映射表（后端字符串 ⇄ 前端展示对象 / 筛选 ID）─────────

/** state 字符串 → 前端 StateTag 期望的对象 { name, state_type } */
const STATE_MAP: Record<string, { name: string; state_type: string }> = {
  pending: { name: '待受理', state_type: 'new' },
  open: { name: '处理中', state_type: 'open' },
  resolved: { name: '已处理', state_type: 'pending' },
  on_hold: { name: '暂缓处理', state_type: 'pending' },
  archived: { name: '已归档', state_type: 'closed' },
  returned: { name: '待受理', state_type: 'new' },
  cancelled: { name: '已撤销', state_type: 'closed' },
}

/** priority 字符串 → 前端 PriorityIcon 期望的对象 { name, ui_color } */
const PRIORITY_MAP: Record<string, { name: string; ui_color: string }> = {
  p1_urgent: { name: 'P1 特别重大事件', ui_color: '#F56C6C' },
  p2_high: { name: 'P2 重大事件', ui_color: '#E6A23C' },
  p3_normal: { name: 'P3 较大事件', ui_color: '#409EFF' },
  p4_enterprise: { name: 'P4 一般事件', ui_color: '#67C23A' },
}

/** 筛选下拉的 state_id（数字）→ 后端 state 字符串 */
export const STATE_ID_TO_KEY: Record<number, string> = {
  1: 'pending', 2: 'open', 3: 'resolved', 4: 'on_hold',
  5: 'archived', 6: 'returned', 7: 'cancelled',
}

/** 筛选下拉的 priority_id（数字）→ 后端 priority 字符串 */
export const PRIORITY_ID_TO_KEY: Record<number, string> = {
  1: 'p1_urgent', 2: 'p2_high', 3: 'p3_normal', 4: 'p4_enterprise',
}

/** 判断是否为退回/回退类流转（目标状态比源状态更靠前） */
function isReturnTransition(fromState: string | undefined | null, toState: string | undefined | null): boolean {
  if (!fromState || !toState) return false
  // 按工单流程顺序定义状态权重：越靠前数值越小
  const order: Record<string, number> = {
    returned: 0,
    pending: 1,
    open: 2,
    on_hold: 2.5,
    resolved: 3,
    archived: 4,
    cancelled: 4,
  }
  const fromOrder = order[fromState]
  const toOrder = order[toState]
  if (fromOrder == null || toOrder == null) return false
  // 目标状态权重小于源状态权重，即回退
  return toOrder < fromOrder
}

/** 后端状态日志数组 → 前端 StateLogTimeline 期望的结构
 *  后端每条日志：{ from_state, to_state, operator_id, operator_name, reason, duration_minutes, created_at }
 *  组件期望：{ from_state, to_state, changed_by, entered_at, left_at, duration_seconds }
 *  - entered_at = 本条日志 created_at（进入 to_state 的时间）
 *  - left_at    = 下一条日志的 created_at（离开 to_state 的时间），最后一条为 null
 *  - duration_seconds = duration_minutes*60，或用 entered_at/left_at 推算
 */
function adaptStateLogs(logs: any[]): any[] {
  if (!logs || logs.length === 0) return []
  const out = logs.map((log, i) => {
    const next = logs[i + 1]
    const enteredAt = log.created_at
    const leftAt = next ? next.created_at : null
    // duration_seconds：优先用后端的 duration_minutes，否则用 entered/left 推算
    let durationSeconds: number | null = null
    if (log.duration_minutes != null) {
      durationSeconds = log.duration_minutes * 60
    } else if (leftAt && enteredAt) {
      durationSeconds = Math.floor((new Date(leftAt).getTime() - new Date(enteredAt).getTime()) / 1000)
    }
    const fromKey = log.from_state || undefined
    const toKey = log.to_state
    return {
      id: log.id,
      from_state: fromKey ? stateLogStrToObj(fromKey) : null,
      from_state_key: fromKey,
      to_state: stateLogStrToObj(toKey),
      to_state_key: toKey,
      changed_by: log.operator_id ? { id: log.operator_id, firstname: log.operator_name || '未知', lastname: '' } : null,
      entered_at: enteredAt,
      left_at: leftAt,
      duration_seconds: durationSeconds,
      reason: log.reason,
      is_return: isReturnTransition(fromKey, toKey),
      // 人员快照：写入 state_log 那一刻工单上的创建者/对接人/处理人
      creator_id_snapshot: log.creator_id_snapshot ?? null,
      creator_name_snapshot: log.creator_name_snapshot ?? null,
      dispatcher_id_snapshot: log.dispatcher_id_snapshot ?? null,
      dispatcher_name_snapshot: log.dispatcher_name_snapshot ?? null,
      owner_id_snapshot: log.owner_id_snapshot ?? null,
      owner_name_snapshot: log.owner_name_snapshot ?? null,
    }
  })
  return out
}

/** 时间线日志专用：state 字符串 → 状态对象
 *  与 stateStrToObj 的区别：returned 显示"退回"（日志记录的是退回动作） */
function stateLogStrToObj(key: string): any {
  const map: Record<string, { name: string; state_type: string }> = {
    pending: { name: '待受理', state_type: 'new' },
    open: { name: '处理中', state_type: 'open' },
    resolved: { name: '已处理', state_type: 'pending' },
    on_hold: { name: '暂缓处理', state_type: 'pending' },
    archived: { name: '已归档', state_type: 'closed' },
    returned: { name: '退回', state_type: 'open' },
    cancelled: { name: '已撤销', state_type: 'closed' },
  }
  return map[key] || { name: key, state_type: 'open' }
}

/** state 字符串 → StateTag 组件期望的对象（列表/详情用） */
function stateStrToObj(key: string): any {
  const map: Record<string, { name: string; state_type: string }> = {
    pending: { name: '待受理', state_type: 'new' },
    open: { name: '处理中', state_type: 'open' },
    resolved: { name: '已处理', state_type: 'pending' },
    on_hold: { name: '暂缓处理', state_type: 'pending' },
    archived: { name: '已归档', state_type: 'closed' },
    returned: { name: '待受理', state_type: 'new' },
    cancelled: { name: '已撤销', state_type: 'closed' },
  }
  return map[key] || { name: key, state_type: 'open' }
}

/** 后端 article 字段映射到前端 ArticleTimeline 期望的结构 */
function adaptArticle(a: any): any {
  // type: reply/addition/reminder
  // sender_type：后端没有此字段，根据 type 推断（客服回复/note/追加/催办都算 agent）
  const senderType = 'agent'
  return {
    ...a,
    // 组件用 origin_by 显示头像和名字
    origin_by: {
      id: a.sender_id,
      firstname: a.sender_name || '未知',
      lastname: '',
    },
    sender_type: a.sender_type || senderType,
    content_type: a.content_type || 'text/plain',
    state_key: a.state_key || undefined,
    attachments: a.attachments || [],
    // 保留原始字段
  }
}

/** 后端工单字段映射到前端 Ticket 类型（保持组件兼容） */
function adaptTicket(t: any): any {
  const stateObj = STATE_MAP[t.state] || { name: t.state, state_type: 'open' }
  const priorityObj = PRIORITY_MAP[t.priority] || { name: t.priority, ui_color: '#909399' }
  // SLA 超时：解决超时
  const slaBreached = !!t.sla_solution_breached
  return {
    ...t,
    // state / priority 转成组件期望的对象，同时保留原始字符串
    state: { ...stateObj, name: stateObj.name, state_type: stateObj.state_type, id: 0 },
    priority: { ...priorityObj, id: 0 },
    state_key: t.state,
    priority_key: t.priority,
    // 关联对象
    owner: t.owner_id ? { id: t.owner_id, firstname: t.owner_name, lastname: '' } : null,
    dispatcher: t.dispatcher_id ? { id: t.dispatcher_id, firstname: t.dispatcher_name, lastname: '' } : null,
    returned_to_user: t.returned_to_user_id ? { id: t.returned_to_user_id, firstname: t.returned_to_user_name, lastname: '' } : null,
    group: t.group_id ? { id: t.group_id, name: t.group_name } : null,
    skill_group: t.skill_group_id ? { id: t.skill_group_id, name: t.skill_group_name } : null,
    category: t.category_id ? { id: t.category_id, name: t.category_name } : null,
    creator: t.creator_id ? { id: t.creator_id, firstname: t.creator_name, lastname: '' } : null,
    // 客户对象（侧边栏用 ticket.customer 显示头像+名字）
    customer: { id: 0, firstname: t.customer_name || '未知', lastname: '', name: t.customer_name },
    // 联系人：后端无单独 contact_name，用 customer_name 兜底
    contact_name: t.contact_name || t.customer_name || null,
    contact_phone: t.contact_phone || null,
    // 组织：后端无，用所属公司兜底
    organization: t.customer_company ? { id: 0, name: t.customer_company, active: true } : null,
    // 分类：后端返回 category_l1/category_l2，兼容旧数据
    category_l1: t.category_l1_id ? { id: t.category_l1_id, name: t.category_l1_name } : null,
    category_l2: t.category_l2_id ? { id: t.category_l2_id, name: t.category_l2_name } : null,
    // 重投关联：后端 linked_ticket_id，无 number，仅放 id
    duplicate_of: t.linked_ticket_id ? { id: t.linked_ticket_id, number: '' } : null,
    // 首受人：后端 first_owner_id，无 name
    first_owner: t.first_owner_id ? { id: t.first_owner_id, firstname: '', lastname: '' } : null,
    // SLA 相关：合成组件期望的字段
    sla_breached: slaBreached,
    escalation_at: t.solution_deadline || null,
    close_at: t.closed_at || null,
    article_count: t.article_count ?? 0,
    // 催办
    urged_at: t.urged_at || null,
    urged_by: t.urged_by_id ? { id: t.urged_by_id, firstname: t.urged_by_name || '未知', lastname: '' } : null,
    // 终态操作人：执行了 archived / cancelled 流转的人
    archived_by_id: t.archived_by_id ?? null,
    archived_by_name: t.archived_by_name ?? null,
    cancelled_by_id: t.cancelled_by_id ?? null,
    cancelled_by_name: t.cancelled_by_name ?? null,
  }
}

function buildListParams(filters?: TicketFilters, page = 1, pageSize = 20) {
  const params: Record<string, any> = { page, page_size: pageSize }
  if (!filters) return params
  const f = filters as any
  if (f.state_id) params.state = STATE_ID_TO_KEY[f.state_id]
  if (f.priority_id) params.priority = PRIORITY_ID_TO_KEY[f.priority_id]
  if (f.owner_id) params.owner_id = f.owner_id
  if (f.creator_id) params.creator_id = f.creator_id
  if (f.group_id) params.group_id = f.group_id
  if (f.skill_group_id) params.skill_group_id = f.skill_group_id
  if (f.category_id) params.category_id = f.category_id
  if (f.category_l2_id) params.category_id = f.category_l2_id
  if (f.customer_type) params.customer_type = f.customer_type
  if (f.keyword) params.keyword = f.keyword
  if (f.is_duplicate !== undefined) params.is_duplicate = f.is_duplicate
  if (f.is_callbacked !== undefined) params.is_callbacked = f.is_callbacked
  if (f.is_overdue) params.is_overdue = true
  if (f.date_from) params.date_from = f.date_from
  if (f.date_to) params.date_to = f.date_to
  return params
}

/** 把创建表单的旧 schema 字段映射到后端 TicketCreate */
function buildCreatePayload(data: any): Record<string, any> {
  return {
    description: data.article?.body || data.body || '',
    priority: PRIORITY_ID_TO_KEY[data.priority_id] || 'p4_enterprise',
    channel: data.channel || 'phone',
    customer_type: data.customer_type || 'personal',
    customer_name: data.contact_name || data.customer_name || null,
    customer_phone: data.customer_phone,
    customer_phone_type: data.customer_phone_type || undefined,
    contact_phone: data.contact_phone || undefined,
    customer_company: data.customer_company || undefined,
    device_sn: data.device_sn || undefined,
    region_name: data.region_name || undefined,
    category_id: data.category_l2_id || data.category_l1_id || data.category_id || undefined,
    group_id: data.group_id || undefined,
    skill_group_id: data.skill_group_id || undefined,
    dispatcher_id: data.dispatcher_id || undefined,  // 部门对接人（建单必填）
    is_duplicate: !!data.is_duplicate,
    duplicate_reason: data.is_duplicate ? (data.duplicate_reason || undefined) : undefined,
    linked_ticket_id: data.duplicate_of_id || undefined,
  }
}

export const ticketApi = {
  async list(filters?: TicketFilters, page?: number, perPage?: number): Promise<PaginatedResponse<Ticket>> {
    const res: ListResponse<any> = await api.get('/tickets', { params: buildListParams(filters, page, perPage) })
    return {
      data: res.data.map(adaptTicket),
      pagination: {
        page: res.pagination.page,
        per_page: res.pagination.page_size,
        total: res.pagination.total,
        total_pages: res.pagination.total_pages,
      },
    } as any
  },

  async get(id: number): Promise<TicketDetail> {
    const t: any = await api.get(`/tickets/${id}`)
    const [articles, stateLogs] = await Promise.all([
      api.get<unknown, { data: any[] }>(`/tickets/${id}/articles`),
      api.get<unknown, { data: any[] }>(`/tickets/${id}/state-logs`),
    ])
    return {
      ...adaptTicket(t),
      articles: articles.data.map(adaptArticle),
      state_logs: adaptStateLogs(stateLogs.data),
      links: [],
    } as any
  },

  async create(data: TicketCreatePayload): Promise<Ticket> {
    const res: any = await api.post('/tickets', buildCreatePayload(data))
    return adaptTicket(res.data)
  },

  async update(id: number, data: TicketUpdatePayload): Promise<Ticket> {
    const res: any = await api.patch(`/tickets/${id}`, data)
    return adaptTicket(res)
  },

  async checkDuplicate(data: DuplicateCheckPayload): Promise<DuplicateCheckResult> {
    const res: ListResponse<any> = await api.get('/tickets', {
      params: {
        keyword: data.customer_phone,
        page: 1, page_size: 5,
      },
    })
    return {
      has_duplicates: res.data.length > 0,
      candidates: res.data.map((t: any) => ({
        id: t.id, number: t.number,
        state: stateStrToObj(t.state),  // StateTag 需要对象
        created_at: t.created_at, customer_phone: t.customer_phone,
        device_sn: t.device_sn || null,
      })),
    } as any
  },

  async getStateLogs(ticketId: number): Promise<TicketStateLog[]> {
    const res: { data: any[] } = await api.get(`/tickets/${ticketId}/state-logs`)
    return adaptStateLogs(res.data) as any
  },

  async batchUpdate(data: BatchUpdatePayload): Promise<{ updated: number }> {
    const res: any = await api.post('/tickets/batch-update', data)
    return res.data
  },

  // 导出 CSV：调后端真实接口，返回 blob 供下载
  async export(params: { filters?: TicketFilters; columns?: string[] }): Promise<Blob> {
    const queryParams: Record<string, any> = buildListParams(params.filters, 1, 10000)
    delete queryParams._t
    // 前端列 key → 后端列组：base/customer/category/workflow
    if (params.columns?.length) {
      const colGroups = new Set<string>()
      for (const key of params.columns) {
        if (['number', 'created_at', 'closed_at', 'close_duration', 'state', 'channel'].includes(key)) colGroups.add('base')
        if (['customer_name', 'customer_company', 'customer_phone', 'contact_phone', 'device_sn', 'region_name'].includes(key)) colGroups.add('customer')
        if (['category_l1', 'category_l2', 'symptom', 'priority'].includes(key)) colGroups.add('category')
        if (['creator_name', 'dispatcher_name', 'owner_name', 'resolution', 'is_callbacked', 'callback_time', 'satisfaction', 'archive_notes', 'sla_breached'].includes(key)) colGroups.add('workflow')
      }
      queryParams.columns = [...colGroups].join(',')
    }
    // blob 响应不走响应拦截器的 data 提取
    return await api.get('/tickets/export', { params: queryParams, responseType: 'blob' }) as unknown as Blob
  },
}

export const draftApi = {
  async list() {
    const res: any = await api.get('/tickets/drafts')
    return res
  },

  async save(payload: Record<string, any>) {
    const body = { ...buildCreatePayload(payload), is_draft: true }
    console.log('[draftApi.save] payload:', JSON.stringify(body, null, 2))
    const res: any = await api.post('/tickets', body)
    console.log('[draftApi.save] response:', JSON.stringify(res, null, 2))
    return adaptTicket(res.data)
  },

  async update(draftId: number, payload: Record<string, any>) {
    const body = { ...buildCreatePayload(payload), is_draft: true }
    const res: any = await api.patch(`/tickets/drafts/${draftId}`, body)
    return adaptTicket(res.data)
  },

  async submit(draftId: number): Promise<Ticket> {
    const res: any = await api.post(`/tickets/drafts/${draftId}/submit`)
    return adaptTicket(res.data)
  },

  async delete(draftId: number) {
    await api.delete(`/tickets/drafts/${draftId}`)
  },
}

export const articleApi = {
  async create(ticketId: number, data: ArticleCreatePayload): Promise<Article> {
    // 后端统一使用 multipart/form-data 接收，始终用 FormData
    const payload = new FormData()
    payload.append('type', data.type)
    payload.append('body', data.body)
    if (data.append_reason) payload.append('append_reason', data.append_reason)
    if (data.attachments) {
      for (const file of data.attachments) {
        payload.append('attachments', file, file.name)
      }
    }

    // Axios 会自动为 FormData 设置正确的 Content-Type（含 boundary）
    const res: any = await api.post(`/tickets/${ticketId}/articles`, payload)
    return adaptArticle(res.data)
  },
}
