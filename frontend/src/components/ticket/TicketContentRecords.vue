<template>
  <!--
    处理记录：承载工单的内容性信息（处理说明 / 补充信息 / 催办 / 附件 / 归档回访），
    与上方「流转时间线」分离——时间线只回答「谁在什么时候做了什么动作」。
    按时间倒序（最新在前）。
  -->
  <div class="content-records">
    <!-- 归档 / 回访结论：工单属性而非流水，置顶展示 -->
    <div v-if="hasClosure" class="closure">
      <div class="closure-head">
        <span class="closure-title">归档与回访</span>
        <span v-if="t.is_callbacked" class="badge badge-ok">已回访</span>
        <span v-else-if="t.callback_required === false" class="badge">无需回访</span>
        <span v-else class="badge badge-warn">未回访</span>
        <span
          v-if="t.is_callbacked && t.satisfaction"
          class="badge"
          :class="`badge-sat-${t.satisfaction}`"
        >
          {{ satisfactionEmoji(t.satisfaction) }} {{ satisfactionLabel(t.satisfaction) }}
        </span>
      </div>
      <div v-if="t.archive_notes" class="closure-body">{{ t.archive_notes }}</div>
      <div v-if="t.satisfaction === 'dissatisfied' && t.unsatisfied_reason" class="closure-reason">
        不满意原因：{{ t.unsatisfied_reason }}
      </div>
    </div>

    <div v-if="records.length === 0" class="empty">暂无处理记录</div>

    <div v-for="r in records" :key="r.key" class="record">
      <div class="record-head">
        <span class="record-type" :class="`type-${r.kind}`">{{ typeLabel(r.kind) }}</span>
        <span class="record-time">
          <DateTimeLabel :iso="r.ts" />
        </span>
      </div>
      <div v-if="r.operator" class="record-operator">操作人：{{ r.operator }}</div>
      <div v-if="r.body" class="record-body">{{ r.body }}</div>
      <div v-if="r.appendReason" class="record-reason">补充原因：{{ r.appendReason }}</div>
      <div v-if="r.attachments.length" class="attachment-list">
        <a
          v-for="att in r.attachments"
          :key="att.id"
          :href="att.url"
          target="_blank"
          class="attachment-thumb-link"
          :title="att.original_filename"
        >
          <img :src="att.url" :alt="att.original_filename" />
        </a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DateTimeLabel from '@/components/common/DateTimeLabel.vue'
import type { Article } from '@/types'

const props = defineProps<{
  ticket: any
  replies?: Article[]
  additions?: Article[]
  reminders?: Article[]
}>()

const t = computed<any>(() => props.ticket || {})

interface RecordItem {
  key: string
  kind: 'reply' | 'addition' | 'reminder'
  ts: string
  operator: string
  body: string
  appendReason: string
  attachments: any[]
}

function senderName(a: Article): string {
  const u = a.origin_by as any
  if (!u) return ''
  return `${u.firstname || ''}${u.lastname || ''}` || u.name || ''
}

const records = computed<RecordItem[]>(() => {
  const pick = (list: Article[] | undefined, kind: RecordItem['kind']) =>
    (list || []).map(a => ({
      key: `${kind}-${a.id}`,
      kind,
      ts: a.created_at,
      operator: senderName(a),
      body: a.body || '',
      appendReason: a.append_reason || '',
      attachments: (a.attachments || []) as any[],
    }))
  return [
    ...pick(props.replies, 'reply'),
    ...pick(props.additions, 'addition'),
    ...pick(props.reminders, 'reminder'),
  ].sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())
})

const hasClosure = computed(
  () =>
    t.value.is_callbacked !== undefined ||
    t.value.callback_required === false ||
    !!t.value.archive_notes ||
    !!t.value.satisfaction ||
    (t.value.satisfaction === 'dissatisfied' && !!t.value.unsatisfied_reason),
)

function typeLabel(kind: RecordItem['kind']): string {
  return { reply: '处理说明', addition: '补充信息', reminder: '催办' }[kind]
}

function satisfactionLabel(v: string): string {
  const map: Record<string, string> = {
    satisfied: '满意', average: '一般', dissatisfied: '不满意', unrated: '未评价',
  }
  return map[v] || v
}
function satisfactionEmoji(v: string): string {
  return v === 'satisfied' ? '😊' : v === 'average' ? '😐' : v === 'dissatisfied' ? '😞' : '—'
}
</script>

<style scoped>
.content-records {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 归档与回访结论 */
.closure {
  padding: 12px 14px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-bg-subtle);
}
.closure-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.closure-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.closure-body {
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.closure-reason {
  margin-top: 6px;
  font-size: 12.5px;
  color: #B91C1C;
}

.badge {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: var(--radius-full);
  background: var(--color-bg-card);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-light);
}
.badge-ok { color: #047857; background: #ECFDF5; border-color: rgba(16,185,129,.3); }
.badge-warn { color: #92400E; background: #FEF3C7; border-color: rgba(245,158,11,.35); }
.badge-sat-satisfied { color: #047857; }
.badge-sat-average { color: #92400E; }
.badge-sat-dissatisfied { color: #B91C1C; }

/* 单条记录 */
.record {
  padding-bottom: 14px;
  border-bottom: 1px solid var(--color-divider);
}
.record:last-child { border-bottom: none; padding-bottom: 0; }

.record-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.record-type {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}
.type-reply { background: #EEF2FF; color: #4338CA; }
.type-addition { background: #EFF6FF; color: #1D4ED8; }
.type-reminder { background: #FEF2F2; color: #B91C1C; }
.record-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}
.record-operator {
  font-size: 12.5px;
  color: var(--color-text-tertiary);
  margin-top: 3px;
}
.record-body {
  margin-top: 6px;
  font-size: 13.5px;
  color: var(--color-text-primary);
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}
.record-reason {
  margin-top: 5px;
  font-size: 12.5px;
  color: var(--color-text-tertiary);
}

.attachment-list {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.attachment-thumb-link img {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-light);
  cursor: pointer;
}

.empty {
  font-size: 13px;
  color: var(--color-text-placeholder);
}
</style>
