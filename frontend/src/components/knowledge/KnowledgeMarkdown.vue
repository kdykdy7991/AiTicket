<template>
  <div class="knowledge-markdown" v-html="html" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderKnowledgeMarkdown } from '@/utils/knowledgeMarkdown'

const props = withDefaults(defineProps<{ text: string; query?: string }>(), { query: '' })

// markdown-it：GFM 表格可用，原始 HTML 关闭，片段中的图片以文本呈现（图片只走资产区）
const html = computed(() => renderKnowledgeMarkdown(props.text || '', props.query))
</script>

<style scoped>
.knowledge-markdown {
  color: var(--color-text-primary);
  font-size: 14px;
  line-height: 1.75;
  overflow-wrap: anywhere;
  min-width: 0;
}
.knowledge-markdown :deep(> :first-child) { margin-top: 0; }
.knowledge-markdown :deep(> :last-child) { margin-bottom: 0; }
.knowledge-markdown :deep(p),
.knowledge-markdown :deep(ul),
.knowledge-markdown :deep(ol),
.knowledge-markdown :deep(blockquote),
.knowledge-markdown :deep(pre) { margin: 8px 0; }
.knowledge-markdown :deep(h1),
.knowledge-markdown :deep(h2),
.knowledge-markdown :deep(h3),
.knowledge-markdown :deep(h4) {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
}
.knowledge-markdown :deep(ul),
.knowledge-markdown :deep(ol) { padding-left: 22px; }
.knowledge-markdown :deep(li) { margin: 2px 0; }
.knowledge-markdown :deep(blockquote) {
  border-left: 2px solid var(--color-border);
  padding-left: 12px;
  color: var(--color-text-secondary);
}
.knowledge-markdown :deep(code) { font-size: 12.5px; }
.knowledge-markdown :deep(pre) {
  overflow-x: auto;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  padding: 12px;
}
.knowledge-markdown :deep(hr) { border: 0; border-top: 1px solid var(--color-border-light); margin: 14px 0; }
/* 表格过宽时横向滚动，不撑破主内容区 */
.knowledge-markdown :deep(.knowledge-table-scroll) {
  max-width: 100%;
  overflow-x: auto;
  margin: 12px 0;
}
.knowledge-markdown :deep(table) {
  border-collapse: collapse;
  width: max-content;
  min-width: 100%;
  font-size: 13px;
}
.knowledge-markdown :deep(th),
.knowledge-markdown :deep(td) {
  border: 1px solid var(--color-border);
  padding: 7px 10px;
  text-align: left;
  vertical-align: top;
}
.knowledge-markdown :deep(th) {
  background: var(--color-bg-subtle);
  font-weight: 600;
  white-space: nowrap;
}
.knowledge-markdown :deep(mark) {
  background: #fff3cd;
  color: inherit;
  border-radius: 2px;
  padding: 0 1px;
}
</style>
