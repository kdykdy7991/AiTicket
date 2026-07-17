import api from './index'

export interface CategoryNode {
  id: number
  name: string
  level: number
  parent_id: number | null
  sort_order: number
  is_active: boolean
  children: CategoryNode[]
  created_at?: string
  updated_at?: string
}

export interface CategoryPayload {
  name: string
  parent_id?: number | null
  sort_order?: number
  is_active?: boolean
}

interface ListResp<T> { data: T[] }

export const categoryApi = {
  async list(includeInactive = false): Promise<CategoryNode[]> {
    const res: ListResp<CategoryNode> = await api.get('/categories', {
      params: { _t: Date.now(), include_inactive: includeInactive },
    })
    return res.data
  },
  async create(data: CategoryPayload): Promise<any> {
    const res = await api.post('/categories', data)
    return res.data
  },
  async update(id: number, data: Partial<CategoryPayload>): Promise<any> {
    const res = await api.patch(`/categories/${id}`, data)
    return res.data
  },
  async remove(id: number): Promise<any> {
    const res = await api.delete(`/categories/${id}`)
    return res.data
  },
}
