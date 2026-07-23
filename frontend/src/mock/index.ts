import type {
  LoginPayload, LoginResponse, TicketCreatePayload, TicketUpdatePayload,
  ArticleCreatePayload, Ticket, Article, TicketDetail, PaginatedResponse,
  Overview, DashboardStats, TicketFilters, User, Group, TicketState, TicketPriority,
  TicketCategory, Region, TicketStateLog, DuplicateCheckPayload, DuplicateCheckResult,
  BatchUpdatePayload, ExportPayload,
} from '@/types'
import {
  users, groups, tickets, articles, ticketLinks, overviews,
  dashboardStats, ticketStates, ticketPriorities,
  ticketCategories, regions, stateLogs, duplicateCandidates,
} from './data'

function delay<T>(data: T, ms = 200): Promise<T> {
  return new Promise(resolve => setTimeout(() => resolve(data), ms))
}

let nextTicketId = 100
let nextArticleId = 2000

// 与后端 RETURN_TRANSITIONS 保持一致：
//   (pending, returned): 客户/客服 退回给创建人
//   (open, pending):     处理人退回给团队负责人
const RETURN_TRANSITIONS = new Set<string>([
  'pending->returned',
  'open->pending',
])

export const mockAuthApi = {
  async login(payload: LoginPayload): Promise<LoginResponse> {
    const user = users.find(u => u.email === payload.email)
    if (!user || payload.password !== 'admin123') {
      throw { response: { status: 401, data: { error: { code: 'UNAUTHORIZED', message: '邮箱或密码错误' } } } }
    }
    return delay({
      access_token: 'mock-access-token-' + user.id,
      refresh_token: 'mock-refresh-token-' + user.id,
      token_type: 'bearer',
      expires_in: 1800,
      user,
    })
  },
}

function matchFilters(t: Ticket, filters: TicketFilters): boolean {
  if (filters.state_id && t.state.id !== filters.state_id) return false
  if (filters.priority_id && t.priority.id !== filters.priority_id) return false
  if (filters.group_id && t.group.id !== filters.group_id) return false
  if (filters.owner_id && t.owner?.id !== filters.owner_id) return false
  if (filters.customer_type && t.customer_type !== filters.customer_type) return false
  if (filters.category_l1_id && t.category_l1?.id !== filters.category_l1_id) return false
  if (filters.category_l2_id && t.category_l2?.id !== filters.category_l2_id) return false
  if (filters.is_duplicate !== null && filters.is_duplicate !== undefined && t.is_duplicate !== filters.is_duplicate) return false
  if (filters.resolved !== null && filters.resolved !== undefined && t.resolved !== filters.resolved) return false
  if (filters.escalated) {
    if (!t.escalation_at || new Date(t.escalation_at) > new Date()) return false
  }
  if (filters.keyword) {
    const kw = filters.keyword.toLowerCase()
    if (!t.number.toLowerCase().includes(kw)) return false
  }
  return true
}

