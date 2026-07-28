<template>
  <div class="reply-editor">
    <template v-if="canReply || canAppend || canRemind">
      <div class="reply-tab-bar">
        <button
          v-if="canReply"
          class="tab-btn"
          :class="{ active: activeTab === 'reply' }"
          @click="activeTab = 'reply'"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9,17 4,12 9,7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/></svg>
          处理说明
        </button>
        <button
          v-if="canAppend"
          class="tab-btn"
          :class="{ active: activeTab === 'addition' }"
          @click="activeTab = 'addition'"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          补充
        </button>
        <button
          v-if="canRemind"
          class="tab-btn"
          :class="{ active: activeTab === 'reminder' }"
          @click="activeTab = 'reminder'"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          催办
        </button>
      </div>

      <div
        class="reply-input-area"
        :class="{
          addition: activeTab === 'addition',
          reminder: activeTab === 'reminder',
        }"
      >
        <el-input
          v-model="body"
          type="textarea"
          :rows="4"
          :placeholder="placeholder"
          :disabled="inputDisabled"
          resize="vertical"
          @paste="onPaste"
        />
      </div>

      <!-- 追加模式：图片附件上传 -->
      <div v-if="activeTab === 'addition'" class="attachment-area">
        <input
          ref="fileInput"
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          multiple
          style="display: none"
          @change="onFileSelected"
        />
        <el-button size="small" @click="fileInput?.click()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
          选择图片
        </el-button>
        <span class="attachment-hint">支持截图粘贴（Ctrl+V）</span>

        <div v-if="attachmentFiles.length" class="attachment-preview-list">
          <div
            v-for="(file, idx) in attachmentFiles"
            :key="idx"
            class="attachment-thumb"
          >
            <img :src="previewUrls[idx]" :alt="file.name" />
            <button class="remove-btn" @click="removeAttachment(idx)">×</button>
          </div>
        </div>
      </div>

      <!-- 当前状态下已有处理说明 -->
      <div v-if="activeTab === 'reply' && hasSummary" class="disabled-hint">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        当前状态下已提交处理说明，流转到下一状态后可继续补充。
      </div>

      <!-- 追加模式：必须填追加原因 -->
      <div v-if="activeTab === 'addition'" class="addition-reason">
        <label class="reason-label">补充原因 <span class="required">*</span></label>
        <el-input
          v-model="appendReason"
          placeholder="请说明此次补充的原因"
          size="small"
          maxlength="200"
          show-word-limit
        />
      </div>

      <div class="reply-actions">
        <span v-if="activeTab === 'addition'" class="addition-hint">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
          补充记录会保留在工单时间线，标注为补充内容
        </span>
        <span v-if="activeTab === 'reminder'" class="addition-hint reminder-hint">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
          催办后该工单将在列表中置顶，每个工单只能催办一次
        </span>
        <div class="reply-actions-right">
          <el-button
            v-if="canHold"
            class="hold-btn"
            @click="openHoldDialog"
          >
            暂缓处理
          </el-button>
          <el-button
            type="primary"
            :loading="submitting"
            @click="onSubmit"
            class="send-btn"
          >
            {{ submitLabel }}
          </el-button>
        </div>
      </div>
    </template>

    <div v-if="!(canReply || canAppend || canRemind)" class="disabled-hint no-perm">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
      您当前无权在该工单提交处理说明、补充或催办。
    </div>

    <!-- 暂缓处理弹窗 -->
    <el-dialog
      v-model="holdDialogVisible"
      title="暂缓处理"
      width="420px"
      top="15vh"
      :close-on-click-modal="false"
    >
      <div class="hold-form">
        <p class="hold-hint">暂缓后工单将进入「暂缓处理」状态，处理人保持不变。</p>
        <el-form-item label="暂缓原因" required style="margin-top: 12px">
          <el-input
            v-model="holdReason"
            type="textarea"
            :rows="3"
            placeholder="请填写暂缓原因"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </div>
      <template #footer>
        <el-button @click="holdDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="holding" :disabled="!holdReason.trim()" @click="confirmHold">确认暂缓</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useTicketStore } from '@/stores/ticket'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import type { Article, ArticleCreatePayload, TicketDetail } from '@/types'

const props = defineProps<{
  ticket: TicketDetail
  articles: Article[]
}>()
const emit = defineEmits<{ submitted: [] }>()

