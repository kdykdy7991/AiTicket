<template>
  <el-popover
    v-model:visible="visible"
    trigger="click"
    placement="bottom-end"
    :width="292"
    :show-arrow="true"
    popper-class="date-range-popover ticket-list-date-popper"
  >
    <template #reference>
      <button
        type="button"
        class="dr-trigger"
        :class="{ 'is-active': hasValue, 'is-open': visible }"
        :title="triggerTitle"
      >
        <svg
          class="dr-trigger__icon"
          width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
        >
          <rect x="3" y="4" width="18" height="18" rx="2" />
          <line x1="16" y1="2" x2="16" y2="6" />
          <line x1="8" y1="2" x2="8" y2="6" />
          <line x1="3" y1="10" x2="21" y2="10" />
        </svg>
        <span class="dr-trigger__text">{{ triggerLabel }}</span>
        <span
          v-if="hasValue"
          class="dr-trigger__clear"
          role="button"
          title="清除时间筛选"
          @click.stop="onClear"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </span>
        <svg
          v-else
          class="dr-trigger__chev"
          width="12" height="12" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
        >
          <polyline points="6,9 12,15 18,9" />
        </svg>
      </button>
    </template>

    <div class="dr-panel">
      <div class="dr-panel__title">{{ panelTitle }}</div>

      <div class="dr-presets">
        <button
          v-for="p in presets"
          :key="p.key"
          type="button"
          class="dr-preset"
          :class="{ 'is-active': p.key === activePreset }"
          @click="applyPreset(p)"
        >
          {{ p.label }}
        </button>
      </div>

      <div class="dr-custom">
        <div class="dr-section-label">自定义区间</div>
        <div class="dr-fields">
          <label class="dr-field">
            <input
              v-model="draftFrom"
              type="date"
              class="dr-field__input"
              :max="draftTo || undefined"
            >
          </label>
          <span class="dr-fields__sep">→</span>
          <label class="dr-field">
            <input
              v-model="draftTo"
              type="date"
              class="dr-field__input"
              :min="draftFrom || undefined"
            >
          </label>
        </div>
        <p v-if="rangeInvalid" class="dr-error">开始日期不能晚于结束日期</p>
      </div>

      <div class="dr-actions">
        <button type="button" class="dr-btn" :disabled="!hasValue" @click="onClear">清除</button>
        <button
          type="button"
          class="dr-btn dr-btn--primary"
          :disabled="!canApply"
          @click="applyCustom"
        >
          应用
        </button>
      </div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import dayjs from 'dayjs'
import type { DateRangeValue } from '@/types'

const props = defineProps<{
  from?: string | null
  to?: string | null
  /** 触发按钮与面板标题，默认「选择时间」 */
  label?: string
}>()

const emit = defineEmits<{ change: [value: DateRangeValue] }>()

const DATE_FMT = 'YYYY-MM-DD'
const visible = ref(false)
const draftFrom = ref('')
const draftTo = ref('')

const fieldLabel = computed(() => props.label || '选择时间')

const hasValue = computed(() => !!(props.from || props.to))

/** 弹层打开时用当前值初始化草稿，关闭时丢弃未应用的修改 */
watch(visible, (open) => {
  if (open) {
    draftFrom.value = props.from || ''
    draftTo.value = props.to || ''
  }
})

interface Preset {
  key: string
  label: string
  from: string
  to: string
}

const presets = computed<Preset[]>(() => {
  const today = dayjs().startOf('day')
  const f = (d: dayjs.Dayjs) => d.format(DATE_FMT)
  const lastMonth = today.subtract(1, 'month')
  const quarterStartMonth = Math.floor(today.month() / 3) * 3
  return [
    { key: 'today', label: '今天', from: f(today), to: f(today) },
    { key: 'yesterday', label: '昨天', from: f(today.subtract(1, 'day')), to: f(today.subtract(1, 'day')) },
    { key: 'last7', label: '近 7 天', from: f(today.subtract(6, 'day')), to: f(today) },
    { key: 'last30', label: '近 30 天', from: f(today.subtract(29, 'day')), to: f(today) },
    { key: 'thisMonth', label: '本月', from: f(today.startOf('month')), to: f(today.endOf('month')) },
    { key: 'lastMonth', label: '上月', from: f(lastMonth.startOf('month')), to: f(lastMonth.endOf('month')) },
    { key: 'thisQuarter', label: '本季度', from: f(today.month(quarterStartMonth).startOf('month')), to: f(today.month(quarterStartMonth + 2).endOf('month')) },
    { key: 'thisYear', label: '今年', from: f(today.startOf('year')), to: f(today.endOf('year')) },
  ]
})

/** 当前选中区间若与某个快捷项一致，高亮该快捷项 */
const activePreset = computed(() => {
  const match = presets.value.find(p => p.from === (props.from || '') && p.to === (props.to || ''))
  return match?.key || ''
})

