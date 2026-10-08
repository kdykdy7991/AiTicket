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
            <!-- V0.21：转派（链推进一步） -->
            <el-button
              v-if="transferAction"
              type="primary"
              size="small"
              class="header-action-btn"
              @click="openTransferDialog"
            >转派</el-button>
            <el-button v-if="canReturn" type="danger" size="small" class="header-action-btn" @click="openReturnDialog">退 回</el-button>
            <el-button v-if="canCancel" type="danger" size="small" class="header-action-btn" @click="openCancelDialog">撤销</el-button>
          </div>
        </div>
      </div>

      <div class="detail-body">
        <div class="detail-main">
          <div class="sidebar-card flow-card">
            <h3 class="timeline-section-title"><svg class="section-title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="12" r="2"/><path d="M6 7v10M8 5h4a6 6 0 0 1 6 5"/></svg>处理流程</h3>
            <StateLogTimeline :logs="ticket.state_logs || []" :current-owner-name="(ticket as any).owner_name || ''" />
          </div>
          <div v-if="(ticket as any).description" class="ticket-description">
            <h3 class="ticket-description-label"><svg class="section-title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h9l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M15 3v5h4M8 12h8M8 16h6"/></svg>问题描述</h3>
            <div class="ticket-description-body">{{ (ticket as any).description }}</div>
          </div>

          <!-- 处理记录：内容性信息（处理说明/补充/催办/附件/归档回访） -->
          <div v-if="hasContentRecords" class="timeline-card">
            <h3 class="timeline-section-title"><svg class="section-title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4.5V3h6v1.5M9 10h6M9 14h6M9 18h4"/></svg>处理记录</h3>
            <TicketContentRecords
              :ticket="ticket"
              :replies="(ticket.articles || []).filter(a => a.type === 'reply')"
              :additions="(ticket.articles || []).filter(a => a.type === 'addition')"
              :reminders="(ticket.articles || []).filter(a => a.type === 'reminder')"
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
              <el-radio-group v-model="callbackChoice">
                <el-radio label="call_backed">已回访</el-radio>
                <el-radio label="no_need">无需回访</el-radio>
              </el-radio-group>
              <!-- 已回访时显示满意度：满意/一般/不满意，必填 -->
              <el-radio-group v-if="callbackChoice === 'call_backed'" v-model="satisfaction" class="satisfaction-group">
                <span class="satisfaction-label">满意度：</span>
                <el-radio :label="'satisfied'">满意</el-radio>
                <el-radio :label="'average'">一般</el-radio>
                <el-radio :label="'dissatisfied'">不满意</el-radio>
                <el-radio :label="'unrated'">未评价</el-radio>
              </el-radio-group>
              <!-- 不满意原因（后端 unsatisfied_reason，dissatisfied 必填，V0.87 收尾） -->
              <el-input
                v-if="callbackChoice === 'call_backed' && satisfaction === 'dissatisfied'"
                v-model="unsatisfiedReason"
                type="textarea"
                :rows="2"
                placeholder="客户不满意原因（必填）"
                maxlength="500"
                show-word-limit
              />
              <!-- 回访详情（不满意原因为其中必填场景），后端 callback_details 字段 -->
              <el-input
                v-if="callbackChoice === 'call_backed'"
                v-model="callbackDetails"
                type="textarea"
                :rows="2"
                :placeholder="satisfaction === 'dissatisfied' ? '请填写客户不满意原因 / 回访记录（必填）' : '回访详情 / 客户反馈（可选）'"
                maxlength="500"
                show-word-limit
              />
              <!-- 闭环规则：不满意不能直接归档（后端 enforced + allowed_actions 不下发） -->
              <p v-if="callbackChoice === 'call_backed' && satisfaction === 'dissatisfied'" class="dissatisfied-hint">
                客户不满意不能直接归档。点击「保存回访结果」记录后，请通过顶部「退回」让处理人重新处理，
                处理完成并再次回访后才能归档。
              </p>
              <div class="archive-actions">
                <el-button
                  type="success"
                  :loading="archiving"
                  :disabled="archiveDisabled"
                  @click="submitArchive"
                >
                  {{ satisfaction === 'dissatisfied' && callbackChoice === 'call_backed' ? '保存回访结果' : '归档' }}
                </el-button>
              </div>
            </div>
          </div>

          <!-- 当前判断人的正常处理动作，选分类后按分派链流转。 -->
          <div v-if="canRefine" class="refine-card">
            <div class="refine-card-title">下一级问题判断</div>
            <p class="refine-card-hint">请选择最符合当前问题的分类，确认后将按对应分派链继续流转。</p>
            <div class="refine-options">
              <button
                v-for="option in refineOptions"
                :key="option.id"
                type="button"
                class="refine-option"
                :disabled="refining"
                @click="onPickRefineCategory(option.id)"
              >
                <span>{{ option.name }}</span>
                <span class="refine-option-next">{{ option.next_department ? `流转至${option.next_department}` : '当前部门继续处理' }}</span>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
              </button>
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
            v-if="!isTerminalState && (ticket.can_reply || ticket.can_addition || ticket.can_remind)"
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
          <TicketOverview :ticket="ticket" />
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

      <!-- 转派弹窗：链本步完成，推进到下一部门 -->
      <el-dialog v-model="transferDialogVisible" title="转派" width="440px" top="15vh" :close-on-click-modal="false">
        <p class="dialog-hint">
          本步处理完成，工单将按分派链转派至下一部门{{ nextDeptName ? `：「${nextDeptName}」` : '' }}。
        </p>
        <el-input v-model="transferReason" type="textarea" :rows="2" placeholder="转派说明（选填，留空自动填写「本步完成，转派下一部门」）" maxlength="500" show-word-limit />
        <template #footer>
          <el-button @click="transferDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="transferring" @click="confirmTransfer">确认转派</el-button>
        </template>
      </el-dialog>

    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTicketStore } from '@/stores/ticket'
