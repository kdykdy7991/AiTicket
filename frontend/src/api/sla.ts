import api from './index'

export interface SLAPolicyItem {
  id: number
  category_id: number
  category_name: string | null
  variant: string
  solution_minutes: number
  created_at: string
}

export interface SLAPolicyPayload {
  category_id: number
  variant: string
  solution_minutes: number
}

interface ListResp<T> { data: T[] }

export const slaApi = {
  async list(): Promise<SLAPolicyItem[]> {
    const res: ListResp<SLAPolicyItem> = await api.get(`/sla-policies?_=${Date.now()}`, {
      headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate' },
    })
    return res.data
  },
  async create(data: SLAPolicyPayload): Promise<any> {
    const res = await api.post('/sla-policies', data)
    return res.data
  },
  async update(id: number, data: SLAPolicyPayload): Promise<any> {
    const res = await api.patch(`/sla-policies/${id}`, data)
    return res.data
  },
  async remove(id: number): Promise<any> {
    const res = await api.delete(`/sla-policies/${id}`)
    return res.data
  },
}
