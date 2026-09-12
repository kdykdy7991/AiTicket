import api from './index'
import type {
  PocPaginatedResponse,
  PocTicketActionRequest,
  PocAttachment,
  PocTicketBrief,
  PocTicketDetail,
  PocTicketFilters,
  PocTicketForm,
} from '@/types/poc'

function queryParams(filters: PocTicketFilters = {}, page = 1, pageSize = 20) {
  return { ...filters, page, page_size: pageSize }
}

export const pocTicketApi = {
  async list(filters?: PocTicketFilters, page = 1, pageSize = 20): Promise<PocPaginatedResponse<PocTicketBrief>> {
    return await api.get('/tickets', { params: queryParams(filters, page, pageSize) })
  },

  async get(id: number): Promise<PocTicketDetail> {
    return await api.get(`/tickets/${id}`)
  },

  async createDraft(data: Partial<PocTicketForm>): Promise<PocTicketDetail> {
    const response: { data: PocTicketDetail } = await api.post('/tickets', { ...data, is_draft: true })
    return response.data
  },

  async updateDraft(id: number, data: Partial<PocTicketForm>): Promise<PocTicketDetail> {
    const response: { data: PocTicketDetail } = await api.patch(`/tickets/drafts/${id}`, { ...data, is_draft: true })
    return response.data
  },

  async submitDraft(id: number, data: Partial<PocTicketForm>): Promise<PocTicketDetail> {
    const response: { data: PocTicketDetail } = await api.post(`/tickets/drafts/${id}/submit`, data)
    return response.data
  },

  async executeAction(id: number, request: PocTicketActionRequest): Promise<PocTicketDetail> {
    return await api.post(`/tickets/${id}/actions`, request)
  },

  async uploadAttachments(id: number, files: File[]): Promise<PocAttachment[]> {
    const form = new FormData()
    files.forEach(file => form.append('files', file))
    const response: { data: PocAttachment[] } = await api.post(`/tickets/${id}/attachments`, form)
    return response.data
  },

  async downloadAttachment(attachment: PocAttachment): Promise<void> {
    const blob = await api.get(attachment.download_url.replace('/api/v1', ''), { responseType: 'blob' }) as unknown as Blob
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = attachment.original_filename
    link.click()
    URL.revokeObjectURL(url)
  },

  async update(id: number, data: Partial<PocTicketForm>): Promise<PocTicketDetail> {
    return await api.patch(`/tickets/${id}`, data)
  },

  async removeDraft(id: number): Promise<void> {
    await api.delete(`/tickets/drafts/${id}`)
  },

  async export(filters?: PocTicketFilters): Promise<Blob> {
    return await api.get('/tickets/export', { params: filters, responseType: 'blob' }) as unknown as Blob
  },
}
