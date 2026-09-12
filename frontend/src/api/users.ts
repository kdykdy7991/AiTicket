import api from './index'

export interface SkillGroupMembership {
  id?: number
  name?: string
  skill_group_id?: number
}

export interface UserItem {
  id: number
  username: string
  name: string
  phone: string | null
  /** 多角色：一个用户可拥有多个业务角色编码 */
  roles: string[]
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
  /** 全量替换角色集合，至少一个 */
  roles?: string[]
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
