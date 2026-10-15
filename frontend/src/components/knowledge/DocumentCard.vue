<template>
  <button ref="card" class="document-card" type="button" @click="emit('open')">
    <DocumentCover :title="title" :file-type="fileType" />
    <div class="card-copy">
      <h3>{{ title }}</h3>
      <p class="card-summary">{{ summary || (presentationState === 'loading' ? '正在加载文档摘要…' : '暂无文档摘要') }}</p>
      <div v-if="tags.length" class="card-tags"><span v-for="tag in tags.slice(0, 3)" :key="tag">{{ tag }}</span></div>
      <div class="card-meta"><span>{{ fileType || 'FILE' }}</span><span>{{ updatedAt || '更新时间未提供' }}</span></div>
    </div>
  </button>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import DocumentCover from './DocumentCover.vue'
defineProps<{ title: string; fileType: string; summary: string; tags: string[]; updatedAt: string; presentationState: string }>()
const emit = defineEmits<{ (event: 'open'): void; (event: 'visible'): void }>()
const card = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null
onMounted(() => {
  if (!('IntersectionObserver' in window)) { emit('visible'); return }
  observer = new IntersectionObserver(entries => { if (entries[0]?.isIntersecting) { emit('visible'); observer?.disconnect() } }, { rootMargin: '200px' })
  if (card.value) observer.observe(card.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.document-card{min-width:0;width:100%;display:flex;flex-direction:column;text-align:left;border:1px solid #e9eae6;border-radius:11px;padding:20px;background:#fff;cursor:pointer;color:#1d2530;box-shadow:0 3px 16px rgba(26,34,29,.025);transition:border-color .18s,box-shadow .18s}.document-card:hover,.document-card:focus-visible{border-color:#a8ad83;box-shadow:0 9px 25px rgba(48,55,40,.1);outline:none}.card-copy{display:flex;flex:1;flex-direction:column;min-height:154px;padding:15px 1px 0}.card-copy h3{margin:0;font-size:15px;line-height:1.45;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.card-summary{margin:6px 0 10px;color:#788294;font-size:13px;line-height:1.55;min-height:40px;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}.card-tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:auto}.card-tags span{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:3px 9px;border-radius:5px;background:#f0f1e9;color:#5e654e;font-size:11px}.card-meta{display:flex;gap:12px;justify-content:space-between;margin-top:auto;padding-top:13px;color:#7b8491;font-size:12px}.card-tags+.card-meta{margin-top:0}.card-meta span:first-child{font-weight:700;color:#5c6978}
</style>
