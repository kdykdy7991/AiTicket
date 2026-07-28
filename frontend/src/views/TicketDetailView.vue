<template>
  <div class="ticket-detail-view" v-loading="ticketStore.loading">
    <template v-if="ticket">
      <div class="detail-header">
        <button class="back-btn" @click="router.back()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12,19 5,12 12,5"/>
          </svg>
          返回
        </button>
        <div class="header-meta">
          <span class="ticket-number">{{ ticket.number || '未编号' }}</span>
          <StateTag :state="ticket.state" />
          <div class="header-actions">
            <el-button v-if="canReturn" type="danger" size="small" class="header-action-btn" @click="openReturnDialog">退 回</el-button>
            <el-button v-if="canCancel" type="danger" size="small" class="header-action-btn" @click="openCancelDialog">撤销</el-button>
          </div>
        </div>
      </div>

      <div class="detail-body">
        <div class="detail-main">
          <div v-if="(ticket as any).description" class="ticket-description">
            <div class="ticket-description-label">详细描述</div>
            <div class="ticket-description-body">{{ (ticket as any).description }}</div>
          </div>
          <div class="timeline-card">
            <h3 class="timeline-section-title">流转时间线</h3>
            <StateLogTimeline
              :logs="ticket.state_logs || []"
              :ticket="ticket"
              :additions="(ticket.articles || []).filter(a => a.type === 'addition')"
              :reminders="(ticket.articles || []).filter(a => a.type === 'reminder')"
              :replies="(ticket.articles || []).filter(a => a.type === 'reply')"
            />
          </div>

          <!-- 已退回工单：补充后重新提交 -->
          <div v-if="canResubmit" class="resubmit-card">
            <div class="resubmit-card-title">重新提交工单</div>
            <div class="resubmit-form">
              <el-input
                v-model="supplement"
                type="textarea"
                :rows="3"
                placeholder="补充说明（可选），将作为补充记录保存"
                maxlength="2000"
                show-word-limit
              />
              <div class="resubmit-selects">
                <el-select
                  v-model="resubmitSkillGroupId"
                  placeholder="选择对接部门"
                  :loading="skillGroupsLoading"
                  @change="onResubmitSkillGroupChange"
                >
                  <el-option
                    v-for="g in skillGroups"
                    :key="g.id"
                    :label="g.name"
                    :value="g.id"
                  />
                </el-select>
                <el-select
                  v-model="resubmitDispatcherId"
                  placeholder="选择部门对接人"
                  :loading="dispatchersLoading"
                  filterable
                  :disabled="!resubmitSkillGroupId"
                >
                  <el-option
                    v-for="d in dispatchers"
                    :key="d.id"
                    :label="d.name"
                    :value="d.id"
                  />
                </el-select>
              </div>
              <div class="resubmit-actions">
                <el-button
                  type="primary"
                  :loading="resubmitting"
                  :disabled="!resubmitSkillGroupId || !resubmitDispatcherId"
                  @click="submitResubmit"
                >
                  重新提交
                </el-button>
              </div>
            </div>
          </div>

          <!-- 已处理工单：归档 -->
          <div v-if="canArchiveFromResolved" class="archive-card">
            <div class="archive-card-title">归档工单</div>
            <div class="archive-form">
              <el-input
                v-model="archiveNotes"
                type="textarea"
                :rows="3"
                placeholder="归档说明（可选）"
                maxlength="2000"
                show-word-limit
              />
              <el-radio-group v-model="isCallbacked">
                <el-radio :label="true">已回访</el-radio>
                <el-radio :label="false">未回访</el-radio>
              </el-radio-group>
              <!-- 已回访时显示满意度：满意/一般/不满意，必填 -->
              <el-radio-group v-if="isCallbacked" v-model="satisfaction" class="satisfaction-group">
                <span class="satisfaction-label">满意度：</span>
                <el-radio :label="'satisfied'">满意</el-radio>
                <el-radio :label="'average'">一般</el-radio>
                <el-radio :label="'dissatisfied'">不满意</el-radio>
              </el-radio-group>
              <div class="archive-actions">
                <el-button
                  type="success"
                  :loading="archiving"
                  :disabled="isCallbacked && !satisfaction"
                  @click="submitArchive"
                >
                  归档
                </el-button>
              </div>
            </div>
          </div>

          <!-- 指派处理人（仅部门对接人 + 待受理可见） -->
          <div v-if="canDispatch" class="dispatch-card">
            <div class="dispatch-card-title">指派处理人</div>
            <div class="dispatch-card-body">
              <el-select
                v-model="dispatchOwnerId"
                placeholder="选择处理人"
                class="dispatch-select"
                filterable
                :loading="handlersLoading"
              >
                <el-option
                  v-for="h in dispatchHandlers"
                  :key="h.id"
                  :label="h.name"
                  :value="h.id"
                />
              </el-select>
              <el-button
                type="primary"
                :loading="dispatching"
                :disabled="!dispatchOwnerId"
                @click="confirmDispatch"
              >
                确认指派
              </el-button>
            </div>
            <p class="dispatch-card-hint">指派后工单将变为「处理中」，由所选处理人负责跟进。</p>
          </div>

          <ArticleTimeline :articles="ticket.articles" />
          <ReplyEditor
            v-if="!isTerminalState && currentStateKey !== 'returned'"
            :ticket="ticket"
            :articles="ticket.articles"
            @submitted="onRefresh"
          />
          <div v-else-if="isTerminalState" class="terminal-notice">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
            工单已结束，无法继续提交处理说明。
          </div>
        </div>
        <aside class="detail-sidebar">
          <TicketInfoSidebar :ticket="ticket" />
        </aside>
      </div>

      <!-- 退回弹窗 -->
      <el-dialog v-model="returnDialogVisible" title="退回工单" width="420px" top="15vh" :close-on-click-modal="false">
        <p class="dialog-hint">退回后工单将返回上一状态，处理人也会同步回退。请填写退回原因：</p>
        <el-input v-model="returnReason" type="textarea" :rows="3" placeholder="请填写退回原因" maxlength="500" show-word-limit />
        <template #footer>
          <el-button @click="returnDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="returning" :disabled="!returnReason.trim()" @click="confirmReturn">确认退回</el-button>
        </template>
      </el-dialog>

      <!-- 撤销弹窗 -->
      <el-dialog v-model="cancelDialogVisible" title="撤销工单" width="420px" top="15vh" :close-on-click-modal="false">
        <p class="dialog-hint">撤销后工单状态将变更为「已撤销」，工单闭环。请填写撤销原因：</p>
        <el-input v-model="cancelReason" type="textarea" :rows="3" placeholder="请填写撤销原因" maxlength="500" show-word-limit />
        <template #footer>
          <el-button @click="cancelDialogVisible = false">取消</el-button>
          <el-button type="danger" :loading="cancelling" :disabled="!cancelReason.trim()" @click="confirmCancel">确认撤销</el-button>
        </template>
      </el-dialog>

    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTicketStore } from '@/stores/ticket'