import { metaApi } from '@/api/overviews'
import { ticketApi } from '@/api/tickets'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { Group, AllowedAction } from '@/types'
import StateTag from '@/components/common/StateTag.vue'
import ArticleTimeline from '@/components/ticket/ArticleTimeline.vue'
import ReplyEditor from '@/components/ticket/ReplyEditor.vue'
import TicketOverview from '@/components/ticket/TicketOverview.vue'
import StateLogTimeline from '@/components/ticket/StateLogTimeline.vue'
import TicketContentRecords from '@/components/ticket/TicketContentRecords.vue'

const route = useRoute()
const router = useRouter()
const ticketStore = useTicketStore()

const ticket = computed(() => ticketStore.currentTicket)
const hasContentRecords = computed(() => {
  const t = ticket.value as any
  if (!t) return false
  const hasArticle = (t.articles || []).some((article: any) =>
    ['reply', 'addition', 'reminder'].includes(article.type),
  )
  return hasArticle || t.state === 'archived' || !!t.archive_notes ||
    t.is_callbacked === true || !!t.satisfaction ||
    !!t.callback_details || !!t.unsatisfied_reason
})

// ── V0.86：所有按钮可见性来自后端 allowed_actions（唯一事实来源）──
// 后端按 TRANSITIONS + 权限矩阵 + requires_reason + 业务约束改写生成；
// 前端只做渲染与取 target_state，不再自行判断状态/角色/人员规则。
const allowedActions = computed<AllowedAction[]>(
  () => (ticket.value as any)?.allowed_actions ?? [],
)
const findAction = (name: string): AllowedAction | undefined =>
  allowedActions.value.find(a => a.action === name)

const isTerminalState = computed(() => (ticket.value as any)?.is_terminal ?? false)

// 显示「指派处理人」卡片：后端允许 dispatch（对接人/admin + 目标状态由后端给出）
const canDispatch = computed(() => !!findAction('dispatch'))

// 顶部「退回」按钮承载三种后端动作：
//   return  —— pending→returned / open→pending（打回）
//   reopen  —— resolved→open（已处理退回重开）
//   resume  —— on_hold→open（恢复处理，沿用原退回弹窗与原因必填）
const returnAction = computed<AllowedAction | undefined>(
  () => findAction('return') || findAction('reopen') || findAction('resume'),
)
const canReturn = computed(() => !!returnAction.value)

const canCancel = computed(() => !!findAction('cancel'))
const canArchiveFromResolved = computed(() => !!findAction('archive'))
const canResubmit = computed(() => !!findAction('resubmit'))

// ── V0.21 分派链快照：进度条与转派弹窗的"下一部门"提示 ──
const chainSteps = computed<{ order: number; department_code: string }[]>(
  () => (ticket.value as any)?.dispatch_chain_steps ?? [],
)
const currentStepIndex = computed(() => (ticket.value as any)?.dispatch_step_index ?? 0)
const nextDeptName = computed(
  () => chainSteps.value[currentStepIndex.value + 1]?.department_code ?? '',
)

