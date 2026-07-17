<template>
  <span class="datetime-label">
    <span class="date-part">{{ datePart }}</span>
    <span class="time-part">{{ timePart }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  iso: string
}>()

const datePart = computed(() => {
  const d = new Date(props.iso)
  return d.toLocaleDateString('zh-CN')
})

const timePart = computed(() => {
  const d = new Date(props.iso)
  return d.toLocaleTimeString('zh-CN', { hour12: false })
})
</script>

<style scoped>
.datetime-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.date-part {
  color: var(--color-text-secondary);
}

.time-part {
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}
</style>
