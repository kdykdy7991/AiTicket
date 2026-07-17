<template>
  <span class="user-avatar-wrapper" v-if="user">
    <span
      class="avatar-circle"
      :style="{ width: `${size}px`, height: `${size}px`, background: gradientBg, fontSize: `${Math.max(10, size * 0.42)}px` }"
    >
      {{ user.firstname.charAt(0) }}
    </span>
    <span v-if="showName" class="name">{{ user.firstname }}{{ user.lastname }}</span>
  </span>
  <span v-else class="user-avatar-wrapper">
    <span
      class="avatar-circle avatar-empty"
      :style="{ width: `${size}px`, height: `${size}px`, fontSize: `${Math.max(10, size * 0.42)}px` }"
    >?</span>
    <span v-if="showName" class="name unassigned">未分配</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { User } from '@/types'

const props = withDefaults(defineProps<{
  user: User | null
  size?: number
  showName?: boolean
}>(), {
  size: 28,
})

const gradients = [
  'linear-gradient(135deg, #635BFF, #8B85FF)',
  'linear-gradient(135deg, #10B981, #34D399)',
  'linear-gradient(135deg, #F59E0B, #FBBF24)',
  'linear-gradient(135deg, #EF4444, #F87171)',
  'linear-gradient(135deg, #8B5CF6, #A78BFA)',
  'linear-gradient(135deg, #EC4899, #F472B6)',
  'linear-gradient(135deg, #06B6D4, #22D3EE)',
]

const gradientBg = computed(() => {
  if (!props.user) return '#E5E7EB'
  return gradients[props.user.id % gradients.length]
})
</script>

<style scoped>
.user-avatar-wrapper {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.avatar-circle {
  border-radius: var(--radius-full);
  color: #fff;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  letter-spacing: 0;
}
.avatar-empty {
  background: var(--color-border);
  color: var(--color-text-tertiary);
}
.name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}
.unassigned {
  color: var(--color-text-placeholder);
}
</style>
