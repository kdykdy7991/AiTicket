<template>
  <div class="state-log-timeline">
    <div v-if="!nodes.length" class="empty">暂无流程记录</div>
    <div v-else class="timeline">
      <div
        v-for="(node, index) in nodes"
        :key="node.log.id"
        class="timeline-item"
        :class="{ 'is-current': node.isCurrent, 'is-first': index === 0 }"
      >
        <div class="timeline-marker">
          <div class="marker-dot" />
          <div v-if="index < nodes.length - 1" class="marker-line" />
        </div>

        <div class="timeline-content">
          <div class="timeline-header">
            <span class="state-name">
              <span class="action-name">{{ actionLabel(node.log.action) }}</span>
              <span class="state-arrow">→</span>
              <span class="state-pill" :class="`pill-${stateType(node.log.to_state)}`">
                <i class="pill-dot" />{{ stateLabel(node.log.to_state) }}
              </span>
              <span v-if="node.returnBadge" class="return-badge">{{ node.returnBadge }}</span>
            </span>
            <span v-if="node.isCurrent" class="duration current">当前</span>
          </div>

          <div class="timeline-meta">
            <DateTimeLabel :iso="node.log.created_at" />
            <span>操作人：{{ node.log.operator_name || '系统' }}</span>
            <span v-if="node.operatorSubsystem">所属系统：{{ node.operatorSubsystem }}</span>
            <span v-if="node.showNextResponsible && node.nextResponsibleSystem">下一责任系统：{{ node.nextResponsibleSystem }}</span>
            <span v-else-if="node.showNextResponsible && node.nextResponsibleRole">下一责任角色：{{ node.nextResponsibleRole }}</span>
            <span v-if="node.showNextResponsible && node.nextResponsibleUser">下一责任人：{{ node.nextResponsibleUser }}</span>
            <span v-if="node.comment" class="comment-summary" :class="{ reason: node.isReturn }" :title="node.comment">
              {{ node.isReturn ? '退回原因' : '意见' }}：{{ node.comment }}
            </span>
          </div>

          <div v-if="node.details.length" class="detail-block">
            <div class="detail-block-label">本次填写内容</div>
            <dl class="detail-grid">
              <template v-for="detail in node.details" :key="detail.label">
                <dt>{{ detail.label }}</dt>
                <dd>{{ detail.value }}</dd>
              </template>
            </dl>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'
import DateTimeLabel from '@/components/common/DateTimeLabel.vue'
import {
  VERIFICATION_STATUS_OPTIONS,
  actionLabel,
  roleLabel,
  stateLabel,
  stateType,
  type PocState,
} from '@/domain/pocWorkflow'
import type { Group } from '@/types'
import type { PocStateLog } from '@/types/poc'

const props = defineProps<{
  /** 按时间正序展示的流程日志（后端按 id 升序返回） */
  logs: PocStateLog[]
  /** 工单当前状态，用于标记「当前」节点 */
  currentState?: PocState | string | null
  /** 分系统字典，用于把 route 动作 payload 里的 skill_group_id 还原成名称 */
  skillGroups?: Group[]
  /** 当前问题所属分系统；分系统人员的对外身份使用此名称 */
  subsystemName?: string | null
}>()

//: payload 里需要展示的字段（其余字段与 comment 重复或属于内部字段）
const PAYLOAD_FIELDS: { key: string; label: string }[] = [
  { key: 'temporary_measure', label: '临时处置措施' },
  { key: 'long_term_measure', label: '长期整改措施' },
  { key: 'planned_completion_at', label: '计划完成时间' },
  { key: 'initial_investigation', label: '初步排查结论' },
  { key: 'root_cause', label: '根本原因分析' },
  { key: 'analysis_report', label: '质量问题分析报告' },
  { key: 'verification_status', label: '验证状态' },
  { key: 'verification_conclusion', label: '验证结论' },
  { key: 'quality_review_result', label: '质量评审结果' },
  { key: 'return_to_state', label: '退回目标' },
]

//: 与 comment 重复（服务层会把意见落到这些业务字段），不重复展示
const COMMENT_BACKED_FIELDS = new Set([
  'confirmation_comment',
  'acceptance_comment',
  'plan_confirmation_comment',
])

interface TimelineNode {
  log: PocStateLog
  isCurrent: boolean
  isReturn: boolean
  returnBadge: string
  comment: string | null
  operatorSubsystem: string
  showNextResponsible: boolean
  nextResponsibleSystem: string
  nextResponsibleRole: string
  nextResponsibleUser: string
  details: { label: string; value: string }[]
}


function skillGroupName(id: unknown): string {
  const found = props.skillGroups?.find(group => group.id === Number(id))
  return found ? found.name : `#${id}`
}

function formatValue(key: string, value: unknown, log: PocStateLog): string {
  if (value == null || value === '') return '—'
  if (key === 'skill_group_id') return skillGroupName(value)
  // 流转节点的人名直接取快照：动作完成后责任人就是刚选定的分系统负责人
  if (key === 'subsystem_owner_id') return log.responsible_user_name_snapshot || `#${value}`
  if (key === 'return_to_state') return stateLabel(String(value))
  if (key === 'verification_status') {
    return VERIFICATION_STATUS_OPTIONS.find(item => item.value === value)?.label || String(value)
  }
  if (key === 'planned_completion_at') return dayjs(String(value)).format('YYYY-MM-DD HH:mm')
  return String(value)
}

