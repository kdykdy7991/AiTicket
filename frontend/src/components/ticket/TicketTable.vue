<template>
  <el-table
    :data="tickets"
    :row-class-name="rowClassName"
    highlight-current-row
    style="width: 100%"
    @row-click="onRowClick"
    class="ticket-table"
  >
    <!-- 编号：实测 need=112（15 字符等宽，SF Mono 未装时 fallback DejaVu Sans Mono）
         + padding 32 + 余量 6 -->
    <el-table-column prop="number" label="编号" width="150">
      <template #default="{ row }">
        <span class="number-cell">{{ row.number || '—' }}</span>
      </template>
    </el-table-column>
    <!--
      标签列：全表唯一的自适应列。
      Element Plus 的列宽分配规则：固定 width 的列先按声明值布局，
      容器富余时全部余量给带 min-width 的列；容器不足时该列退到 min-width，
      其余固定列不会被压缩（因此「其他列不够时找标签列要空间」成立，
      标签列压到 min-width 后表格才出横向滚动条）。
      min-width=155 覆盖「3 个徽标 + N」实测 need=123 + 余量。
      徽标最多展示 3 个，超出折叠为 +N，避免 nowrap 撑破列宽。
    -->
    <el-table-column label="标签" min-width="155">
      <template #default="{ row }">
        <div class="title-cell" :title="badgeSummary(row)">
          <span
            v-for="b in visibleBadges(row)"
            :key="b.key"
            class="title-badge"
            :class="`badge-${b.variant}`"
          >
            <svg v-if="b.icon === 'warning'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <svg v-else-if="b.icon === 'repeat'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="17,1 21,5 17,9"/>
              <path d="M3 11V9a4 4 0 0 1 4-4h14"/>
              <polyline points="7,23 3,19 7,15"/>
              <path d="M21 13v2a4 4 0 0 1-4 4H3"/>
            </svg>
            <template v-else>{{ b.label }}</template>
          </span>
          <span v-if="hiddenBadgeCount(row) > 0" class="title-badge badge-more">
            +{{ hiddenBadgeCount(row) }}
          </span>
        </div>
      </template>
    </el-table-column>
    <!-- 状态：实测 need=79（StateTag"暂缓处理"：6dot+5gap+48字+20内距）+ padding 32 + 余量 6 -->
    <el-table-column label="状态" width="117" align="center">
      <template #default="{ row }">
        <StateTag :state="row.state" />
      </template>
    </el-table-column>
    <!-- 优先级：实测 need=125（"P1 特别重大事件" 文本 97.5 + dot 8 + gap 6 + inline 余量）
         + padding 32 + 余量 6。这列完全被"特别重大事件"6 个字撑起，是全表最贵的一列 -->
    <el-table-column label="优先级" width="163" align="center">
      <template #default="{ row }">
        <PriorityIcon :priority="row.priority" :show-label="true" />
      </template>
    </el-table-column>
    <!--
      处理人：固定列，姓名完整显示不截断。
      实测 5 字中文名 need=116，每多 1 字 +13 → 6 字 need=129。
      取 162 使 avail=130 覆盖 6 字姓名；更长姓名（库字段 VARCHAR(100)）走 ellipsis + title。
    -->
    <el-table-column label="处理人" width="162">
      <template #default="{ row }">
        <!--
          按状态显示"当前节点的处理人员"：
          - pending：还没分派，对接人就是当前处理人（负责分派）
          - archived：谁执行了 archived 动作（archived_by_*）
          - cancelled：谁执行了 cancelled 动作（cancelled_by_*）
          - 其他：直接显示 owner（handler / creator / 最后处理人）
        -->
        <span class="handler-cell" :title="handlerName(row)">
          <UserAvatar
            :user="resolveHandler(row)"
            :size="24"
            :show-name="true"
          />
        </span>
      </template>
    </el-table-column>
    <!-- SLA：实测 need=66（"剩 23时59分" 12px tabular-nums）+ padding 32 + 余量 8 -->
    <el-table-column label="SLA" width="106" align="center">
      <template #default="{ row }">
        <span v-if="slaLabel(row)" class="sla-cell" :class="slaState(row)">{{ slaLabel(row) }}</span>
        <span v-else class="muted">—</span>
      </template>
    </el-table-column>
    <!-- 更新时间：实测 need=48（zh-cn 相对时间最长"3 个月前"）+ padding 32 + 余量 8 -->
    <el-table-column label="更新时间" width="94" align="right">
      <template #default="{ row }">
        <RelativeTime :datetime="row.updated_at" />
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import StateTag from '@/components/common/StateTag.vue'
import PriorityIcon from '@/components/common/PriorityIcon.vue'
import UserAvatar from '@/components/common/UserAvatar.vue'
import RelativeTime from '@/components/common/RelativeTime.vue'
import type { Ticket } from '@/types'