// ── 问题判断（原「分诊」）：能力位与选项全部来自后端 can_refine / refine_options ──
// 后端已判定「状态允许 + 当前账号是该分类链首部门的判断人」，前端不再重复判断，
// 无权限时整个控件不渲染。
const canRefine = computed<boolean>(() => (ticket.value as any)?.can_refine === true)
const refineOptions = computed<
  { id: number; name: string; level?: number; next_department?: string | null }[]
>(() => (ticket.value as any)?.refine_options ?? [])
const refining = ref(false)

/**
 * 选择分类 = 完成一次问题判断。分类只能向下细分一级且不可回退，
 * 同时会按新分类重新落位责任部门，故提交前二次确认。
 */
async function onPickRefineCategory(categoryId: number) {
  const opt = refineOptions.value.find(o => o.id === categoryId)
  if (!opt) return
  const nextDept = opt.next_department
  const tip = nextDept
    ? `将把问题分类细化为「${opt.name}」，并重新落位至「${nextDept}」。此操作不可回退。`
    : `将把问题分类细化为「${opt.name}」。此操作不可回退。`
  try {
    await ElMessageBox.confirm(tip, '确认问题分类', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error('确认框打开失败，请重试')
    }
    return
  }
  refining.value = true
  try {
    await ticketApi.refine((ticket.value as any).id, categoryId)
    ElMessage.success('分类已更新，责任部门已重新落位')
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '分类更新失败')
  } finally {
    refining.value = false
  }
}

// ── 转派（transfer）：后端 allowed_actions 下发的链推进动作 ──
const transferAction = computed<AllowedAction | undefined>(() => findAction('transfer'))
const transferDialogVisible = ref(false)
const transferReason = ref('')
const transferring = ref(false)

function openTransferDialog() {
  transferReason.value = ''
  transferDialogVisible.value = true
}

async function confirmTransfer() {
  transferring.value = true
  try {
    await ticketApi.transfer((ticket.value as any).id, transferReason.value.trim())
    ElMessage.success('已转派至下一部门')
    transferDialogVisible.value = false
    ticketStore.refreshCurrentInList()
    await loadTicket()
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '转派失败')
  } finally {
    transferring.value = false
  }
}

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
      state: findAction('dispatch')?.target_state || 'open',
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
// 回访选择：'call_backed'=已回访（is_callbacked=true），'no_need'=无需回访（callback_required=false）
const callbackChoice = ref<'call_backed' | 'no_need'>('no_need')
const satisfaction = ref<'satisfied' | 'average' | 'dissatisfied' | 'unrated' | ''>('')
// 回访详情（不满意原因）：后端 callback_details 字段，不满意时必填
const callbackDetails = ref('')
// 不满意原因（后端 unsatisfied_reason，V0.87 收尾：dissatisfied 必填）
const unsatisfiedReason = ref('')

// 归档按钮禁用条件：已回访必须选满意度；不满意必须填写不满意原因与回访详情
const archiveDisabled = computed(() => {
  if (callbackChoice.value === 'call_backed' && !satisfaction.value) return true
  if (
    callbackChoice.value === 'call_backed'
    && satisfaction.value === 'dissatisfied'
    && !unsatisfiedReason.value.trim()
  ) return true
  if (
    callbackChoice.value === 'call_backed'
    && satisfaction.value === 'dissatisfied'
    && !callbackDetails.value.trim()
  ) return true
  return false
})

watch(canArchiveFromResolved, (visible) => {
  if (!visible) {
    archiveNotes.value = ''
    callbackChoice.value = 'no_need'
    satisfaction.value = ''
    callbackDetails.value = ''
    unsatisfiedReason.value = ''
  } else {
    const t = ticket.value as any
    archiveNotes.value = t?.archive_notes || ''
    callbackChoice.value = t?.is_callbacked ? 'call_backed' : 'no_need'
    satisfaction.value = t?.satisfaction || ''
    callbackDetails.value = t?.callback_details || ''
    unsatisfiedReason.value = t?.unsatisfied_reason || ''
  }
}, { immediate: true })

