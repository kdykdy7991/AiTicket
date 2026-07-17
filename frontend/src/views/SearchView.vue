<template>
  <div class="search-view">
    <div class="page-header">
      <h2 class="page-title">搜索结果</h2>
      <p class="page-subtitle">关键词: "{{ keyword }}"</p>
    </div>

    <el-card shadow="never" v-loading="loading" class="search-card">
      <template v-if="!loading && results.length === 0">
        <div class="empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="empty-icon">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <p class="empty-text">未找到匹配的工单</p>
          <p class="empty-hint">尝试使用不同的关键词搜索</p>
        </div>
      </template>
      <TicketTable v-else :tickets="results" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ticketApi } from '@/api/tickets'
import TicketTable from '@/components/ticket/TicketTable.vue'
import type { Ticket } from '@/types'

const route = useRoute()
const keyword = ref('')
const results = ref<Ticket[]>([])
const loading = ref(false)

async function doSearch() {
  const q = (route.query.q as string) || ''
  keyword.value = q
  if (!q) { results.value = []; return }
  loading.value = true
  try {
    const res = await ticketApi.list({ keyword: q })
    results.value = res.data
  } finally {
    loading.value = false
  }
}

onMounted(doSearch)
watch(() => route.query.q, doSearch)
</script>

<style scoped>
.page-header {
  margin-bottom: 24px;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
  margin: 0;
}
.page-subtitle {
  font-size: 14px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}

.search-card {
  border: 1px solid var(--color-border-light);
}
.search-card :deep(.el-card__body) {
  padding: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 20px;
}
.empty-icon {
  color: var(--color-text-placeholder);
  margin-bottom: 16px;
}
.empty-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin: 0;
}
.empty-hint {
  font-size: 13px;
  color: var(--color-text-tertiary);
  margin: 6px 0 0;
}
</style>