const rangeInvalid = computed(
  () => !!draftFrom.value && !!draftTo.value && draftFrom.value > draftTo.value,
)
const canApply = computed(
  () => !rangeInvalid.value && !!(draftFrom.value || draftTo.value),
)

/** 面板标题 */
const panelTitle = computed(() => fieldLabel.value)

/** 触发按钮文案：未选中显示字段名，选中后显示紧凑区间 */
const triggerLabel = computed(() => {
  if (!hasValue.value) return fieldLabel.value
  const from = props.from
  const to = props.to
  if (from && to && from === to) return compact(from)
  if (from && to) return from.slice(0, 4) === to.slice(0, 4)
    ? `${compact(from)} — ${to.slice(5)}`
    : `${from} — ${to}`
  return from ? `${from} 起` : `至 ${to}`
})

const triggerTitle = computed(() => {
  const name = fieldLabel.value
  return hasValue.value ? `${name}：${props.from || '不限'} ~ ${props.to || '不限'}` : name
})

/** 同年省略年份，压缩显示长度 */
function compact(date: string) {
  const now = dayjs().format(DATE_FMT)
  return date.slice(0, 4) === now.slice(0, 4) ? date.slice(5) : date
}

function applyPreset(p: Preset) {
  emit('change', { from: p.from, to: p.to })
  visible.value = false
}

function applyCustom() {
  if (!canApply.value) return
  let from = draftFrom.value || null
  let to = draftTo.value || null
  // 只填一端时视为开放区间；两端都填但顺序颠倒时自动交换
  if (from && to && from > to) [from, to] = [to, from]
  emit('change', { from, to })
  visible.value = false
}

function onClear() {
  draftFrom.value = ''
  draftTo.value = ''
  emit('change', { from: null, to: null })
  visible.value = false
}
</script>

<style scoped>
.dr-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  background: var(--color-bg-subtle);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}
.dr-trigger:hover {
  border-color: var(--color-border);
  color: var(--color-text-primary);
}
.dr-trigger.is-active {
  background: var(--color-primary-ghost);
  border-color: rgba(99, 91, 255, 0.35);
  color: var(--color-primary);
}
.dr-trigger.is-open {
  border-color: var(--color-primary);
}
.dr-trigger__icon {
  flex: none;
  color: var(--color-text-tertiary);
  transition: color var(--duration-fast) var(--ease-out);
}
.dr-trigger:hover .dr-trigger__icon,
.dr-trigger.is-active .dr-trigger__icon {
  color: currentColor;
}
.dr-trigger__text {
  font-variant-numeric: tabular-nums;
}
.dr-trigger__clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-right: -2px;
  border-radius: var(--radius-full);
  color: var(--color-text-tertiary);
  transition: all var(--duration-fast) var(--ease-out);
}
.dr-trigger__clear:hover {
  background: rgba(17, 24, 39, 0.1);
  color: var(--color-text-primary);
}
.dr-trigger__chev {
  flex: none;
  color: var(--color-text-tertiary);
  transition: transform var(--duration-fast) var(--ease-out);
}
.dr-trigger.is-open .dr-trigger__chev {
  transform: rotate(180deg);
}

.dr-panel__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 10px;
}

.dr-presets {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
}
.dr-preset {
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  background: var(--color-bg-subtle);
  color: var(--color-text-secondary);
  font-family: var(--font-sans);
  font-size: 13px;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}
.dr-preset:hover {
  background: var(--color-primary-ghost);
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.dr-preset.is-active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
  font-weight: 600;
}

.dr-custom {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-divider);
}
.dr-section-label {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-bottom: 8px;
}
.dr-fields {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dr-field {
  flex: 1;
  min-width: 0;
}
.dr-field__input {
  width: 100%;
  height: 32px;
  padding: 0 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-card);
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  transition: border-color var(--duration-fast) var(--ease-out), box-shadow var(--duration-fast) var(--ease-out);
}
.dr-field__input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-ring);
}
.dr-field__input::-webkit-calendar-picker-indicator {
  cursor: pointer;
  opacity: 0.4;
  transition: opacity var(--duration-fast) var(--ease-out);
}
.dr-field__input::-webkit-calendar-picker-indicator:hover {
  opacity: 0.8;
}
.dr-fields__sep {
  color: var(--color-text-placeholder);
  font-size: 12px;
}
.dr-error {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-danger);
}

.dr-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
.dr-btn {
  height: 30px;
  padding: 0 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-card);
  color: var(--color-text-secondary);
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}
.dr-btn:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.dr-btn--primary {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}
.dr-btn--primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
  border-color: var(--color-primary-hover);
  color: #fff;
}
.dr-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>

<!-- 弹层被 teleport 到 body，popper 根节点不携带 scoped 属性，需全局样式 -->
<style>
.date-range-popover.el-popover {
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  border: 1px solid var(--color-border-light);
}
</style>