const ticketStore = useTicketStore()
const authStore = useAuthStore()
const activeTab = ref<'reply' | 'addition' | 'reminder'>('reply')
const body = ref('')
const appendReason = ref('')
const submitting = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const attachmentFiles = ref<File[]>([])
const previewUrls = ref<string[]>([])

const currentStateKey = computed(() => (props.ticket as any).state_key || '')
const allowedAdditionStates = ['pending', 'open', 'on_hold']
const replyAllowedStates = ['open', 'on_hold']
const reminderAllowedStates = ['pending', 'open', 'on_hold']

const currentUserId = computed(() => (authStore.user as any)?.id)
const isOwner = computed(() => (props.ticket as any).owner_id === currentUserId.value)

// 是否具备提交处理说明权限：当前处理人，且工单处于处理中/暂缓
const canReply = computed(() =>
  isOwner.value && replyAllowedStates.includes(currentStateKey.value)
)

// 当前状态对应的状态日志节点 id（后端用 state_log id 作为处理说明的 state_key）
const currentStateLogId = computed(() => {
  const logs = (props.ticket as any)?.state_logs || []
  const current = [...logs].reverse().find((l: any) => l.to_state_key === currentStateKey.value)
  return current?.id ? String(current.id) : currentStateKey.value
})

// 是否已存在处理说明（当前状态下已有 reply）
const hasSummary = computed(() =>
  props.articles.some(a => a.type === 'reply' && a.state_key === currentStateLogId.value)
)

// 是否具备追加权限：admin / agent，且工单状态在已处理之前
const canAppend = computed(() =>
  authStore.isAgent && allowedAdditionStates.includes(currentStateKey.value)
)

// 是否具备催办权限：客服团队（admin / agent），且工单处于待受理/处理中/暂缓，且未催办过
const canRemind = computed(() =>
  authStore.isAgent &&
  reminderAllowedStates.includes(currentStateKey.value) &&
  !(props.ticket as any).urged_at
)

// 是否可暂缓处理：当前处理人，且工单处于处理中
const canHold = computed(() =>
  isOwner.value && currentStateKey.value === 'open'
)

const inputDisabled = computed(() =>
  activeTab.value === 'reply' && hasSummary.value
)

const placeholder = computed(() => {
  if (activeTab.value === 'addition') {
    return '输入补充内容（如：补充截图说明、补充排查信息）...'
  }
  if (activeTab.value === 'reminder') {
    return '请输入催办内容，提交后将通知当前处理人并在时间线记录...'
  }
  if (hasSummary.value) {
    return '当前状态下已提交处理说明'
  }
  return '请输入处理说明，提交后将标记为已处理...'
})

const submitLabel = computed(() => {
  if (activeTab.value === 'addition') return '补充记录'
  if (activeTab.value === 'reminder') return '发起催办'
  return '提交处理说明'
})

// 附件处理
function onFileSelected(e: Event) {
  const target = e.target as HTMLInputElement
  const files = target.files
  if (!files) return
  for (const file of files) {
    if (!file.type.startsWith('image/')) {
      ElMessage.warning(`仅支持图片文件：${file.name}`)
      continue
    }
    addAttachment(file)
  }
  target.value = ''
}

function onPaste(e: ClipboardEvent) {
  if (activeTab.value !== 'addition') return
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) addAttachment(file)
    }
  }
}

function addAttachment(file: File) {
  attachmentFiles.value.push(file)
  previewUrls.value.push(URL.createObjectURL(file))
}

function removeAttachment(idx: number) {
  URL.revokeObjectURL(previewUrls.value[idx])
  attachmentFiles.value.splice(idx, 1)
  previewUrls.value.splice(idx, 1)
}

function clearAttachments() {
  previewUrls.value.forEach(url => URL.revokeObjectURL(url))
  attachmentFiles.value = []
  previewUrls.value = []
}

onUnmounted(clearAttachments)

// 权限变化时自动切到可用的 tab
watch([canReply, canAppend, canRemind], ([replyAllowed, appendAllowed, remindAllowed]) => {
  if (activeTab.value === 'reply' && !replyAllowed) {
    if (appendAllowed) activeTab.value = 'addition'
    else if (remindAllowed) activeTab.value = 'reminder'
  }
  if (activeTab.value === 'addition' && !appendAllowed) {
    if (replyAllowed) activeTab.value = 'reply'
    else if (remindAllowed) activeTab.value = 'reminder'
  }
  if (activeTab.value === 'reminder' && !remindAllowed) {
    if (replyAllowed) activeTab.value = 'reply'
    else if (appendAllowed) activeTab.value = 'addition'
  }
}, { immediate: true })