import { useAuthStore } from '@/stores/auth'
import { metaApi } from '@/api/overviews'
import { ElMessage } from 'element-plus'
import type { Group } from '@/types'
import StateTag from '@/components/common/StateTag.vue'
import ArticleTimeline from '@/components/ticket/ArticleTimeline.vue'
import ReplyEditor from '@/components/ticket/ReplyEditor.vue'
import TicketInfoSidebar from '@/components/ticket/TicketInfoSidebar.vue'
import StateLogTimeline from '@/components/ticket/StateLogTimeline.vue'

const route = useRoute()
const router = useRouter()
const ticketStore = useTicketStore()
const authStore = useAuthStore()

const ticket = computed(() => ticketStore.currentTicket)

const TERMINAL_STATES = new Set(['archived', 'cancelled'])
const isTerminalState = computed(() => {
  const key = (ticket.value as any)?.state_key || ''
  return TERMINAL_STATES.has(key)
})

const currentStateKey = computed(() => (ticket.value as any)?.state_key || '')
const currentUserId = computed(() => (authStore.user as any)?.id)

// 是否显示「指派处理人」入口：待受理 + 部门对接人（或 admin）
const canDispatch = computed(() => {
  if (currentStateKey.value !== 'pending') return false
  const t = ticket.value as any
  if (!t) return false
  if (authStore.isAdmin) return true
  return t.dispatcher_id === currentUserId.value
})