export const mockTicketApi = {
  async list(filters: TicketFilters = {}, page = 1, perPage = 25): Promise<PaginatedResponse<Ticket>> {
    const filtered = tickets.filter(t => matchFilters(t, filters))
    filtered.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    const start = (page - 1) * perPage
    const data = filtered.slice(start, start + perPage)
    return delay({
      data,
      pagination: { page, per_page: perPage, total: filtered.length, total_pages: Math.ceil(filtered.length / perPage) },
    })
  },

  async get(id: number): Promise<TicketDetail> {
    const ticket = tickets.find(t => t.id === id)
    if (!ticket) throw { response: { status: 404, data: { error: { code: 'NOT_FOUND', message: `Ticket #${id} not found` } } } }
    return delay({
      ...ticket,
      articles: articles[id] || [],
      links: ticketLinks[id] || [],
      state_logs: stateLogs[id] || [],
    })
  },

  async create(payload: TicketCreatePayload): Promise<Ticket> {
    const id = nextTicketId++
    const group = groups.find(g => g.id === payload.group_id) || groups[0]
    const priority = ticketPriorities.find(p => p.id === payload.priority_id) || ticketPriorities[1]
    const now = new Date().toISOString()
    const newTicket: Ticket = {
      id,
      number: `${new Date().toISOString().slice(0, 8).replace(/-/g, '')}-${String(id).padStart(4, '0')}`,
      state: ticketStates[0],
      priority,
      group,
      owner: null,
      customer: users[1],
      organization: null,
      channel: payload.channel,
      escalation_at: new Date(Date.now() + 4 * 3600_000).toISOString(),
      close_at: null,
      article_count: 1,
      created_at: now,
      updated_at: now,
      // P7 字段
      customer_type: payload.customer_type,
      customer_phone: payload.customer_phone,
      device_sn: payload.device_sn ?? null,
      contact_name: payload.contact_name ?? null,
      contact_phone: payload.contact_phone ?? null,
      customer_company: payload.customer_company ?? null,
      organization: payload.customer_company ? { id: 0, name: payload.customer_company, active: true } : null,
      region: payload.region_name ? { province: payload.region_name } : null,
      region_name: payload.region_name ?? null,
      category_l1: payload.category_l1_id ? (ticketCategories.find(c => c.id === payload.category_l1_id) || null) : null,
      category_l2: payload.category_l2_id ? (ticketCategories.find(c => c.id === payload.category_l2_id) || null) : null,
      is_duplicate: payload.is_duplicate ?? false,
      duplicate_reason: payload.duplicate_reason ?? null,
      duplicate_of: payload.duplicate_of_id ? (tickets.find(t => t.id === payload.duplicate_of_id) || null) : null,
      first_owner: null,
      skill_group: payload.skill_group_id ? (groups.find(g => g.id === payload.skill_group_id) || null) : null,
      sla_breached: false,
      resolved: false,
      resolution: null,
      archive_notes: null,
      is_callbacked: false,
      urged_at: null,
      urged_by: null,
      has_addition: false,
      has_returned: false,
    }
    tickets.unshift(newTicket)
    articles[id] = [{
      id: nextArticleId++, ticket_id: id, origin_by: users[1],
      sender_type: 'customer', article_type: 'web',
      body: payload.article.body, content_type: payload.article.content_type,
      created_at: now,
      is_addition: false, append_reason: null,
    }]
    return delay(newTicket)
  },

  async update(id: number, payload: TicketUpdatePayload): Promise<Ticket> {
    const ticket = tickets.find(t => t.id === id)
    if (!ticket) throw { response: { status: 404 } }
    if (payload.state) {
      const oldState = ticket.state
      const newState = payload.state as any
      ticket.state = newState
      // has_returned 跟随"最新一次动作"：只有当本次转换属于退回动作时才置 true
      const isReturn = RETURN_TRANSITIONS.has(`${oldState}->${newState}`)
      ticket.has_returned = isReturn
      // 同步更新最新一条 state_log 的 from/to key
      const logs = stateLogs[id]
      if (logs && logs.length > 0) {
        const last = logs[logs.length - 1]
        last.from_state_key = oldState
        last.to_state_key = newState
      }
    }
    if (payload.state_id) {
      const state = ticketStates.find(s => s.id === payload.state_id)
      if (state) ticket.state = state
    }
    if (payload.priority_id) {
      const pri = ticketPriorities.find(p => p.id === payload.priority_id)
      if (pri) ticket.priority = pri
    }
    if (payload.owner_id !== undefined) {
      ticket.owner = payload.owner_id ? (users.find(u => u.id === payload.owner_id) || null) : null
    }
    if (payload.group_id) {
      const grp = groups.find(g => g.id === payload.group_id)
      if (grp) ticket.group = grp
    }
    if (payload.resolved !== undefined) ticket.resolved = payload.resolved
    if (payload.resolution !== undefined) ticket.resolution = payload.resolution
    ticket.updated_at = new Date().toISOString()
    return delay({ ...ticket })
  },

  // —— P7：重投工单检测 ——
  async checkDuplicate(payload: DuplicateCheckPayload): Promise<DuplicateCheckResult> {
    const key = `${payload.customer_phone}|${payload.device_sn || ''}|${payload.category_l1_id}`
    const candidates = duplicateCandidates[key] || []
    return delay({ has_duplicates: candidates.length > 0, candidates })
  },

  // —— P7：获取工单状态流转日志 ——
  async getStateLogs(ticketId: number): Promise<TicketStateLog[]> {
    return delay(stateLogs[ticketId] || [])
  },

  // —— P7：批量更新 ——
  async batchUpdate(payload: BatchUpdatePayload): Promise<{ updated: number }> {
    let count = 0
    for (const id of payload.ticket_ids) {
      const ticket = tickets.find(t => t.id === id)
      if (!ticket) continue
      if (payload.state_id) {
        const s = ticketStates.find(x => x.id === payload.state_id)
        if (s) ticket.state = s
      }
      if (payload.priority_id) {
        const p = ticketPriorities.find(x => x.id === payload.priority_id)
        if (p) ticket.priority = p
      }
      if (payload.owner_id !== undefined) {
        ticket.owner = payload.owner_id ? (users.find(u => u.id === payload.owner_id) || null) : null
      }
      if (payload.group_id) {
        const g = groups.find(x => x.id === payload.group_id)
        if (g) ticket.group = g
      }
      ticket.updated_at = new Date().toISOString()
      count++
    }
    return delay({ updated: count })
  },

  // —— P7：导出 ——
  async export(payload: ExportPayload): Promise<{ url: string; filename: string }> {
    const filtered = tickets.filter(t => matchFilters(t, payload.filters))
    const lines: string[] = []
    const headers = payload.columns.map(c => c.label)
    lines.push(headers.join(','))
    for (const t of filtered) {
      const row = payload.columns.map(c => {
        switch (c.key) {
          case 'number': return t.number
          case 'state': return t.state.name
          case 'priority': return t.priority.name
          case 'channel': return t.channel
          case 'created_at': return t.created_at
          case 'close_at': return t.close_at || ''
          case 'close_duration': return t.close_at ? `${Math.round((new Date(t.close_at).getTime() - new Date(t.created_at).getTime()) / 60000)}分钟` : ''
          case 'customer_name': return t.customer ? `${t.customer.firstname}${t.customer.lastname}` : ''
          case 'customer_phone': return t.customer_phone
          case 'customer_type': return t.customer_type === 'enterprise' ? '政企' : '个人'
          case 'device_sn': return t.device_sn || ''
          case 'region': return t.region ? [t.region.province, t.region.city, t.region.district, t.region.station].filter(Boolean).join(' / ') : ''
          case 'category_l1': return t.category_l1?.name || ''
          case 'category_l2': return t.category_l2?.name || ''
          case 'symptom': return t.symptom || ''
          case 'is_duplicate': return t.is_duplicate ? '是' : '否'
          case 'first_owner': return t.first_owner ? `${t.first_owner.firstname}${t.first_owner.lastname}` : ''
          case 'skill_group': return t.skill_group?.name || t.group.name
          case 'sla_breached': return t.sla_breached ? '超时' : '达标'
          case 'resolved': return t.resolved ? '是' : '否'
          case 'resolution': return t.resolution || ''
          default: return ''
        }
      }).map(v => `"${String(v).replace(/"/g, '""')}"`)
      lines.push(row.join(','))
    }
    const csv = '﻿' + lines.join('\n') // BOM 让 Excel 识别 UTF-8
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    return delay({ url, filename: `工单导出_${new Date().toISOString().slice(0, 10)}.${payload.format === 'xlsx' ? 'xlsx' : 'csv'}` })
  },
}

