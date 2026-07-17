<template>
  <span class="priority-icon" :title="priority.name">
    <span class="priority-dot" :style="{ background: priority.ui_color, boxShadow: `0 0 0 3px ${priority.ui_color}20` }" />
    <span v-if="showLabel" class="priority-label">{{ priority.name }}</span>
  </span>
</template>

<script setup lang="ts">
import type { TicketPriority } from '@/types'

defineProps<{
  priority: TicketPriority
  showLabel?: boolean
}>()
</script>

<style scoped>
.priority-icon {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.priority-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.priority-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  font-weight: 500;
}
</style>