// 状态操作权限
const canReturn = computed(() => {
  const t = ticket.value as any
  if (!t) return false
  const state = currentStateKey.value
  if (authStore.isAdmin) return ['pending', 'open', 'on_hold', 'resolved'].includes(state)
  if (state === 'pending') {
    return t.dispatcher_id === currentUserId.value
  }
  if (state === 'open' || state === 'on_hold') {
    return t.owner_id === currentUserId.value
  }
  if (state === 'resolved') {
    // 已处理状态业务上已回到客服侧，创建者或客服均可退回
    return t.creator_id === currentUserId.value || authStore.isAgent
  }
  return false
})

const canCancel = computed(() => {
  const t = ticket.value as any
  if (!t) return false
  const state = currentStateKey.value
  if (!['pending', 'open', 'on_hold', 'returned'].includes(state)) return false
  if (authStore.isAdmin) return true
  // 只有工单发起人（创建者）可撤销
  return t.creator_id === currentUserId.value
})

const canArchiveFromResolved = computed(() => {
  const t = ticket.value as any
  if (!t) return false
  if (currentStateKey.value !== 'resolved') return false
  return authStore.isAdmin || authStore.isAgent
})

const canResubmit = computed(() => {
  const t = ticket.value as any
  if (!t) return false
  if (currentStateKey.value !== 'returned') return false
  if (authStore.isAdmin) return true
  return t.creator_id === currentUserId.value
})

async function loadTicket() {
  const id = Number(route.params.id)
  if (id) await ticketStore.fetchTicketDetail(id)
}

onMounted(loadTicket)
watch(() => route.params.id, loadTicket)

function onRefresh() {
  loadTicket()
}

// ── 指派处理人 ──────────────────────────────────────
const dispatchOwnerId = ref<number | null>(null)
const dispatchHandlers = ref<any[]>([])
const handlersLoading = ref(false)
const dispatching = ref(false)

// 当指派卡片可见时，加载该对接部门的处理人列表
watch(canDispatch, async (visible) => {
  if (!visible) {
    dispatchOwnerId.value = null
    dispatchHandlers.value = []
    return
  }
  const t = ticket.value as any
  dispatchOwnerId.value = null
  await nextTick()
  if (t?.skill_group_id) {
    handlersLoading.value = true
    try {
      dispatchHandlers.value = await metaApi.getHandlers(t.skill_group_id)
    } catch {
      dispatchHandlers.value = []
    } finally {
      handlersLoading.value = false
    }
  } else {
    dispatchHandlers.value = []
  }
}, { immediate: true })

async function confirmDispatch() {
  if (!dispatchOwnerId.value) {
    ElMessage.warning('请选择处理人')
    return
  }
  dispatching.value = true
  try {
    await ticketStore.updateTicket((ticket.value as any).id, {
      state: 'open',
      owner_id: dispatchOwnerId.value,
    } as any)
    ElMessage.success('已指派处理人')
    // 同步刷新列表缓存，避免返回列表页时状态不同步
    ticketStore.refreshCurrentInList()
    // 重新拉取详情，确保状态、处理人、流转时间线等全部同步刷新
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '指派失败')
  } finally {
    dispatching.value = false
  }
}

// ── 状态操作：退回 / 撤销 / 回访 / 归档 / 重新处理 ──────────────────────────────────────
const returnDialogVisible = ref(false)
const returnReason = ref('')
const returning = ref(false)

const cancelDialogVisible = ref(false)
const cancelReason = ref('')
const cancelling = ref(false)

const archiving = ref(false)

// ── 已处理工单归档面板 ──────────────────────────────────────
const archiveNotes = ref('')
const isCallbacked = ref(false)
const satisfaction = ref<'satisfied' | 'average' | 'dissatisfied' | ''>('')

