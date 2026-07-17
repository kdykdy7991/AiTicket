import { defineStore } from 'pinia'
import { ref } from 'vue'
import { overviewApi, statsApi } from '@/api/overviews'
import type { Overview, Ticket, DashboardStats, Pagination } from '@/types'

export const useOverviewStore = defineStore('overview', () => {
  const overviews = ref<Overview[]>([])
  const currentOverviewTickets = ref<Ticket[]>([])
  const currentOverviewPagination = ref<Pagination>({ page: 1, per_page: 10, total: 0, total_pages: 0 })
  const dashboardStats = ref<DashboardStats | null>(null)
  const loading = ref(false)

  async function fetchOverviews() {
    overviews.value = await overviewApi.list()
  }

  async function fetchOverviewTickets(overviewId: number, page = 1) {
    loading.value = true
    try {
      const res = await overviewApi.tickets(overviewId, page, 10)
      currentOverviewTickets.value = res.data
      currentOverviewPagination.value = res.pagination
    } finally {
      loading.value = false
    }
  }

  async function fetchDashboardStats() {
    dashboardStats.value = await statsApi.dashboard()
  }

  return {
    overviews, currentOverviewTickets, currentOverviewPagination, dashboardStats, loading,
    fetchOverviews, fetchOverviewTickets, fetchDashboardStats,
  }
})