async function submitArchive() {
  const t = ticket.value as any
  const callBacked = callbackChoice.value === 'call_backed'
  const isDissatisfied = callBacked && satisfaction.value === 'dissatisfied'
  archiving.value = true
  try {
    if (isDissatisfied) {
      // 闭环规则：不满意不能直接归档 —— 只保存回访结果（含不满意原因），
      // 保存后后端 allowed_actions 将隐藏归档动作，需通过「退回」重开处理
      await ticketStore.updateTicket(t.id, {
        is_callbacked: true,
        callback_required: true,
        satisfaction: satisfaction.value,
        unsatisfied_reason: unsatisfiedReason.value.trim(),
        callback_details: callbackDetails.value.trim(),
      } as any)
      ElMessage.warning('已记录回访结果：客户不满意，请通过「退回」让处理人重新处理')
    } else {
      await ticketStore.updateTicket(t.id, {
        state: findAction('archive')?.target_state || 'archived',
        archive_notes: archiveNotes.value.trim(),
        callback_required: callBacked,  // 已回访→true(需要回访已落实)；无需回访→false
        is_callbacked: callBacked,
        satisfaction: callBacked ? satisfaction.value : undefined,
        callback_details: callBacked ? callbackDetails.value.trim() : undefined,
      } as any)
      ElMessage.success('工单已归档')
    }
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
      state: findAction('resubmit')?.target_state || 'pending',
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

async function confirmReturn() {
  if (!returnReason.value.trim()) {
    ElMessage.warning('请填写退回原因')
    return
  }
  const action = returnAction.value
  if (!action) {
    ElMessage.warning('当前状态不允许退回')
    return
  }
  returning.value = true
  try {
    // 目标状态由后端 allowed_actions 给出（含 resolved→on_hold→open 业务约束改写）
    await ticketStore.updateTicket((ticket.value as any).id, {
      state: action.target_state,
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
      state: findAction('cancel')?.target_state || 'cancelled',
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
  font-size: 24px;
  color: var(--color-text-primary);
  font-weight: 700;
  letter-spacing: -0.02em;
}

.ticket-description {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 16px;
}

.ticket-description-label,
.timeline-section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0 0 20px;
}
.section-title-icon { width: 19px; height: 19px; flex: none; color: var(--color-primary); }

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
  width: min(420px, 38%);
  flex-shrink: 0;
  align-self: flex-start;
  position: sticky;
  top: 20px;
  max-height: calc(100vh - 40px);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.detail-sidebar :deep(.overview-card) { padding: 20px; }
.detail-sidebar :deep(.overview-grid) { grid-template-columns: minmax(0, 1fr); gap: 14px; }
.detail-sidebar :deep(.info-column) { gap: 14px; }
.detail-sidebar :deep(.info-column + .info-column) { border-left: 0; padding-left: 0; }
.detail-sidebar :deep(.info-row) { grid-template-columns: 104px minmax(0, 1fr); gap: 10px; }
.detail-sidebar :deep(.section-divider) { margin-top: 20px; padding-top: 20px; }
.sidebar-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
  padding: 20px;
}
.flow-card :deep(.timeline-item) { padding-bottom: 22px; }
.flow-card :deep(.action-operator) { margin-top: 4px; }
.flow-card :deep(.timeline-marker) { width: 14px; }
.flow-card :deep(.marker-dot) { width: 10px; height: 10px; }
.flow-card :deep(.is-current .marker-dot) { background: var(--color-primary); }
.flow-card :deep(.is-current .action-name) { color: var(--color-text-primary); }
.flow-card :deep(.current-tag) { color: var(--color-primary); }

@media (max-width: 900px) {
  .detail-body { flex-direction: column; }
  .detail-sidebar { width: auto; position: static; max-height: none; overflow: visible; }
}

.timeline-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 16px;
}


/* 判断动作与指派动作放在同一处理区域。 */
.refine-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-lg);
  padding: 16px;
  box-shadow: 0 0 0 3px rgba(99, 91, 255, 0.08);
}
.refine-card-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-primary);
}
.refine-card-hint {
  margin: 6px 0 14px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.refine-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.refine-option {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 3px 8px;
  align-items: center;
  text-align: left;
  padding: 11px 12px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-bg-card);
  color: var(--color-text-primary);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.18s, background 0.18s;
}
.refine-option:hover:not(:disabled), .refine-option:focus-visible {
  border-color: var(--color-primary);
  background: rgba(99, 91, 255, 0.06);
  outline: none;
}
.refine-option:disabled { opacity: 0.6; cursor: wait; }
.refine-option-next {
  grid-column: 1;
  color: var(--color-text-tertiary);
  font-size: 11px;
  font-weight: 400;
}
.refine-option svg { grid-column: 2; grid-row: 1 / 3; color: var(--color-primary); }

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
.dissatisfied-hint {
  margin: 6px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: #e6a23c;
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
