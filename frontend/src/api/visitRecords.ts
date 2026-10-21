import api from './index'

export interface VisitRecord {
  id: number
  source_sheet: string | null
  source_row: number | null
  contact_at: string
  contact_number: string | null
  customer_name: string | null
  service_agent: string | null
  channel: string
  category_l1: string | null
  category_l2: string | null
  registered_ticket: boolean | null
  fields: Record<string, string>
}

export type VisitPayload = Omit<VisitRecord, 'id' | 'source_sheet' | 'source_row'>

export const visitRecordApi = {
  async list(params: Record<string, string | number | boolean | undefined>) {
    return await api.get('/visit-records', { params }) as unknown as {
      data: VisitRecord[]
      pagination: { page: number; page_size: number; total: number }
    }
  },
  async create(payload: VisitPayload) {
    return await api.post('/visit-records', payload) as unknown as { data: VisitRecord }
  },
  async update(id: number, payload: VisitPayload) {
    return await api.put(`/visit-records/${id}`, payload) as unknown as { data: VisitRecord }
  },
  async export(params: Record<string, string | undefined>) {
    return await api.get('/visit-records/export', { params, responseType: 'blob' }) as unknown as Blob
  },
}