watch(canArchiveFromResolved, (visible) => {
  if (!visible) {
    archiveNotes.value = ''
    isCallbacked.value = false
    satisfaction.value = ''
  } else {
    const t = ticket.value as any
    archiveNotes.value = t?.archive_notes || ''
    isCallbacked.value = t?.is_callbacked ?? false
    satisfaction.value = t?.satisfaction || ''
  }
}, { immediate: true })

async function submitArchive() {
  const t = ticket.value as any
  archiving.value = true
  try {
    await ticketStore.updateTicket(t.id, {
      state: 'archived',
      archive_notes: archiveNotes.value.trim(),
      is_callbacked: isCallbacked.value,
      satisfaction: isCallbacked.value ? satisfaction.value : undefined,
    } as any)
    ElMessage.success('工单已归档')
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '归档失败')
  } finally {
    archiving.value = false
  }
}

const resubmitting = ref(false)

// ── 已退回工单重新提交面板 ──────────────────────────────────────
const supplement = ref('')
const resubmitSkillGroupId = ref<number | null>(null)
const resubmitDispatcherId = ref<number | null>(null)
const skillGroups = ref<Group[]>([])
const dispatchers = ref<any[]>([])
const skillGroupsLoading = ref(false)
const dispatchersLoading = ref(false)

watch(canResubmit, async (visible) => {
  if (!visible) {
    supplement.value = ''
    resubmitSkillGroupId.value = null
    resubmitDispatcherId.value = null
    skillGroups.value = []
    dispatchers.value = []
    return
  }
  const t = ticket.value as any
  skillGroupsLoading.value = true
  try {
    skillGroups.value = await metaApi.getSkillGroups()
    resubmitSkillGroupId.value = t?.skill_group_id ?? null
    resubmitDispatcherId.value = null
    dispatchers.value = []
    if (resubmitSkillGroupId.value) {
      dispatchersLoading.value = true
      dispatchers.value = await metaApi.getDispatchers(resubmitSkillGroupId.value)
      resubmitDispatcherId.value = t?.dispatcher_id ?? null
    }
  } catch {
    skillGroups.value = []
    dispatchers.value = []
  } finally {
    skillGroupsLoading.value = false
    dispatchersLoading.value = false
  }
}, { immediate: true })

async function onResubmitSkillGroupChange() {
  resubmitDispatcherId.value = null
  dispatchers.value = []
  if (!resubmitSkillGroupId.value) return
  dispatchersLoading.value = true
  try {
    dispatchers.value = await metaApi.getDispatchers(resubmitSkillGroupId.value)
  } catch {
    dispatchers.value = []
  } finally {
    dispatchersLoading.value = false
  }
}

async function submitResubmit() {
  if (!resubmitSkillGroupId.value || !resubmitDispatcherId.value) {
    ElMessage.warning('请选择对接部门和部门对接人')
    return
  }
  const t = ticket.value as any
  const reason = supplement.value.trim() || '客服补充后重新提交'
  resubmitting.value = true
  try {
    if (supplement.value.trim()) {
      await ticketStore.addArticle(t.id, {
        type: 'addition',
        body: supplement.value.trim(),
        append_reason: '退回补充说明',
      })
    }
    await ticketStore.updateTicket(t.id, {
      state: 'pending',
      skill_group_id: resubmitSkillGroupId.value,
      dispatcher_id: resubmitDispatcherId.value,
      reason,
    })
    ElMessage.success('工单已重新提交')
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '重新提交失败')
  } finally {
    resubmitting.value = false
  }
}

function openReturnDialog() {
  returnReason.value = ''
  returnDialogVisible.value = true
}

// 根据当前状态确定退回目标状态
// 约束：resolved → on_hold 不允许（on_hold 是暂停位，回退后无人 unpause
// 就会卡住）。如果上一步是 on_hold，跳过它，退回到进入 on_hold 之前的状态。
// 后端 _enforce_business_constraints 也会兜底做相同改写，防非前端路径绕过。
function resolveReturnTarget(): string {
  const state = currentStateKey.value
  if (state === 'pending') return 'returned'
  if (state === 'open') return 'pending'
  if (state === 'on_hold') return 'open'
  if (state === 'resolved') {
    const logs: any[] = (ticket.value as any)?.state_logs || []
    // 倒序找最近一次进入 resolved 的 log
    const resolvedLog = [...logs].reverse().find((l: any) => l.to_state_key === 'resolved')
    let target = resolvedLog?.from_state_key
    // 如果上一步是 on_hold，跳过它，找"进入 on_hold 之前"的状态
    if (target === 'on_hold' && resolvedLog) {
      const onHoldLog = [...logs].reverse().find(
        (l: any) => l.to_state_key === 'on_hold' && l.created_at < resolvedLog.created_at
      )
      target = onHoldLog?.from_state_key
    }
    return target || 'open'
  }
  return state
}

