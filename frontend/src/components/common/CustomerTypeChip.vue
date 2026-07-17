<template>
  <span class="customer-type-chip" :class="`type-${type}`" v-if="type">
    <svg v-if="type === 'enterprise'" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 21h18M5 21V7l7-4 7 4v14M9 9h.01M9 13h.01M9 17h.01M15 9h.01M15 13h.01M15 17h.01"/>
    </svg>
    <svg v-else width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
      <circle cx="12" cy="7" r="4"/>
    </svg>
    <span>{{ type === 'enterprise' ? '政企' : '个人' }}</span>
  </span>
</template>

<script setup lang="ts">
import type { CustomerType } from '@/types'

defineProps<{ type: CustomerType | null | undefined }>()
</script>

<style scoped>
.customer-type-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
  white-space: nowrap;
}

.type-enterprise {
  background: linear-gradient(135deg, #FEF3C7, #FDE68A);
  color: #92400E;
  border: 1px solid #F59E0B;
}

.type-personal {
  background: var(--color-bg-subtle);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
}
</style>
