<template>
  <el-dialog
    :model-value="visible"
    width="760px"
    align-center
    append-to-body
    class="asset-dialog ticket-dark-dialog"
    :show-close="true"
    @update:model-value="emit('close')"
  >
    <template #header>
      <span class="dialog-title">{{ asset?.caption || '知识图片' }}</span>
    </template>
    <div class="asset-preview">
      <img v-if="asset && !failed" :src="asset.url" :alt="asset.caption || '知识图片'" @error="failed = true" />
      <p v-else class="asset-failed">图片加载失败，请稍后重试</p>
    </div>
    <p v-if="asset?.caption" class="asset-caption">{{ asset.caption }}</p>
    <p class="asset-note">图片为知识派生资产，不提供原文件下载</p>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { KnowledgeAsset } from '@/types/knowledge'

const props = defineProps<{ asset: KnowledgeAsset | null; visible: boolean }>()
const emit = defineEmits<{ (event: 'close'): void }>()

const failed = ref(false)
watch(() => props.asset?.id, () => { failed.value = false })
</script>

<style scoped>
.asset-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
}
.asset-preview img { display: block; max-width: 100%; max-height: 60vh; object-fit: contain; }
.asset-failed { color: var(--color-text-tertiary); font-size: 13px; }
.dialog-title { font-size: 14px; font-weight: 600; }
.asset-caption { margin-top: 12px; font-size: 13px; color: var(--color-text-secondary); line-height: 1.7; }
.asset-note { margin-top: 4px; font-size: 12px; color: var(--color-text-tertiary); }
</style>
