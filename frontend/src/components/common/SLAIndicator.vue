<template>
  <div class="sla-indicator" v-if="escalationAt">
    <div class="sla-bar-track">
      <div
        class="sla-bar-fill"
        :style="{ width: `${percentage}%`, background: barColor }"
      />
    </div>
    <span class="sla-text" :class="{ overdue: isOverdue, warning: isWarning }">
      {{ remainingText }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'

const props = defineProps<{
  escalationAt: string | null
  totalMinutes?: number
}>()

const total = computed(() => props.totalMinutes || 240)

const remaining = computed(() => {
  if (!props.escalationAt) return total.value
  return dayjs(props.escalationAt).diff(dayjs(), 'minute')
})

const percentage = computed(() => {
  const used = total.value - remaining.value
  return Math.min(100, Math.max(0, (used / total.value) * 100))
})

const isOverdue = computed(() => remaining.value <= 0)
const isWarning = computed(() => !isOverdue.value && percentage.value >= 80)

const barColor = computed(() => {
  if (isOverdue.value) return 'var(--color-danger)'
  if (isWarning.value) return 'var(--color-warning)'
  return 'var(--color-primary)'
})

const remainingText = computed(() => {
  if (isOverdue.value) {
    const overMin = Math.abs(remaining.value)
    if (overMin >= 60) return `已超时 ${Math.floor(overMin / 60)}h${overMin % 60}m`
    return `已超时 ${overMin}m`
  }
  const min = remaining.value
  if (min >= 60) return `剩余 ${Math.floor(min / 60)}h${min % 60}m`
  return `剩余 ${min}m`
})
</script>

<style scoped>
.sla-indicator {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sla-bar-track {
  height: 4px;
  background: var(--color-bg-hover);
  border-radius: var(--radius-full);
  overflow: hidden;
}
.sla-bar-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width var(--duration-slow) var(--ease-out);
}

.sla-text {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}
.sla-text.overdue { color: var(--color-danger); }
.sla-text.warning { color: var(--color-warning); }
</style>
