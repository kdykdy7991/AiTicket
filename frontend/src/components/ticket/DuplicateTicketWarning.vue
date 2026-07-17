<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="(v) => emit('update:modelValue', v)"
    title="疑似重复工单"
    width="640px"
    :show-close="false"
    :close-on-click-modal="false"
    align-center
  >
    <div class="duplicate-warning">
      <div class="warning-banner">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <div>
          <div class="banner-title">检测到 {{ candidates.length }} 条疑似重复工单</div>
          <div class="banner-sub">同一手机号 + 设备 SN + 一级分类在 30 天内有未关闭工单，请确认是否关联</div>
        </div>
      </div>

      <div class="candidate-list">
        <div
          v-for="t in candidates"
          :key="t.id"
          class="candidate-item"
          :class="{ selected: selectedId === t.id }"
          @click="selectedId = t.id"
        >
          <div class="candidate-radio">
            <div class="radio-circle" :class="{ active: selectedId === t.id }" />
          </div>
          <div class="candidate-body">
            <div class="candidate-header">
              <span class="candidate-number">{{ t.number }}</span>
              <StateTag :state="t.state" :compact="true" />
              <span class="candidate-date">{{ formatDate(t.created_at) }}</span>
            </div>
            <div class="candidate-meta">
              <span v-if="t.device_sn">SN: {{ t.device_sn }}</span>
              <span>{{ t.customer_phone }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="onIgnore">忽略，仍创建新工单</el-button>
        <el-button type="primary" @click="onConfirm" :disabled="selectedId === null">
          关联到选中工单并创建
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import StateTag from '@/components/common/StateTag.vue'
import type { DuplicateTicket } from '@/types'

const props = defineProps<{
  modelValue: boolean
  candidates: DuplicateTicket[]
}>()

const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  confirm: [duplicateOfId: number | null]
}>()

const selectedId = ref<number | null>(null)

watch(() => props.modelValue, (v) => {
  if (v) selectedId.value = props.candidates[0]?.id ?? null
})

function onConfirm() {
  emit('confirm', selectedId.value)
  emit('update:modelValue', false)
}

function onIgnore() {
  emit('confirm', null)
  emit('update:modelValue', false)
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
}
</script>

<style scoped>
.duplicate-warning {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.warning-banner {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  background: #FEF3C7;
  border: 1px solid #FCD34D;
  border-radius: var(--radius-md);
  color: #92400E;
}

.warning-banner svg {
  flex-shrink: 0;
  margin-top: 2px;
}

.banner-title {
  font-size: 14px;
  font-weight: 600;
}

.banner-sub {
  font-size: 12.5px;
  margin-top: 2px;
  opacity: 0.85;
}

.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.candidate-item {
  display: flex;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.candidate-item:hover {
  background: var(--color-bg-subtle);
  border-color: var(--color-border);
}

.candidate-item.selected {
  background: rgba(99, 91, 255, 0.04);
  border-color: var(--color-primary);
}

.candidate-radio {
  display: flex;
  align-items: flex-start;
  padding-top: 2px;
}

.radio-circle {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid var(--color-border);
  position: relative;
  transition: all var(--duration-fast) var(--ease-out);
}

.radio-circle.active {
  border-color: var(--color-primary);
}

.radio-circle.active::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-primary);
}

.candidate-body {
  flex: 1;
  min-width: 0;
}

.candidate-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.candidate-number {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12.5px;
  color: var(--color-text-tertiary);
  font-weight: 600;
}

.candidate-date {
  font-size: 11.5px;
  color: var(--color-text-tertiary);
  margin-left: auto;
}

.candidate-meta {
  display: flex;
  gap: 12px;
  font-size: 11.5px;
  color: var(--color-text-tertiary);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
