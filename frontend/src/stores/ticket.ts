import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ticketApi, articleApi, draftApi } from '@/api/tickets'
import type { Ticket, TicketDetail, TicketFilters, Pagination, TicketCreatePayload, TicketUpdatePayload, ArticleCreatePayload } from '@/types'

export const useTicketStore = defineStore('ticket', () => {
  const tickets = ref<Ticket[]>([])
  const currentTicket = ref<TicketDetail | null>(null)
  const filters = ref<TicketFilters>({})
  const pagination = ref<Pagination>({ page: 1, per_page: 25, total: 0, total_pages: 0 })
  const loading = ref(false)
  const drafts = ref<Ticket[]>([])

  async function fetchTickets(page = 1) {
    loading.value = true
    try {
      const res = await ticketApi.list(filters.value, page, pagination.value.per_page)
      tickets.value = res.data
      pagination.value = res.pagination
    } finally {
      loading.value = false
    }
  }

  async function fetchTicketDetail(id: number) {
    loading.value = true
    try {
      currentTicket.value = await ticketApi.get(id)
    } finally {
      loading.value = false
    }
  }

  async function createTicket(data: TicketCreatePayload): Promise<Ticket> {
    const ticket = await ticketApi.create(data)
    return ticket
  }

  async function updateTicket(id: number, data: TicketUpdatePayload) {
    await ticketApi.update(id, data)
    // 更新后重新拉取详情，确保 state/priority 等对象字段结构一致
    if (currentTicket.value?.id === id) {
      currentTicket.value = await ticketApi.get(id)
    }
  }

  async function addArticle(ticketId: number, data: ArticleCreatePayload) {
    const article = await articleApi.create(ticketId, data)
    if (currentTicket.value?.id === ticketId) {
      // 处理说明会触发状态流转，追加也可能影响展示，重新拉取完整详情保证同步
      currentTicket.value = await ticketApi.get(ticketId)
    }
    return article
  }

  function setFilters(newFilters: TicketFilters) {
    filters.value = { ...newFilters }
  }

  // 详情更新后，同步刷新列表中对应工单的状态，避免返回列表页缓存不同步
  function refreshCurrentInList() {
    if (!currentTicket.value) return
    const idx = tickets.value.findIndex(t => t.id === currentTicket.value!.id)
    if (idx === -1) return
    const cur = currentTicket.value as any
    const old = tickets.value[idx] as any
    tickets.value[idx] = {
      ...old,
      state: cur.state,
      state_key: cur.state_key,
      owner_id: cur.owner_id,
      owner: cur.owner,
      owner_name: (cur as any).owner_name,
      updated_at: cur.updated_at,
    } as any
  }

  // Draft operations
  async function fetchDrafts() {
    const res = await draftApi.list()
    drafts.value = res.data || []
  }

  async function saveDraft(payload: Record<string, any>) {
    return await draftApi.save(payload)
  }

  async function submitDraft(draftId: number): Promise<Ticket> {
    return await draftApi.submit(draftId)
  }

  async function deleteDraft(draftId: number) {
    await draftApi.delete(draftId)
  }

  return {
    tickets, currentTicket, filters, pagination, loading, drafts,
    fetchTickets, fetchTicketDetail, createTicket, updateTicket, addArticle, setFilters,
    refreshCurrentInList,
    fetchDrafts, saveDraft, submitDraft, deleteDraft,
  }
})
