<template>
  <div class="state-log-timeline">
    <div v-if="nodes.length === 0" class="empty">
      暂无流转记录
    </div>
    <div v-else class="timeline">
      <div
        v-for="(node, index) in nodes"
        :key="node.key"
        class="timeline-item"
        :class="{
          'is-current': node.kind === 'state' && !node.log.left_at,
          'is-first': index === 0,
          'is-addition': node.kind === 'addition',
          'is-reminder': node.kind === 'reminder',
          'has-branch': node.kind !== 'state',
        }"
      >
        <div class="timeline-marker">
          <div class="marker-dot" />
          <div v-if="index < nodes.length - 1" class="marker-line" />
        </div>
        <div v-if="node.kind !== 'state'" class="timeline-branch">
          <div class="branch-line" />
          <div class="branch-dot" />
        </div>
        <div class="timeline-content">
          <!-- 状态节点 -->
          <template v-if="node.kind === 'state'">
            <div class="timeline-header">
              <span class="state-name">
                <StateTag :state="node.log.to_state" :compact="true" />
                <span v-if="node.log.is_return && node.log.to_state_key !== 'returned'" class="return-badge">退回</span>
              </span>
              <span v-if="!node.log.left_at" class="duration current">当前</span>
            </div>
            <div class="timeline-meta">
              <DateTimeLabel :iso="node.log.entered_at" />
              <span v-if="node.log.changed_by && relatedPeople(node.log, node.log.to_state_key).length === 0">操作人：{{ node.log.changed_by.firstname }}{{ node.log.changed_by.lastname }}</span>
              <span v-for="p in relatedPeople(node.log, node.log.to_state_key)" :key="p.label" class="related">
                {{ p.label }}：{{ p.name }}
              </span>
              <span v-if="node.log.reason" class="reason">{{ node.log.is_return ? '退回原因' : '原因' }}：{{ node.log.reason }}</span>
            </div>
            <!-- 该状态下的处理说明 -->
            <div
              v-for="r in repliesForState(node.log)"
              :key="r.id"
              class="reply-block"
            >
              <div class="reply-block-label">处理说明</div>
              <div class="reply-block-body">{{ r.body }}</div>
              <div class="reply-block-meta">
                <span v-if="senderName(r)">操作人：{{ senderName(r) }}</span>
                <DateTimeLabel :iso="r.created_at" />
              </div>
            </div>

            <!-- 归档信息 -->
            <div v-if="node.log.to_state_key === 'archived'" class="archive-block">
              <div class="archive-block-label">归档信息</div>
              <div v-if="ticket?.archive_notes" class="archive-block-body">{{ ticket.archive_notes }}</div>
              <div class="archive-block-meta">
                <span v-if="ticket?.is_callbacked" class="badge badge-callback">✓ 已回访</span>
                <span v-else-if="ticket?.callback_required === false" class="badge badge-no-callback">无需回访</span>
                <span v-else class="badge badge-no-callback">未回访</span>
                <span
                  v-if="ticket?.is_callbacked && ticket?.satisfaction"
                  class="badge"
                  :class="`badge-sat-${ticket.satisfaction}`"
                >
                  <span class="badge-emoji">{{ satisfactionEmoji(ticket.satisfaction) }}</span>
                  {{ satisfactionLabel(ticket.satisfaction) }}
                </span>
              </div>
            </div>
          </template>

          <!-- 追加节点 -->
          <template v-else-if="node.kind === 'addition'">
            <div class="timeline-header">
              <span class="addition-name">补充信息</span>
            </div>
            <div class="timeline-meta">
              <DateTimeLabel :iso="node.article.created_at" />
              <span v-if="senderName(node.article)">操作人：{{ senderName(node.article) }}</span>
            </div>
            <div v-if="node.article.body" class="addition-body">{{ node.article.body }}</div>
            <div v-if="node.article.append_reason" class="addition-reason">补充原因：{{ node.article.append_reason }}</div>
            <div v-if="node.article.attachments?.length" class="attachment-list">
              <a
                v-for="att in node.article.attachments"
                :key="att.id"
                :href="att.url"
                target="_blank"
                class="attachment-thumb-link"
                :title="att.original_filename"
              >
                <img :src="att.url" :alt="att.original_filename" />
              </a>
            </div>
          </template>

          <!-- 催办节点 -->
          <template v-else>
            <div class="timeline-header">
              <span class="reminder-name">催办信息</span>
            </div>
            <div class="timeline-meta">
              <DateTimeLabel :iso="node.article.created_at" />
              <span v-if="senderName(node.article)">催办人：{{ senderName(node.article) }}</span>
            </div>
            <div v-if="node.article.body" class="reminder-body">{{ node.article.body }}</div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StateTag from '@/components/common/StateTag.vue'