defineProps<{
  tickets: Ticket[]
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

function handlerName(row: Ticket): string {
  const u = resolveHandler(row) as any
  if (!u) return '未分配'
  return `${u.firstname || ''}${u.lastname || ''}` || '未分配'
}

/** 标签徽标最多可见数，超出折叠为 +N（配合 min-width，避免 nowrap 撑破列宽） */
const MAX_VISIBLE_BADGES = 3

type BadgeVariant = 'sla' | 'dup' | 'urge' | 'addition' | 'returned'

interface Badge {
  key: string
  /** 徽标含义，同时作为折叠时的提示文案 */
  label: string
  variant: BadgeVariant
  /** 纯图标型徽标（无文字） */
  icon?: 'warning' | 'repeat'
}

/** 按重要度排序：SLA 超时 > 催办 > 退回 > 补充 > 重投 */
function badgesOf(row: Ticket): Badge[] {
  const list: Badge[] = []
  if (isEscalated(row)) {
    list.push({ key: 'sla', label: 'SLA 已超时', variant: 'sla', icon: 'warning' })
  }
  if (row.urged_at) list.push({ key: 'urge', label: '已催办', variant: 'urge' })
  if (row.has_returned) list.push({ key: 'returned', label: '曾退回', variant: 'returned' })
  if (row.has_addition) list.push({ key: 'addition', label: '有补充信息', variant: 'addition' })
  if (row.is_duplicate) list.push({ key: 'dup', label: '重投工单', variant: 'dup', icon: 'repeat' })
  return list
}

function visibleBadges(row: Ticket): Badge[] {
  return badgesOf(row).slice(0, MAX_VISIBLE_BADGES)
}

function hiddenBadgeCount(row: Ticket): number {
  return Math.max(0, badgesOf(row).length - MAX_VISIBLE_BADGES)
}

/** 单元格 hover 提示：列出全部徽标，折叠掉的 +N 也能看到含义 */
function badgeSummary(row: Ticket): string {
  return badgesOf(row).map(b => b.label).join(' · ')
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
</script>

<style scoped>
.ticket-table { cursor: pointer; }
.ticket-table :deep(.el-table__row) { transition: background var(--duration-fast) var(--ease-out); }
.ticket-table :deep(.el-table__header th) { background: var(--color-bg-subtle); }

/* SLA 列文字 */
.sla-cell {
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
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
  white-space: nowrap;
}

/* Element Plus .cell 默认 white-space:normal + overflow-wrap:break-word，
   子组件文字（优先级名、姓名）需显式 nowrap，否则空间不足时换行导致行高不一致 */
.ticket-table :deep(.priority-icon),
.ticket-table :deep(.priority-label) {
  white-space: nowrap;
}

/* 处理人姓名：6 字内完整显示，超长（库字段 VARCHAR(100)）省略并由 title 兜底 */
.handler-cell {
  display: block;
  max-width: 100%;
}
.ticket-table :deep(.user-avatar-wrapper) {
  max-width: 100%;
}
.ticket-table :deep(.name) {
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.title-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  overflow: hidden;
}

/* 徽标基类：文字型（催办/退回/补充）撑开，图标型（重投/SLA）固定 20px 圆 */
.title-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  height: 20px;
  padding: 0 6px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}
.badge-sla,
.badge-dup {
  width: 20px;
  padding: 0;
}
.badge-sla { background: var(--color-danger-light); color: var(--color-danger); }
.badge-dup { background: #FEF3C7; color: #92400E; }
.badge-urge { background: #FEF2F2; color: #B91C1C; }
.badge-addition { background: #EFF6FF; color: #1D4ED8; }
.badge-returned { background: #FEF3C7; color: #92400E; }
.badge-more {
  padding: 0 5px;
  background: var(--color-bg-subtle);
  color: var(--color-text-tertiary);
}
</style>
