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

/** 下载地址必须带 Authorization 头，不能用 <img src> / <a href> 直接访问，
 *  因此统一先取回 blob，再由调用方决定是预览还是保存。 */
async function fetchAttachmentBlob(attachment: PocAttachment): Promise<Blob> {
  return await api.get(attachment.download_url.replace('/api/v1', ''), {
    responseType: 'blob',
  }) as unknown as Blob
}

export const pocTicketApi = {
  fetchAttachmentBlob,
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
    const blob = await fetchAttachmentBlob(attachment)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = attachment.original_filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    // 交给浏览器读取后再释放，立即 revoke 在部分浏览器会打断下载
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
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
