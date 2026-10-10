<template>
  <!-- 已完成的操作按日志展示；当前待办根据工单状态单独接在末尾。 -->
  <div class="timeline">
    <div v-if="nodes.length === 0" class="empty">暂无流转记录</div>
    <div
      v-for="(node, index) in nodes"
      :key="node.key"
      class="timeline-item"
      :class="{ 'is-first': index === 0 }"
    >
      <div class="timeline-marker">
        <div class="marker-dot" />
        <div v-if="index < nodes.length - 1 || currentStage" class="marker-line" />
      </div>
      <div class="timeline-content">
        <div class="timeline-head">
          <span class="action-name">{{ actionName(node.log) }}</span>
          <span class="action-time">
            <DateTimeLabel :iso="node.ts" />
          </span>
        </div>
        <div v-if="responsibleName(node.log)" class="action-operator">
          {{ responsibleLabel(node.log) }}：{{ responsibleName(node.log) }}
        </div>
        <div v-for="article in articlesByLog?.get(node.log.id) || []" :key="article.id" class="node-reply">
          <div class="node-record-head">
            <span class="node-reply-label">{{ articleLabel(article.type) }}<span v-if="article.origin_by?.firstname"> · {{ article.origin_by.firstname }}</span></span>
            <DateTimeLabel :iso="article.created_at" />
          </div>
          <div v-if="article.body" class="node-reply-body">{{ article.body }}</div>
          <div v-if="article.append_reason" class="node-record-note">补充原因：{{ article.append_reason }}</div>
          <div v-if="article.attachments?.length" class="node-attachments">
            <a v-for="att in article.attachments" :key="att.id" :href="att.url" target="_blank" :title="att.original_filename">
              <img :src="att.url" :alt="att.original_filename" />
            </a>
          </div>
        </div>
        <div v-if="closureLogId === node.log.id" class="node-reply">
          <div class="node-record-head">
            <span class="node-reply-label">归档与回访</span>
            <span class="closure-badge">{{ ticket?.is_callbacked ? '已回访' : ticket?.callback_required === false ? '无需回访' : '未回访' }}</span>
            <span v-if="ticket?.is_callbacked && ticket?.satisfaction" class="closure-badge">{{ satisfactionText(ticket.satisfaction) }}</span>
          </div>
          <div v-if="ticket?.archive_notes" class="node-reply-body">{{ ticket.archive_notes }}</div>
          <div v-if="ticket?.callback_details" class="node-record-note">回访记录：{{ ticket.callback_details }}</div>
          <div v-if="ticket?.satisfaction === 'dissatisfied' && ticket?.unsatisfied_reason" class="node-record-note">不满意原因：{{ ticket.unsatisfied_reason }}</div>
        </div>
      </div>
    </div>
    <div v-if="currentStage" class="timeline-item is-current">
      <div class="timeline-marker"><div class="marker-dot" /></div>
      <div class="timeline-content">
        <div class="timeline-head">
          <span class="action-name">{{ currentStage.title }}</span>
          <span class="current-tag">当前</span>
          <span v-if="currentStage.enteredAt" class="action-time"><DateTimeLabel :iso="currentStage.enteredAt" /></span>
        </div>
        <div v-if="currentStage.person" class="action-operator">{{ currentStage.personLabel }}：{{ currentStage.person }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DateTimeLabel from '@/components/common/DateTimeLabel.vue'
import type { Article, TicketStateLog } from '@/types'

const props = defineProps<{
  logs: TicketStateLog[]
  currentState?: string
  currentOwnerName?: string
  currentDispatcherName?: string
  currentCreatorName?: string
  articlesByLog?: Map<number, Article[]>
  ticket?: any
  closureLogId?: number | null
}>()

function articleLabel(type?: string): string {
  return ({ reply: '处理说明', addition: '补充信息', reminder: '催办', return: '退回补充' } as Record<string, string>)[type || ''] || '沟通记录'
}

function satisfactionText(value: string): string {
  return { satisfied: '😊 满意', average: '😐 一般', dissatisfied: '😞 不满意', unrated: '未评价' }[value] || value
}

interface TimelineNode {
  key: string
  log: TicketStateLog
  ts: string
}

const nodes = computed<TimelineNode[]>(() =>
  (props.logs || [])
    .map(log => ({
      key: `state-${log.id}`,
      log,
      ts: log.entered_at || (log as any).created_at,
    }))
    .sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime()),
)

/** 动作名：日志动作类型 → 业务语言（回退到目标状态名） */
const ACTION_NAMES: Record<string, string> = {
  create: '创建工单',
  instant_resolve: '即办结归档',
  dispatch: '分派处理人',
  refine: '问题判断',
  transfer: '转派下一部门',
  hold: '暂缓处理',
  resume: '恢复处理',
  return: '退回',
  reopen: '退回重开',
  resubmit: '重新提交',
  resolve: '提交处理结果',
  archive: '归档',
  cancel: '撤销',
}
const STATE_FALLBACK: Record<string, string> = {
  pending: '进入待受理',
  open: '进入处理中',
  resolved: '进入已处理',
  on_hold: '进入暂缓处理',
  returned: '进入已退回',
  archived: '归档',
  cancelled: '撤销',
  awaiting_callback: '进入待回访',
  callbacked: '回访完成',
}

