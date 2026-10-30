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
          <span class="action-name">{{ timelineActionName(node.log, ticket?.node_submissions || [], logs) }}</span>
          <span v-if="completedSubmission(node.log)" class="completed-tag">已完成</span>
          <span class="action-time">
            <DateTimeLabel :iso="node.ts" />
          </span>
        </div>
        <div v-if="responsibleName(node.log)" class="action-operator">
          {{ responsibleLabel(node.log) }}：{{ responsibleName(node.log) }}
        </div>
        <template v-if="node.log.action_type === 'hold'">
          <div v-if="node.log.reason" class="action-operator">暂缓原因：{{ node.log.reason }}</div>
          <div class="action-operator">预计恢复时间：{{ (node.log as any).hold_until_snapshot ? new Date((node.log as any).hold_until_snapshot).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '未记录' }}</div>
          <div v-if="node.log.reason?.startsWith('需要寄回维修：')" class="action-operator">是否需要寄回：是</div>
        </template>
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
import type { TicketStateLog } from '@/types'
import { timelineActionName } from '@/utils/ticketTimeline'

const props = defineProps<{
  logs: TicketStateLog[]
  currentState?: string
  currentOwnerName?: string
  currentDispatcherName?: string
  currentCreatorName?: string
  ticket?: any
}>()

interface TimelineNode {
  key: string
  log: TicketStateLog
  ts: string
}

const nodes = computed<TimelineNode[]>(() =>
  (props.logs || [])
    .filter(log => log.action_type !== 'auto_assign')
    .map(log => ({
      key: `state-${log.id}`,
      log,
      ts: log.entered_at || (log as any).created_at,
    }))
    .sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime()),
)

function completedSubmission(log: TicketStateLog) {
  return props.ticket?.node_submissions?.find((entry: any) =>
    entry.state_log_id === log.id && entry.action_type !== 'callback_record',
  )
}

function responsibleLabel(log: TicketStateLog): string {
  if (completedSubmission(log)?.node_type === 'processing') return '处理人'
  const actionLabels: Record<string, string> = {
    create: '创建人',
    dispatch: '分派人',
    direct_assign: '指派人',
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
  const latestLog = [...(props.logs || [])].sort((a, b) => new Date(a.entered_at).getTime() - new Date(b.entered_at).getTime()).at(-1)
  const enteredAt = latestLog?.entered_at || ''
  const steps = props.ticket?.dispatch_chain_steps || []
  const isPhoneFeedback = steps[props.ticket?.dispatch_step_index]?.stage === 'phone_feedback'
  const nodeName = props.ticket?.node_context?.node_name
  if (nodeName && state === 'resolved') return { title: nodeName, personLabel: '', person: '', enteredAt }
  if (nodeName && ['pending', 'open', 'on_hold'].includes(state)) {
    return { title: nodeName, personLabel: state === 'pending' ? '对接人' : '处理人',
      person: state === 'pending' ? props.currentDispatcherName || '' : props.currentOwnerName || '', enteredAt }
  }
  if (props.ticket?.node_context?.node_type === 'assignment' && state === 'pending') {
    return { title: '待指派售后人员', personLabel: '售后负责人', person: props.currentDispatcherName || '', enteredAt }
  }
  if (props.ticket?.category_id === 2301 && state === 'open') {
    return { title: '待售后问题判断', personLabel: '售后人员', person: props.currentOwnerName || '', enteredAt }
  }
  if (isPhoneFeedback && state === 'pending') return { title: '售后致电反馈待接续', personLabel: '责任人', person: props.currentOwnerName || props.currentDispatcherName || '', enteredAt }
  if (isPhoneFeedback && state === 'open') return { title: '待售后致电反馈', personLabel: '处理人', person: props.currentOwnerName || '', enteredAt }
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

.completed-tag {
  font-size: 11px;
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border);
  padding: 1px 6px;
  border-radius: var(--radius-full);
}

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
.empty {
  font-size: 13px;
  color: var(--color-text-placeholder);
  padding: 8px 0;
}
</style>
