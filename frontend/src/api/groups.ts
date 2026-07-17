import api from './index'

export interface GroupItem {
  id: number
  name: string
  dingtalk_webhook_url: string | null
  created_at: string
}

export interface GroupPayload {
  name: string
  dingtalk_webhook_url?: string | null
}

interface ListResp<T> { data: T[] }

export const groupApi = {
  async list(): Promise<GroupItem[]> {
    const res: ListResp<GroupItem> = await api.get('/groups', { params: { _t: Date.now() } })
    return res.data
  },
  async create(data: GroupPayload): Promise<any> {
    const res = await api.post('/groups', data)
    return res.data
  },
  async update(id: number, data: GroupPayload): Promise<any> {
    const res = await api.patch(`/groups/${id}`, data)
    return res.data
  },
  async remove(id: number): Promise<any> {
    const res = await api.delete(`/groups/${id}`)
    return res.data
  },
}

export const skillGroupApi = {
  async list(): Promise<GroupItem[]> {
    const res: ListResp<GroupItem> = await api.get('/skill-groups', { params: { _t: Date.now() } })
    return res.data
  },
  async create(data: GroupPayload): Promise<any> {
    const res = await api.post('/skill-groups', data)
    return res.data
  },
  async update(id: number, data: GroupPayload): Promise<any> {
    const res = await api.patch(`/skill-groups/${id}`, data)
    return res.data
  },
  async remove(id: number): Promise<any> {
    const res = await api.delete(`/skill-groups/${id}`)
    return res.data
  },
}