export const mockArticleApi = {
  async create(ticketId: number, payload: ArticleCreatePayload): Promise<Article> {
    const ticket = tickets.find(t => t.id === ticketId)
    if (!ticket) throw { response: { status: 404 } }
    const type = payload.type || payload.article_type || 'note'
    const article: Article = {
      id: nextArticleId++,
      ticket_id: ticketId,
      origin_by: users[1],
      sender_type: 'agent',
      type,
      article_type: (payload.article_type || 'note') as Article['article_type'],
      body: payload.body,
      content_type: payload.content_type || 'text/plain',
      state_key: type === 'reply' ? (ticket as any).state_key : undefined,
      created_at: new Date().toISOString(),
      is_addition: payload.type === 'addition',
      append_reason: payload.append_reason ?? null,
    }
    if (!articles[ticketId]) articles[ticketId] = []
    articles[ticketId].push(article)
    ticket.article_count++
    if (type === 'addition') {
      ticket.has_addition = true
    }
    ticket.updated_at = article.created_at
    return delay(article)
  },
}

export const mockOverviewApi = {
  async list(): Promise<Overview[]> {
    return delay(overviews)
  },

  async tickets(overviewId: number, page = 1, perPage = 25): Promise<PaginatedResponse<Ticket>> {
    let filtered: Ticket[]
    switch (overviewId) {
      case 1:
        filtered = tickets.filter(t => t.owner?.id === 2 && t.state.state_type !== 'closed')
        break
      case 2:
        filtered = tickets.filter(t => !t.owner && t.state.state_type === 'new')
        break
      case 3:
        filtered = tickets.filter(t => t.escalation_at && new Date(t.escalation_at) < new Date() && t.state.state_type !== 'closed')
        break
      default:
        filtered = tickets
    }
    const start = (page - 1) * perPage
    return delay({
      data: filtered.slice(start, start + perPage),
      pagination: { page, per_page: perPage, total: filtered.length, total_pages: Math.ceil(filtered.length / perPage) },
    })
  },
}

export const mockStatsApi = {
  async dashboard(): Promise<DashboardStats> {
    return delay(dashboardStats)
  },
}

export const mockMetaApi = {
  async getStates(): Promise<TicketState[]> { return delay(ticketStates) },
  async getPriorities(): Promise<TicketPriority[]> { return delay(ticketPriorities) },
  async getGroups(): Promise<Group[]> { return delay(groups) },
  async getAgents(): Promise<User[]> { return delay(users.filter(u => u.role.name === 'agent' || u.role.name === 'admin')) },
  // P7
  async getCategories(): Promise<TicketCategory[]> { return delay(ticketCategories) },
  async getRegions(): Promise<Region[]> { return delay(regions) },
}