import DateTimeLabel from '@/components/common/DateTimeLabel.vue'
import type { TicketStateLog, Article } from '@/types'

const props = defineProps<{
  logs: TicketStateLog[]
  ticket?: any
  additions?: Article[]
  reminders?: Article[]
  replies?: Article[]
}>()

// 合并状态日志、追加记录和催办记录，按时间排序
type TimelineNode =
  | { key: string; kind: 'state'; log: TicketStateLog; ts: string }
  | { key: string; kind: 'addition'; article: Article; ts: string }
  | { key: string; kind: 'reminder'; article: Article; ts: string }

const nodes = computed<TimelineNode[]>(() => {
  const stateNodes: TimelineNode[] = (props.logs || []).map(log => ({
    key: `state-${log.id}`,
    kind: 'state' as const,
    log,
    ts: log.entered_at,
  }))
  const additionNodes: TimelineNode[] = (props.additions || []).map(a => ({
    key: `addition-${a.id}`,
    kind: 'addition' as const,
    article: a,
    ts: a.created_at,
  }))
  const reminderNodes: TimelineNode[] = (props.reminders || []).map(a => ({
    key: `reminder-${a.id}`,
    kind: 'reminder' as const,
    article: a,
    ts: a.created_at,
  }))
  return [...stateNodes, ...additionNodes, ...reminderNodes].sort((a, b) => {
    return new Date(a.ts).getTime() - new Date(b.ts).getTime()
  })
})

// 按状态节点返回应显示的相关人员。
// 优先读 log 上的 _snapshot 字段（写入 state_log 那一刻工单上的人），
// 快照为空时回退到 ticket 当前值（兼容老数据 / 回填不完整的工单）。
// 待受理：创建者 + 部门对接人；处理中：部门对接人 + 处理人
function relatedPeople(log: TicketStateLog, stateKey: string | undefined): { label: string; name: string }[] {
  const t = props.ticket as any
  if (!t || !stateKey) return []
  const snapCreatorId    = log.creator_id_snapshot    ?? null
  const snapDispatcherId = log.dispatcher_id_snapshot ?? null
  const snapOwnerId      = log.owner_id_snapshot      ?? null
  const snapCreatorName    = log.creator_name_snapshot
  const snapDispatcherName = log.dispatcher_name_snapshot
  const snapOwnerName      = log.owner_name_snapshot

  const creatorId    = snapCreatorId    ?? t.creator_id
  const dispatcherId = snapDispatcherId ?? t.dispatcher_id
  const ownerId      = snapOwnerId      ?? t.owner_id
  const creatorName    = snapCreatorName    || (t.creator?.firstname    || t.creator_name    || '')
  const dispatcherName = snapDispatcherName || (t.dispatcher?.firstname || t.dispatcher_name || '')
  const ownerName      = snapOwnerName      || (t.owner?.firstname      || t.owner_name      || '')

  const people: { label: string; name: string }[] = []
  if (stateKey === 'pending') {
    if (creatorId)    people.push({ label: '创建者',     name: creatorName    || `用户#${creatorId}` })
    if (dispatcherId) people.push({ label: '部门对接人', name: dispatcherName || `用户#${dispatcherId}` })
  } else if (stateKey === 'open') {
    if (dispatcherId) people.push({ label: '部门对接人', name: dispatcherName || `用户#${dispatcherId}` })
    if (ownerId)      people.push({ label: '处理人',     name: ownerName      || `用户#${ownerId}` })
  }
  return people
}

function senderName(article: Article): string {
  const u = article.origin_by as any
  if (!u) return ''
  return u.firstname || u.name || ''
}

/** 后端 enum → 中文标签 */
function satisfactionLabel(v: string): string {
  const map: Record<string, string> = {
    satisfied: '满意',
    average: '一般',
    dissatisfied: '不满意',
    unrated: '未评价',
  }
  return map[v] || v
}

/** 后端 enum → emoji（归档信息徽标用） */
function satisfactionEmoji(v: string): string {
  const map: Record<string, string> = {
    satisfied: '⭐',
    average: '😐',
    dissatisfied: '⚠️',
    unrated: '—',
  }
  return map[v] || ''
}

// 某状态下挂载的处理说明：优先按 state_log id 匹配，旧数据降级为按状态 key + 时间范围匹配
function repliesForState(log: TicketStateLog): Article[] {
  return (props.replies || []).filter(r => {
    if (r.state_key === String(log.id)) return true
    if (r.state_key === log.to_state_key) {
      const created = new Date(r.created_at).getTime()
      const entered = new Date(log.entered_at).getTime()
      const left = log.left_at ? new Date(log.left_at).getTime() : Infinity
      return created >= entered && created < left
    }
    return false
  })
}