function actionName(log: TicketStateLog): string {
  const t = log.action_type || ''
  if (ACTION_NAMES[t]) return ACTION_NAMES[t]
  const st = log.to_state_key || ''
  return STATE_FALLBACK[st] || '状态变更'
}

function responsibleLabel(log: TicketStateLog): string {
  const actionLabels: Record<string, string> = {
    create: '创建人',
    dispatch: '分派人',
    refine: '判断人',
    transfer: '转派人',
    resolve: '处理人',
    archive: '归档人',
    cancel: '撤销人',
    hold: '暂缓人',
    resume: '恢复人',
    return: '退回人',
    reopen: '重开人',
    resubmit: '提交人',
    instant_resolve: '操作人',
  }
  if (log.action_type) return actionLabels[log.action_type] || '操作人'
  if (log.to_state_key === 'pending') return '节点对接人'
  if (log.to_state_key === 'returned') return '退回接收人'
  return '节点处理人'
}

function responsibleName(log: TicketStateLog): string {
  if (log.action_type === 'create') return log.operator_name || log.creator_name_snapshot || ''
  if (log.action_type === 'dispatch') return log.operator_name || log.dispatcher_name_snapshot || ''
  if (log.action_type) return log.operator_name || log.changed_by?.firstname || ''
  if (log.to_state_key === 'pending') return log.dispatcher_name_snapshot || ''
  if (log.to_state_key === 'returned') return log.creator_name_snapshot || ''
  return log.operator_name || log.changed_by?.firstname || ''
}

const TERMINAL_STATES = new Set(['archived', 'cancelled'])

const currentStage = computed(() => {
  const state = props.currentState || nodes.value[nodes.value.length - 1]?.log.to_state_key
  if (!state || TERMINAL_STATES.has(state)) return null
  const enteredAt = nodes.value[nodes.value.length - 1]?.ts || ''
  if (state === 'pending') return { title: '待分派处理人', personLabel: '对接人', person: props.currentDispatcherName || '', enteredAt }
  if (state === 'open') return { title: '待提交处理说明', personLabel: '处理人', person: props.currentOwnerName || '', enteredAt }
  if (state === 'on_hold') return { title: '暂缓处理中', personLabel: '处理人', person: props.currentOwnerName || '', enteredAt }
  if (state === 'returned') return { title: '待补充后重新提交', personLabel: '创建人', person: props.currentCreatorName || '', enteredAt }
  if (state === 'resolved') return { title: '待回访归档', personLabel: '', person: '', enteredAt }
  return null
})
</script>

<style scoped>
.timeline {
  display: flex;
  flex-direction: column;
}

.timeline-item {
  display: flex;
  gap: 12px;
  position: relative;
  padding-bottom: 14px;
}
.timeline-item:last-child { padding-bottom: 0; }

.timeline-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 10px;
}
.marker-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  background: var(--color-border);
  margin-top: 5px;
  flex-shrink: 0;
}
.is-first .marker-dot {
  background: var(--color-text-tertiary);
}
.is-current .marker-dot {
  background: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-ghost);
}
.marker-line {
  flex: 1;
  width: 1px;
  background: var(--color-divider);
  margin-top: 4px;
}

.timeline-content {
  flex: 1;
  min-width: 0;
}

.timeline-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
.action-name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.is-current .action-name { color: var(--color-primary); }

.current-tag {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-primary);
  background: var(--color-primary-ghost);
  padding: 1px 6px;
  border-radius: var(--radius-full);
}

.action-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}

.action-operator {
  font-size: 12.5px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
}
.node-reply {
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-bg-card);
  box-shadow: var(--shadow-xs);
}
.node-reply-label { color: var(--color-text-secondary); font-size: 12px; font-weight: 600; }
.node-record-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; color: var(--color-text-tertiary); font-size: 11px; }
.node-record-head > :last-child { margin-left: auto; }
.node-reply-body { margin-top: 8px; color: var(--color-text-primary); font-size: 13px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }
.node-record-note { margin-top: 6px; color: var(--color-text-tertiary); font-size: 12px; white-space: pre-wrap; overflow-wrap: anywhere; }
.closure-badge { padding: 1px 7px; border-radius: var(--radius-full); background: var(--color-primary-ghost); color: var(--color-primary); font-size: 11px; }
.node-attachments { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.node-attachments img { width: 64px; height: 64px; object-fit: cover; border-radius: var(--radius-sm); border: 1px solid var(--color-border-light); }

.empty {
  font-size: 13px;
  color: var(--color-text-placeholder);
  padding: 8px 0;
}
</style>
