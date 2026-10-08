<template>
  <!-- 处理流程按操作展示，节点责任人取流转时的人员快照。 -->
  <div class="timeline">
    <div v-if="nodes.length === 0" class="empty">暂无流转记录</div>
    <div
      v-for="(node, index) in nodes"
      :key="node.key"
      class="timeline-item"
      :class="{ 'is-first': index === 0, 'is-current': isCurrent(node) }"
    >
      <div class="timeline-marker">
        <div class="marker-dot" />
        <div v-if="index < nodes.length - 1" class="marker-line" />
      </div>
      <div class="timeline-content">
        <div class="timeline-head">
          <span class="action-name">{{ actionName(node.log) }}</span>
          <span v-if="isCurrent(node)" class="current-tag">当前</span>
          <span class="action-time">
            <DateTimeLabel :iso="node.ts" />
          </span>
        </div>
        <div v-if="responsibleName(node.log, isCurrent(node))" class="action-operator">
          {{ responsibleLabel(node.log) }}：{{ responsibleName(node.log, isCurrent(node)) }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DateTimeLabel from '@/components/common/DateTimeLabel.vue'
import type { TicketStateLog } from '@/types'

const props = defineProps<{
  logs: TicketStateLog[]
  currentOwnerName?: string
}>()

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
  if (log.action_type === 'create') return '创建人'
  if (log.to_state_key === 'pending') return '节点对接人'
  if (log.to_state_key === 'returned') return '退回接收人'
  return '节点处理人'
}

function responsibleName(log: TicketStateLog, current: boolean): string {
  if (log.action_type === 'create') return log.creator_name_snapshot || log.operator_name || ''
  if (log.to_state_key === 'pending') return log.dispatcher_name_snapshot || ''
  if (log.to_state_key === 'returned') return log.creator_name_snapshot || ''
  return (current && props.currentOwnerName) || log.owner_name_snapshot || ''
}

const TERMINAL_STATES = new Set(['archived', 'cancelled'])

/** 当前节点 = 最后一条且该动作未把工单带入终态 */
function isCurrent(node: TimelineNode): boolean {
  const last = nodes.value[nodes.value.length - 1]
  if (!last || last.key !== node.key) return false
  return !TERMINAL_STATES.has(node.log.to_state_key || '')
}
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

.empty {
  font-size: 13px;
  color: var(--color-text-placeholder);
  padding: 8px 0;
}
</style>
