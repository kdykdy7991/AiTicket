<template>
  <el-table
    :data="tickets"
    :row-class-name="rowClassName"
    highlight-current-row
    style="width: 100%"
    @row-click="onRowClick"
    @selection-change="onSelectionChange"
    class="ticket-table"
    ref="tableRef"
  >
    <el-table-column v-if="selectable" type="selection" width="48" />
    <el-table-column prop="number" label="编号" width="145">
      <template #default="{ row }">
        <span class="number-cell">{{ row.number || '—' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="标签" min-width="200">
      <template #default="{ row }">
        <div class="title-cell">
          <span v-if="row.is_duplicate" class="dup-badge" title="重投工单">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="17,1 21,5 17,9"/>
              <path d="M3 11V9a4 4 0 0 1 4-4h14"/>
              <polyline points="7,23 3,19 7,15"/>
              <path d="M21 13v2a4 4 0 0 1-4 4H3"/>
            </svg>
          </span>
          <span v-if="isEscalated(row)" class="sla-badge" title="SLA 已超时">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
          </span>
          <span v-if="row.urged_at" class="urge-badge" title="已催办">催办</span>
          <span v-if="row.has_addition" class="addition-badge" title="有补充信息">补充</span>
          <span v-if="row.has_returned" class="returned-badge" title="曾退回">退回</span>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="状态" width="110" align="center">
      <template #default="{ row }">
        <StateTag :state="row.state" />
      </template>
    </el-table-column>
    <el-table-column label="优先级" width="100" align="center">
      <template #default="{ row }">
        <PriorityIcon :priority="row.priority" :show-label="true" />
      </template>
    </el-table-column>
    <el-table-column label="处理人" width="130">
      <template #default="{ row }">
        <!--
          按状态显示"当前节点的处理人员"：
          - pending：还没分派，对接人就是当前处理人（负责分派）
          - archived：谁执行了 archived 动作（archived_by_*）
          - cancelled：谁执行了 cancelled 动作（cancelled_by_*）
          - 其他：直接显示 owner（handler / creator / 最后处理人）
        -->
        <UserAvatar
          :user="resolveHandler(row)"
          :size="24"
          :show-name="true"
        />
      </template>
    </el-table-column>
    <el-table-column label="SLA" width="110" align="center">
      <template #default="{ row }">
        <span v-if="slaLabel(row)" class="sla-cell" :class="slaState(row)">{{ slaLabel(row) }}</span>
        <span v-else class="muted">—</span>
      </template>
    </el-table-column>
    <el-table-column label="更新时间" width="110" align="right">
      <template #default="{ row }">
        <RelativeTime :datetime="row.updated_at" />
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import type { TableInstance } from 'element-plus'
import StateTag from '@/components/common/StateTag.vue'
import PriorityIcon from '@/components/common/PriorityIcon.vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import RelativeTime from '@/components/common/RelativeTime.vue'
import type { Ticket } from '@/types'

const props = withDefaults(defineProps<{
  tickets: Ticket[]
  selectable?: boolean
}>(), { selectable: false })

const emit = defineEmits<{
  'selection-change': [tickets: Ticket[]]
}>()

const router = useRouter()

function isClosed(stateType: string): boolean {
  return stateType === 'closed' || stateType === 'merged'
}

/** 是否终态（已归档/已撤销，不再强调超时） */
function isTerminal(row: Ticket): boolean {
  const key = (row as any).state_key
  return key === 'archived' || key === 'cancelled'
}

/**
 * "处理人"列按状态选人：
 * - pending：dispatcher（对接人正在负责分派）
 * - returned：owner（state machine 已把 owner_id 设成 creator_id，
 *   即"退回后由创建人处理"，不显示是谁退回的）
 * - archived：archived_by_* 谁归档的
 * - cancelled：cancelled_by_* 谁撤销的
 * - open / on_hold / resolved：owner（handler）
 */
function resolveHandler(row: Ticket): any {
  const r = row as any
  const sk = r.state_key
  if (sk === 'pending') return r.dispatcher
  if (sk === 'returned') return r.owner
  if (sk === 'archived' && r.archived_by_id) {
    return { id: r.archived_by_id, firstname: r.archived_by_name || '未知', lastname: '' }
  }
  if (sk === 'cancelled' && r.cancelled_by_id) {
    return { id: r.cancelled_by_id, firstname: r.cancelled_by_name || '未知', lastname: '' }
  }
  return r.owner
}
function slaState(row: Ticket): 'danger' | 'warning' | 'normal' {
  // 终态工单不标红（已闭环，超时仅作历史记录）
  if (isTerminal(row)) return 'normal'
  // 优先用后端 SLA 引擎标记的 breach（最准）
  if (row.sla_breached) return 'danger'
  if (!row.escalation_at) return 'normal'
  const now = Date.now()
  const target = new Date(row.escalation_at).getTime()
  if (target < now) return 'danger'
  // 剩余时间 ≤ 20% 预警
  const total = target - new Date(row.created_at).getTime()
  if (total <= 0) return 'danger'
  const remaining = target - now
  if (remaining / total < 0.2) return 'warning'
  return 'normal'
}

function isEscalated(t: Ticket): boolean {
  // 标题旁的超时徽标：仅进行中状态的超时工单显示
  return slaState(t) === 'danger'
}

/** SLA 列文本 */
function slaLabel(row: Ticket): string {
  const breached = row.sla_breached
  // 终态工单：显示最终结论
  if (isTerminal(row)) {
    return breached ? '曾超时' : '达标'
  }
  // 进行中：已超时显示「已超时」
  if (breached) return '已超时'
  const deadline = row.escalation_at
  if (!deadline) return ''
  const remaining = new Date(deadline).getTime() - Date.now()
  if (remaining <= 0) return '已超时'
  return formatRemaining(remaining)
}

function formatRemaining(ms: number): string {
  const min = Math.floor(ms / 60000)
  if (min < 60) return `剩 ${min}分`
  const h = Math.floor(min / 60)
  if (h < 24) return `剩 ${h}时${min % 60}分`
  return `剩 ${Math.floor(h / 24)}天`
}

function rowClassName({ row }: { row: Ticket }): string {
  const key = (row as any).state_key || ''
  if (key === 'cancelled') return 'row-cancelled'
  const s = slaState(row)
  if (s === 'danger') return 'row-sla-danger'
  if (s === 'warning') return 'row-sla-warning'
  return ''
}

function onRowClick(row: Ticket) {
  router.push({ name: 'TicketDetail', params: { id: row.id } })
}

function onSelectionChange(rows: Ticket[]) {
  emit('selection-change', rows)
}

const tableRef = ref<TableInstance>()

/** 暴露给父组件，批量取消时同步清掉 el-table 内部的勾选状态 */
defineExpose({
  clearSelection: () => tableRef.value?.clearSelection(),
})
</script>

<style scoped>
.ticket-table { cursor: pointer; }
.ticket-table :deep(.el-table__row) { transition: background var(--duration-fast) var(--ease-out); }
.ticket-table :deep(.el-table__header th) { background: var(--color-bg-subtle); }

/* SLA 列文字 */
.sla-cell { font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
.sla-cell.danger { color: #EF4444; }
.sla-cell.warning { color: #EA580C; }
.sla-cell.normal { color: var(--color-text-tertiary); }
.muted { color: var(--color-text-tertiary); }

/* SLA 底色 */
.ticket-table :deep(.row-sla-warning) {
  background: linear-gradient(90deg, rgba(234, 88, 12, 0.10) 0%, rgba(234, 88, 12, 0.04) 100%) !important;
}
.ticket-table :deep(.row-sla-warning):hover > td {
  background: linear-gradient(90deg, rgba(234, 88, 12, 0.18) 0%, rgba(234, 88, 12, 0.08) 100%) !important;
}
.ticket-table :deep(.row-sla-danger) {
  background: linear-gradient(90deg, rgba(239, 68, 68, 0.12) 0%, rgba(239, 68, 68, 0.05) 100%) !important;
}
.ticket-table :deep(.row-sla-danger):hover > td {
  background: linear-gradient(90deg, rgba(239, 68, 68, 0.20) 0%, rgba(239, 68, 68, 0.10) 100%) !important;
}
.ticket-table :deep(.row-sla-danger) .number-cell { color: #B91C1C; font-weight: 600; }

/* 已撤销工单变灰 */
.ticket-table :deep(.row-cancelled) {
  background: var(--color-bg-subtle) !important;
  opacity: 0.75;
}
.ticket-table :deep(.row-cancelled):hover > td {
  background: var(--color-bg-hover) !important;
}
.ticket-table :deep(.row-cancelled) .number-cell {
  color: var(--color-text-tertiary);
}

.number-cell {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12.5px;
  color: var(--color-text-tertiary);
}

.title-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.title-chip {
  flex-shrink: 0;
}

.sla-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: var(--radius-full);
  background: var(--color-danger-light);
  color: var(--color-danger);
  flex-shrink: 0;
}
.dup-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: var(--radius-full);
  background: #FEF3C7;
  color: #92400E;
  flex-shrink: 0;
}
.urge-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
  height: 20px;
  border-radius: var(--radius-full);
  background: #FEF2F2;
  color: #B91C1C;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}
.addition-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
  height: 20px;
  border-radius: var(--radius-full);
  background: #EFF6FF;
  color: #1D4ED8;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}
.returned-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
  height: 20px;
  border-radius: var(--radius-full);
  background: #FEF3C7;
  color: #92400E;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}
</style>