</script>

<style scoped>
.state-log-timeline {
  width: 100%;
}

.empty {
  padding: 20px;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: 13px;
}

.timeline {
  display: flex;
  flex-direction: column;
}

.timeline-item {
  display: flex;
  gap: 12px;
  padding-bottom: 16px;
  align-items: flex-start;
}

.timeline-item.has-branch {
  gap: 0;
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

.is-addition .marker-dot,
.is-reminder .marker-dot {
  width: 6px;
  height: 6px;
  background: var(--color-border);
  border: none;
  box-shadow: none;
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

.timeline-branch {
  position: relative;
  width: 28px;
  flex-shrink: 0;
  margin-right: 12px;
  padding-top: 6px;
  height: 20px;
}

.branch-line {
  position: absolute;
  top: 10px;
  left: 0;
  width: 100%;
  height: 0;
  border-top: 2px dashed var(--color-border);
}

.branch-dot {
  position: absolute;
  top: 6px;
  right: -4px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-bg-card);
  border: 2px solid var(--color-border);
  z-index: 1;
}

.is-addition .branch-line {
  border-color: rgba(99, 91, 255, 0.35);
}

.is-addition .branch-dot {
  border-color: #635BFF;
}

.is-reminder .branch-line {
  border-color: rgba(245, 108, 108, 0.35);
}

.is-reminder .branch-dot {
  border-color: #F56C6C;
}

.timeline-content {
  flex: 1;
  background: var(--color-bg-subtle);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  border: 1px solid var(--color-border-light);
}

.is-current .timeline-content {
  background: rgba(16, 185, 129, 0.04);
  border-color: rgba(16, 185, 129, 0.2);
}

.is-addition .timeline-content,
.is-reminder .timeline-content {
  padding: 8px 12px;
}

.is-addition .timeline-content {
  background: rgba(99, 91, 255, 0.04);
  border-color: rgba(99, 91, 255, 0.2);
}

.is-reminder .timeline-content {
  background: rgba(245, 108, 108, 0.04);
  border-color: rgba(245, 108, 108, 0.2);
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

.return-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: var(--radius-full);
  background: var(--color-warning-light);
  color: var(--color-warning-text);
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
}

.addition-name {
  font-size: 11.5px;
  font-weight: 600;
  color: #4338CA;
}

.reminder-name {
  font-size: 11.5px;
  font-weight: 600;
  color: #C45656;
}

.duration {
  font-size: 12px;
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

.duration.current {
  color: var(--color-success);
  font-weight: 600;
}

.timeline-meta {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11.5px;
  color: var(--color-text-tertiary);
}
.timeline-meta .reason {
  color: var(--color-warning-text);
}

.addition-body {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

.reminder-body {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

.addition-reason {
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--color-text-tertiary);
}

.reply-block {
  margin-top: 10px;
  padding: 10px 12px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
}

.reply-block-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
}

.reply-block-body {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

.reply-block-meta {
  margin-top: 6px;
  display: flex;
  gap: 12px;
  font-size: 11.5px;
  color: var(--color-text-tertiary);
}

.archive-block {
  margin-top: 10px;
  padding: 10px 12px;
  background: rgba(16, 185, 129, 0.06);
  border: 1px solid rgba(16, 185, 129, 0.2);
  border-radius: var(--radius-sm);
}

.archive-block-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
}

.archive-block-body {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}

.archive-block-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
}

/* 归档信息徽标（回访 / 满意度） */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.6;
}
.badge-callback {
  background: #ECFDF5;
  color: #047857;
}
.badge-no-callback {
  background: #F3F4F6;
  color: #6B7280;
}
.badge-sat-satisfied {
  background: #FEF3C7;
  color: #92400E;
}
.badge-sat-average {
  background: #F3F4F6;
  color: #374151;
}
.badge-sat-dissatisfied {
  background: #FEE2E2;
  color: #B91C1C;
}
.badge-sat-unrated {
  background: #F3F4F6;
  color: #6B7280;
}
.badge-emoji {
  font-size: 13px;
  line-height: 1;
}

.attachment-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.attachment-thumb-link {
  display: block;
  width: 96px;
  height: 96px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  border: 1px solid var(--color-border-light);
  background: var(--color-bg-page);
}

.attachment-thumb-link img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform var(--duration-fast) var(--ease-out);
}

.attachment-thumb-link:hover img {
  transform: scale(1.04);
}
</style>
