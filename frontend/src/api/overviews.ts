import api from './index'
import { mockOverviewApi } from '@/mock'   // overview 一期暂用 mock
import type {
  Overview, PaginatedResponse, Ticket,
  TicketState, TicketPriority, Group, User,
  TicketCategory, Region,
} from '@/types'

/** Dashboard 概览（按状态分类）后端尚未提供，沿用 mock */
export const overviewApi = {
  list(): Promise<Overview[]> {
    return mockOverviewApi.list()
  },
  tickets(overviewId: number, page?: number, perPage?: number): Promise<PaginatedResponse<Ticket>> {
    return mockOverviewApi.tickets(overviewId, page, perPage)
  },
}

export const statsApi = {
  async dashboard(params: { date_from?: string; date_to?: string } = {}): Promise<any> {
    const res: any = await api.get('/stats/dashboard', { params: { ...params, _t: Date.now() } })
    return res.data
  },

  async report(params: { period?: string; date_from?: string; date_to?: string; skill_group_id?: number } = {}): Promise<any> {
    const res: any = await api.get('/stats/report', { params: { ...params, _t: Date.now() } })
    return res.data
  },

  async trend(params: { date_from?: string; date_to?: string; skill_group_id?: number } = {}): Promise<any> {
    const res: any = await api.get('/stats/trend', { params: { ...params, _t: Date.now() } })
    return res.data
  },
}

interface ListResp<T> { data: T[] }

function adaptCategory(c: any): TicketCategory {
  return {
    id: c.id,
    name: c.name,
    parent_id: c.parent_id,
    sort_order: c.sort_order ?? 0,
    active: true,
  }
}

function flattenCategories(tree: any[]): TicketCategory[] {
  const out: TicketCategory[] = []
  function walk(nodes: any[]) {
    for (const n of nodes) {
      out.push(adaptCategory(n))
      if (n.children?.length) walk(n.children)
    }
  }
  walk(tree)
  return out
}

const LEVEL_MAP = { 1: 'province', 2: 'city', 3: 'district', 4: 'station' } as const

export const metaApi = {
  // 工单状态/优先级是固定枚举，前端直接定义即可（后端用字符串枚举）
  async getStates(): Promise<TicketState[]> {
    return [
      { id: 1, name: '待受理', state_type: 'new', sort_order: 1 } as any,
      { id: 2, name: '处理中', state_type: 'open', sort_order: 2 } as any,
      { id: 3, name: '已处理', state_type: 'pending', sort_order: 3 } as any,
      { id: 4, name: '暂缓处理', state_type: 'pending', sort_order: 4 } as any,
      { id: 5, name: '已归档', state_type: 'closed', sort_order: 5 } as any,
      { id: 6, name: '退回', state_type: 'open', sort_order: 6 } as any,
      { id: 7, name: '已撤销', state_type: 'closed', sort_order: 7 } as any,
    ]
  },

  async getPriorities(): Promise<TicketPriority[]> {
    return [
      { id: 1, name: 'P1 特别重大事件', ui_color: '#F56C6C', sort_order: 1 } as any,
      { id: 2, name: 'P2 重大事件', ui_color: '#E6A23C', sort_order: 2 } as any,
      { id: 3, name: 'P3 较大事件', ui_color: '#409EFF', sort_order: 3 } as any,
      { id: 4, name: 'P4 一般事件', ui_color: '#67C23A', sort_order: 4 } as any,
    ]
  },

  async getGroups(): Promise<Group[]> {
    const res: ListResp<any> = await api.get('/groups')
    return res.data.map(g => ({ id: g.id, name: g.name, parent_id: null, active: true })) as any
  },

  async getSkillGroups(): Promise<Group[]> {
    const res: ListResp<any> = await api.get('/skill-groups')
    return res.data.map(g => ({ id: g.id, name: g.name, parent_id: null, active: true })) as any
  },

  // 查某对接部门的部门对接人（建单时选）
  async getDispatchers(skillGroupId: number): Promise<any[]> {
    const res: ListResp<any> = await api.get(`/skill-groups/${skillGroupId}/dispatchers`)
    return res.data
  },

  // 查某对接部门的处理人（分派时选）
  async getHandlers(skillGroupId: number): Promise<any[]> {
    const res: ListResp<any> = await api.get(`/skill-groups/${skillGroupId}/handlers`)
    return res.data
  },

  async getAgents(): Promise<User[]> {
    // 负责人下拉应包含所有活跃用户（坐席、组长、管理员都可处理工单）
    const res: ListResp<any> = await api.get('/users')
    return res.data
      .filter((u: any) => u.is_active)
      .map(u => ({
        id: u.id,
        email: u.username,
        firstname: u.name,
        lastname: '',
        role: { id: 0, name: u.role, permissions: [] },
        active: u.is_active,
      })) as any
  },

  // 工单创建人：仅客服组(agent)成员 + 管理员。
  // 处理人(handler)在对接部门，不参与建单，不应出现在创建人筛选里。
  async getCreators(): Promise<User[]> {
    const [a, ad] = await Promise.all([
      api.get('/users', { params: { role: 'agent' } }),
      api.get('/users', { params: { role: 'admin' } }),
    ])
    return [...(a.data as any[]), ...(ad.data as any[])]
      .filter((u: any) => u.is_active)
      .map(u => ({
        id: u.id,
        email: u.username,
        firstname: u.name,
        lastname: '',
        role: { id: 0, name: u.role, permissions: [] },
        active: u.is_active,
      })) as any
  },

  async getCategories(): Promise<TicketCategory[]> {
    const res: ListResp<any> = await api.get('/categories')
    return flattenCategories(res.data)
  },

  async getRegions(): Promise<Region[]> {
    const res: ListResp<any> = await api.get('/regions')
    return res.data.map((r: any) => ({
      id: r.id,
      name: r.name,
      parent_id: r.parent_id,
      level: LEVEL_MAP[r.level as 1 | 2 | 3 | 4] ?? 'province',
    })) as any
  },
}
