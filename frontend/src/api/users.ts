import api from './index'

export interface SkillGroupMembership {
  skill_group_id: number
  is_dispatcher: boolean
  complaint_leader: boolean
  complaint_division_leader: boolean
  complaint_responsibilities: string[]
}

export interface UserItem {
  id: number
  username: string
  name: string
  phone: string | null
  role: string
  group_id: number | null
  is_group_leader: boolean
  is_active: boolean
  dingtalk_id: string | null
  skill_groups: SkillGroupMembership[]
  grants: string[]
  created_at: string
}

export interface UserPayload {
  username?: string
  name?: string
  phone?: string | null
  password?: string
  role?: string
  group_id?: number | null
  is_group_leader?: boolean
  skill_groups?: SkillGroupMembership[]
  dingtalk_id?: string | null
  is_active?: boolean
  grants?: string[]
}

interface ListResp<T> { data: T[] }

export interface GrantDefinition {
  key: string
  label: string
  kind: 'bundle' | 'read' | 'feature'
  description: string
  includes: string[]
}

export interface PasswordChangeLog {
  id: number
  actor_id: number | null
  actor_name: string
  target_id: number | null
  target_name: string
  method: 'self' | 'admin'
  method_label: string
  ip_address: string | null
  created_at: string
}

export const passwordLogApi = {
  async list(params?: { user_id?: number; limit?: number }): Promise<PasswordChangeLog[]> {
    const res = await api.get<unknown, { data: PasswordChangeLog[] }>('/password-change-logs', { params })
    return res.data
  },
}

export const grantApi = {
  async list(): Promise<GrantDefinition[]> {
    const res = await api.get<unknown, { data: GrantDefinition[] }>('/grant-definitions')
    return res.data
  },
}

export const userApi = {
  async list(params?: { role?: string; skill_group_id?: number; keyword?: string; include_inactive?: boolean }): Promise<UserItem[]> {
    const res: ListResp<UserItem> = await api.get('/users', { params })
    return res.data
  },

  async create(data: UserPayload): Promise<any> {
    const res = await api.post('/users', data)
    return res.data
  },

  async update(id: number, data: UserPayload): Promise<any> {
    const res = await api.patch(`/users/${id}`, data)
    return res.data
  },

  async activate(id: number): Promise<any> {
    const res = await api.post(`/users/${id}/activate`)
    return res.data
  },

  async disable(id: number): Promise<any> {
    const res = await api.delete(`/users/${id}`)
    return res.data
  },
}
