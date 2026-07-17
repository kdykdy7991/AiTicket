import api from './index'

export interface SkillGroupMembership {
  skill_group_id: number
  is_dispatcher: boolean
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
}

interface ListResp<T> { data: T[] }

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