const SUBSYSTEM_ACTIONS = new Set(['submit_plan', 'submit_analysis'])
const COMMENT_SUMMARY_LENGTH = 160
const DETAIL_SUMMARY_LENGTH = 120

function summarize(value: string, maxLength: number): string {
  const normalized = value.replace(/\s+/g, ' ').trim()
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}…` : normalized
}

const nodes = computed<TimelineNode[]>(() => {
  const sorted = [...(props.logs || [])].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )
  return sorted.map((log, index) => {
    const isReturn = log.action === 'return' || log.action === 'reject'
    const payload = log.payload || {}
    const nextRole = log.responsible_role_snapshot
    return {
      log,
      // 最后一条即当前节点（后端每次动作都会写日志）
      isCurrent: index === sorted.length - 1 && log.to_state === props.currentState,
      isReturn,
      returnBadge: log.action === 'reject' ? '驳回' : isReturn ? '退回' : '',
      // 首条日志的 comment 固定是「提交审批」，与动作名重复
      comment: log.action && log.comment ? summarize(log.comment, COMMENT_SUMMARY_LENGTH) : null,
      showNextResponsible: index === sorted.length - 1 && log.to_state === props.currentState && !['closed', 'cancelled'].includes(log.to_state),      operatorSubsystem: log.action && SUBSYSTEM_ACTIONS.has(log.action) ? (props.subsystemName || '') : '',      nextResponsibleSystem: nextRole === 'subsystem' ? (props.subsystemName || '') : '',      nextResponsibleRole: nextRole && nextRole !== 'subsystem' ? roleLabel(nextRole) : '',      nextResponsibleUser: log.responsible_user_name_snapshot || '',
      details: PAYLOAD_FIELDS.filter(field => {
        if (COMMENT_BACKED_FIELDS.has(field.key)) return false
        const value = payload[field.key]
        return value != null && value !== ''
      }).map(field => ({
        label: field.label,
        value: summarize(formatValue(field.key, payload[field.key], log), DETAIL_SUMMARY_LENGTH),
      })),
    }
  })
})
</script>

<style scoped>
.state-log-timeline { width: 100%; }

.empty {
  padding: 20px;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: 13px;
}

.timeline { display: flex; flex-direction: column; }

.timeline-item {
  display: flex;
  gap: 12px;
  padding-bottom: 16px;
  align-items: flex-start;
}

.timeline-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 14px;
  flex-shrink: 0;
  padding-top: 6px;
}

.marker-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-primary);
  border: 2px solid var(--color-bg-card);
  box-shadow: 0 0 0 1px var(--color-primary);
  z-index: 1;
}

.is-current .marker-dot {
  background: var(--color-success);
  box-shadow: 0 0 0 1px var(--color-success);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.marker-line {
  flex: 1;
  width: 2px;
  background: var(--color-border);
  margin-top: 4px;
  min-height: 24px;
}

.timeline-content {
  flex: 1;
  min-width: 0;
  background: var(--color-bg-subtle);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  border: 1px solid var(--color-border-light);
  overflow: hidden;
}

.is-current .timeline-content {
  background: rgba(16, 185, 129, 0.04);
  border-color: rgba(16, 185, 129, 0.2);
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.state-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 700;
}

.action-name { color: var(--color-text-primary); }
.state-arrow { color: var(--color-text-tertiary); font-weight: 500; }

.state-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 9px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.6;
  white-space: nowrap;
}

.pill-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }

.pill-warning { background: var(--color-warning-light); color: var(--color-warning-text); }
.pill-warning .pill-dot { background: var(--color-warning); }
.pill-primary { background: var(--color-primary-light); color: #4338CA; }
.pill-primary .pill-dot { background: #635BFF; }
.pill-success { background: var(--color-success-light); color: var(--color-success-text); }
.pill-success .pill-dot { background: var(--color-success); }
.pill-danger { background: #FEE2E2; color: #B91C1C; }
.pill-danger .pill-dot { background: #DC2626; }
.pill-info { background: var(--color-info-light); color: var(--color-info-text); }
.pill-info .pill-dot { background: var(--color-info); }

.return-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  background: var(--color-warning-light);
  color: var(--color-warning-text);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
}

.duration {
  font-size: 12px;
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

.duration.current { color: var(--color-success); font-weight: 600; }

.timeline-meta {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11.5px;
  color: var(--color-text-tertiary);
}

.timeline-meta .reason { color: var(--color-warning-text); }

.comment-summary {
  display: -webkit-box;
  overflow: hidden;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.detail-block {
  margin-top: 10px;
  padding: 10px 12px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  overflow: hidden;
  border-radius: var(--radius-sm);
}

.detail-block-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
}

.detail-grid {
  display: grid;
  grid-template-columns: 108px minmax(0, 1fr);
  gap: 6px 12px;
  margin: 0;
  font-size: 12.5px;
}

.detail-grid dt { color: var(--color-text-tertiary); }

.detail-grid dd {
  margin: 0;
  color: var(--color-text-primary);
  line-height: 1.6;
  display: -webkit-box;
  overflow: hidden;
  overflow-wrap: anywhere;
  word-break: break-word;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}
</style>
