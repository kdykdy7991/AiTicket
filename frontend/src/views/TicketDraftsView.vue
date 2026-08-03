<template>
  <div class="drafts-view">
    <div class="page-header">
      <div>
        <h2 class="page-title">我的草稿</h2>
        <p class="page-subtitle">暂存的工单草稿</p>
      </div>
    </div>

    <el-card shadow="never" v-loading="loading" class="drafts-card">
      <template v-if="drafts.length === 0 && !loading">
        <div class="empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
          </svg>
          <p class="empty-text">暂无草稿</p>
        </div>
      </template>

      <template v-else>
        <div class="drafts-list">
          <div
            v-for="draft in drafts"
            :key="draft.id"
            class="draft-item"
          >
            <div class="draft-main" @click="onEdit(draft.id)">
              <div class="draft-left">
                <span class="draft-customer">{{ draft.customer_name }}</span>
                <span v-if="(draft as any).category_l1_name" class="draft-category">{{ (draft as any).category_l1_name }}{{ (draft as any).category_l2_name ? '/' + (draft as any).category_l2_name : '' }}</span>
              </div>
              <div class="draft-right">
                <span class="draft-time">{{ formatTime(draft.updated_at) }}</span>
                <div class="draft-actions">
                  <el-button size="small" text @click.stop="onDelete(draft.id)">删除</el-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTicketStore } from '@/stores/ticket'
import { ElMessage, ElMessageBox } from 'element-plus'
import RelativeTime from '@/components/common/RelativeTime.vue'

const router = useRouter()
const ticketStore = useTicketStore()
const drafts = ref<any[]>([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    await ticketStore.fetchDrafts()
    drafts.value = ticketStore.drafts
  } finally {
    loading.value = false
  }
})

function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function onEdit(id: number) {
  router.push({ name: 'TicketCreate', query: { draft_id: String(id) } })
}

async function onSubmit(id: number) {
  try {
    const ticket = await ticketStore.submitDraft(id)
    ElMessage.success('工单提交成功')
    await ticketStore.fetchDrafts()
    drafts.value = ticketStore.drafts
    router.push({ name: 'TicketDetail', params: { id: ticket.id } })
  } catch (err: any) {
    ElMessage.error(err.message || '提交失败')
  }
}

async function onDelete(id: number) {
  try {
    await ElMessageBox.confirm('确认删除此草稿？', '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await ticketStore.deleteDraft(id)
    ElMessage.success('已删除')
    await ticketStore.fetchDrafts()
    drafts.value = ticketStore.drafts
  } catch {
    // cancelled
  }
}
</script>

<style scoped>
.drafts-view {
  max-width: 900px;
}

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

.drafts-card {
  border-radius: var(--radius-lg);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--color-text-tertiary);
}

.empty-state svg {
  opacity: 0.3;
  margin-bottom: 16px;
}

.empty-text {
  font-size: 15px;
  margin: 0 0 16px;
}

.drafts-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.draft-item {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  transition: all var(--duration-fast) var(--ease-out);
}

.draft-item:hover {
  border-color: var(--color-border);
  background: var(--color-bg-subtle);
}

.draft-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  cursor: pointer;
}

.draft-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.draft-customer {
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
}

.draft-category {
  font-size: 12.5px;
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.draft-right {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}

.draft-time {
  font-size: 12.5px;
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.draft-actions {
  display: flex;
  gap: 4px;
}
</style>
