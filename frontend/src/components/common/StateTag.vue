<template>
  <span class="state-tag" :class="[`state-${state.state_type}`, { compact }]">
    <span class="state-dot" />
    {{ state.name }}
  </span>
</template>

<script setup lang="ts">
import type { TicketState } from '@/types'

withDefaults(defineProps<{ state: TicketState; compact?: boolean }>(), { compact: false })
</script>

<style scoped>
.state-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}

.state-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.state-new {
  background: var(--color-primary-light);
  color: #4338CA;
}
.state-new .state-dot { background: #635BFF; }

.state-open {
  background: var(--color-warning-light);
  color: var(--color-warning-text);
}
.state-open .state-dot { background: var(--color-warning); }

.state-pending {
  background: var(--color-info-light);
  color: var(--color-info-text);
}
.state-pending .state-dot { background: var(--color-info); }

.state-closed {
  background: var(--color-success-light);
  color: var(--color-success-text);
}
.state-closed .state-dot { background: var(--color-success); }

.state-merged {
  background: #E2E8F0;
  color: #334155;
}
.state-merged .state-dot { background: #64748B; }

.state-tag.compact {
  padding: 1px 7px;
  font-size: 11px;
}
.state-tag.compact .state-dot {
  width: 5px;
  height: 5px;
}
</style>