async function confirmReturn() {
  if (!returnReason.value.trim()) {
    ElMessage.warning('请填写退回原因')
    return
  }
  returning.value = true
  try {
    const targetState = resolveReturnTarget()
    await ticketStore.updateTicket((ticket.value as any).id, {
      state: targetState,
      reason: returnReason.value.trim(),
    } as any)
    ElMessage.success('工单已退回')
    returnDialogVisible.value = false
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '退回失败')
  } finally {
    returning.value = false
  }
}

function openCancelDialog() {
  cancelReason.value = ''
  cancelDialogVisible.value = true
}

async function confirmCancel() {
  if (!cancelReason.value.trim()) {
    ElMessage.warning('请填写撤销原因')
    return
  }
  cancelling.value = true
  try {
    await ticketStore.updateTicket((ticket.value as any).id, {
      state: 'cancelled',
      reason: cancelReason.value.trim(),
    } as any)
    ElMessage.success('工单已撤销')
    cancelDialogVisible.value = false
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '撤销失败')
  } finally {
    cancelling.value = false
  }
}

</script>

<style scoped>
.detail-header {
  margin-bottom: 28px;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-tertiary);
  font-size: 13px;
  font-weight: 500;
  border: none;
  background: none;
  cursor: pointer;
  padding: 4px 0;
  font-family: var(--font-sans);
  transition: color var(--duration-fast) var(--ease-out);
  margin-bottom: 16px;
}
.header-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.accept-btn {
  flex-shrink: 0;
}
.back-btn:hover {
  color: var(--color-primary);
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.header-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.dialog-hint {
  margin: 0 0 12px;
  color: var(--color-text-secondary);
  font-size: 14px;
  line-height: 1.6;
}

.ticket-number {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 13px;
  color: var(--color-text-tertiary);
  font-weight: 500;
}

.ticket-description {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 16px;
}

.ticket-description-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 10px;
}

.ticket-description-body {
  font-size: 14px;
  color: var(--color-text-primary);
  line-height: 1.7;
  white-space: pre-wrap;
}

.detail-body {
  display: flex;
  gap: 24px;
}
.detail-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
.detail-sidebar {
  width: 320px;
  flex-shrink: 0;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  align-self: flex-start;
  position: sticky;
  top: 20px;
  box-shadow: var(--shadow-xs);
}

.timeline-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 16px;
}

.timeline-section-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 0 0 12px;
}

.terminal-notice {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  color: var(--color-text-tertiary);
  font-size: 14px;
}

.dispatch-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-lg);
  padding: 16px;
  box-shadow: 0 0 0 3px rgba(99, 91, 255, 0.08);
}

.dispatch-card-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 12px;
}

.dispatch-card-body {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dispatch-select {
  flex: 1;
}

.dispatch-card-hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.resubmit-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-lg);
  padding: 16px;
  box-shadow: 0 0 0 3px rgba(99, 91, 255, 0.08);
}

.resubmit-card-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 12px;
}

.resubmit-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.resubmit-selects {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.resubmit-actions {
  display: flex;
  justify-content: flex-end;
}

.archive-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-success);
  border-radius: var(--radius-lg);
  padding: 16px;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.08);
}

.archive-card-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 12px;
}

.archive-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.archive-actions {
  display: flex;
  justify-content: flex-end;
}

.satisfaction-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.satisfaction-label {
  color: var(--color-text-tertiary);
  font-size: 12.5px;
  margin-right: 6px;
}

.header-action-btn {
  min-width: 120px;
  height: 34px;
  padding: 0 20px;
  font-size: 15px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
</style>