async function onSubmit() {
  if (activeTab.value === 'reply' && hasSummary.value) {
    ElMessage.warning('当前状态下已提交处理说明')
    return
  }
  if (activeTab.value === 'addition' && !appendReason.value.trim()) {
    ElMessage.warning('请填写补充原因')
    return
  }
  if (activeTab.value === 'reminder' && body.value.trim().length > 200) {
    ElMessage.warning('催办内容最多 200 字')
    return
  }
  const hasBody = !!body.value.trim()
  const hasAttachments = attachmentFiles.value.length > 0
  if (!hasBody && !hasAttachments) {
    ElMessage.warning(activeTab.value === 'addition' ? '请填写补充内容或上传截图' : '请填写内容')
    return
  }

  submitting.value = true
  try {
    const type = activeTab.value
    const payload: ArticleCreatePayload = {
      type,
      body: body.value,
      append_reason: activeTab.value === 'addition' ? appendReason.value.trim() : undefined,
    }
    if (activeTab.value === 'addition' && attachmentFiles.value.length) {
      payload.attachments = attachmentFiles.value
    }
    await ticketStore.addArticle(props.ticket.id, payload)
    body.value = ''
    appendReason.value = ''
    clearAttachments()
    const msgMap: Record<string, string> = {
      reply: '处理说明已提交',
      addition: '补充已记录',
      reminder: '催办已发起',
    }
    ElMessage.success(msgMap[activeTab.value])
    emit('submitted')
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

// ── 暂缓处理 ──────────────────────────────────────
const holdDialogVisible = ref(false)
const holdReason = ref('')
const holding = ref(false)

function openHoldDialog() {
  holdReason.value = ''
  holdDialogVisible.value = true
}

async function confirmHold() {
  if (!holdReason.value.trim()) {
    ElMessage.warning('请填写暂缓原因')
    return
  }
  holding.value = true
  try {
    await ticketStore.updateTicket((props.ticket as any).id, {
      state: 'on_hold',
      reason: holdReason.value.trim(),
    } as any)
    ElMessage.success('工单已暂缓')
    holdDialogVisible.value = false
    emit('submitted')
  } catch (e: any) {
    const detail = e?.response?.data?.error?.message || e?.response?.data?.detail
    ElMessage.error(detail || '暂缓失败')
  } finally {
    holding.value = false
  }
}
</script>

<style scoped>
.reply-editor {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  background: var(--color-bg-card);
  overflow: hidden;
}

.reply-tab-bar {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--color-divider);
  padding: 0 4px;
}
.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 16px;
  border: none;
  background: none;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-tertiary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all var(--duration-fast) var(--ease-out);
}
.tab-btn:hover { color: var(--color-text-secondary); }
.tab-btn.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }

.reply-input-area { padding: 12px 16px 0; }
.reply-input-area.addition { background: rgba(99, 91, 255, 0.04); }
.reply-input-area.reminder { background: rgba(245, 108, 108, 0.04); }
.reply-input-area :deep(.el-textarea__inner) {
  border: none;
  box-shadow: none;
  padding: 8px 0;
  font-size: 14px;
  line-height: 1.6;
  background: transparent;
}
.reply-input-area :deep(.el-textarea__inner:focus) { box-shadow: none; }

.disabled-hint {
  padding: 12px 16px 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.disabled-hint.no-perm {
  padding: 16px;
}

.addition-reason {
  padding: 12px 16px 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.reason-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
}
.required { color: var(--color-danger); margin-left: 2px; }

.reply-actions {
  padding: 12px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.reply-actions-right {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}

.hold-btn {
  font-weight: 600;
}

.addition-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--color-text-tertiary);
}
.addition-hint.reminder-hint {
  color: var(--color-danger);
}

.send-btn { font-weight: 600; min-width: 100px; }

.attachment-area {
  padding: 12px 16px 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.attachment-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.attachment-preview-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
  margin-top: 4px;
}

.attachment-thumb {
  position: relative;
  width: 80px;
  height: 80px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--color-border-light);
  background: var(--color-bg-page);
}

.attachment-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.attachment-thumb .remove-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.attachment-thumb .remove-btn:hover {
  background: rgba(0, 0, 0, 0.7);
}

.hold-form .hold-hint {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 14px;
}
</style>
