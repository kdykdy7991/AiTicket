<template>
  <div class="drafts-view">
    <div class="page-header">
      <div>
        <h2 class="page-title">我的草稿</h2>
        <p class="page-subtitle">继续填写尚未提交的工单</p>
      </div>
      <el-button type="primary" class="create-btn" @click="router.push({ name: 'TicketCreate' })">＋ 新建工单</el-button>
    </div>

    <section v-loading="loading" class="drafts-card" aria-label="草稿列表">
      <div class="card-heading"><span class="heading-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg></span><strong>草稿列表</strong><span class="draft-count">{{ drafts.length }}</span><small>DRAFT TICKETS</small></div>
      <template v-if="drafts.length === 0 && !loading">
        <div class="empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
          </svg>
          <p class="empty-text">暂无草稿</p>
          <span>新建工单时选择「保存草稿」，就能在这里继续填写</span>
        </div>
      </template>

      <template v-else>
        <div class="drafts-list">
          <div class="draft-list-header"><span>客户 / 分类</span><span>最后更新</span><span>操作</span></div>
          <div
            v-for="draft in drafts"
            :key="draft.id"
            class="draft-item"
          >
            <button type="button" class="draft-main" @click="onEdit(draft.id)">
              <span class="draft-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M16 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8Z"/><polyline points="14,3 14,8 21,8"/></svg></span>
              <span class="draft-left"><strong class="draft-customer">{{ draft.customer_name || '未填写客户' }}</strong><span class="draft-category">{{ [draft.category_l1_name, draft.category_l2_name].filter(Boolean).join(' / ') || '未选择分类' }}</span></span>
              <span class="draft-time">{{ formatTime(draft.updated_at) }}</span>
              <span class="draft-edit">继续编辑 <span aria-hidden="true">›</span></span>
            </button>
            <div class="draft-actions">
              <el-button size="small" text @click="onDelete(draft.id)">删除</el-button>
            </div>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTicketStore } from '@/stores/ticket'
import { ElMessage, ElMessageBox } from 'element-plus'

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

async function onDelete(id: number) {
  try {
    await ElMessageBox.confirm('确认删除此草稿？', '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
      customClass: 'ticket-dark-dialog',
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
.drafts-view { width: 100%; min-height: calc(100vh - 120px); color: #eaf4ff; }
.page-header { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin: 4px 0 20px; }
.page-title { margin: 0; color: #f1f8ff; font-size: 28px; font-weight: 700; text-shadow: 0 0 17px #40aaff38; }
.page-subtitle { margin: 7px 0 0; color: #91b6d4; font-size: 13px; }
.create-btn { height: 40px; min-width: 126px; font-weight: 600; }
.drafts-card { overflow: hidden; min-height: 280px; border: 1px solid #176496; border-radius: 9px; background: linear-gradient(110deg, #082646, #061d39 78%); box-shadow: 0 0 14px #0064ae35; }
.card-heading { position: relative; display: flex; align-items: center; gap: 11px; min-height: 62px; margin: 0 24px; border-bottom: 1px solid #17527d; }
.card-heading::after { content: ''; position: absolute; left: 0; bottom: -2px; width: 48px; height: 3px; border-radius: 3px; background: #159df5; box-shadow: 0 0 12px #189cff; }
.card-heading strong { color: #edf7ff; font-size: 19px; }
.card-heading small { margin-left: auto; color: #2c9be9; font-size: 10px; letter-spacing: .08em; }
.heading-icon { width: 23px; height: 23px; color: #62bfff; filter: drop-shadow(0 0 5px #168eef); }
.heading-icon svg, .draft-icon svg { width: 100%; height: 100%; }
.draft-count { padding: 2px 8px; border: 1px solid #1a659a; border-radius: 4px; background: #0a3156; color: #8ed4ff; font-size: 12px; }
.drafts-list { padding: 10px 24px 20px; }
.draft-list-header { display: grid; grid-template-columns: minmax(0, 1fr) 150px 150px; padding: 10px 16px; color: #91b7d7; font-size: 12px; }
.draft-list-header span:last-child { text-align: right; }
.draft-item { display: flex; align-items: center; min-height: 68px; border-top: 1px solid #17466d; transition: background .16s; }
.draft-item:hover { background: #0a3154; }
.draft-main { display: grid; grid-template-columns: 38px minmax(0, 1fr) 150px 95px; align-items: center; gap: 14px; flex: 1; min-width: 0; padding: 12px 16px; border: 0; background: transparent; color: inherit; cursor: pointer; text-align: left; font: inherit; }
.draft-main:focus-visible, .draft-actions :deep(.el-button:focus-visible) { outline: 2px solid #50baff; outline-offset: -2px; }
.draft-icon { display: grid; place-items: center; width: 38px; height: 38px; padding: 9px; box-sizing: border-box; border: 1px solid #185b8a; border-radius: 6px; background: #0b3459; color: #83cfff; }
.draft-left { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.draft-customer { overflow: hidden; color: #eef7ff; font-size: 14px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.draft-category { overflow: hidden; color: #91b7d7; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.draft-time { color: #aac8e2; font-size: 13px; white-space: nowrap; }
.draft-edit { color: #69c2ff; font-size: 13px; font-weight: 600; white-space: nowrap; }
.draft-edit span { padding-left: 4px; font-size: 18px; vertical-align: -1px; }
.draft-actions { width: 55px; padding-right: 16px; text-align: right; }
.draft-actions :deep(.el-button) { color: #f2aab5; }
.draft-actions :deep(.el-button:hover) { background: #4b1f34; color: #ffc5ce; }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 215px; padding: 30px 20px; color: #91b7d7; text-align: center; }
.empty-state svg { margin-bottom: 12px; color: #3ba9f4; opacity: .65; filter: drop-shadow(0 0 8px #0e83d9); }
.empty-text { margin: 0 0 8px; color: #e2f2ff; font-size: 16px; font-weight: 600; }
.empty-state > span { font-size: 13px; line-height: 1.5; }
@media (max-width: 720px) { .drafts-list { padding: 8px 14px 16px; } .card-heading { margin: 0 14px; } .draft-list-header { display: none; } .draft-main { grid-template-columns: 38px minmax(0, 1fr); gap: 8px 12px; } .draft-time { grid-column: 2; } .draft-edit { display: none; } .draft-actions { width: auto; padding-right: 10px; } }
@media (max-width: 480px) { .page-header { align-items: flex-start; } .page-title { font-size: 24px; } .create-btn { min-width: 0; padding: 0 10px; font-size: 12px; } .card-heading small { display: none; } }
</style>
