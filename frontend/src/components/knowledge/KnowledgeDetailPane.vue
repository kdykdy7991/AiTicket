<template>
  <article class="detail-pane">
    <header class="detail-head">
      <div class="head-main">
        <h2>{{ result.documentName }}</h2>
        <p class="detail-meta">
          <span v-if="result.heading" class="meta-tag">{{ result.heading }}</span>
          <span v-if="collectionName">{{ collectionName }}</span>
          <template v-if="result.page"> · 第 {{ result.page }} 页</template>
        </p>
      </div>
      <div class="head-actions">
        <button type="button" class="ghost-btn" @click="emit('open-window')">在新窗口打开</button>
        <button type="button" class="primary-btn" :class="{ active: favorite }" @click="emit('toggle-favorite')">
          <span class="plus">{{ favorite ? '✓' : '+' }}</span>{{ favorite ? '已加入常用' : '加入常用' }}
        </button>
      </div>
    </header>

    <!-- 文档摘要：来自 presentation.summary，不是 AI 回答 -->
    <section v-if="summaryVisible" class="detail-section">
      <h3>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/><path d="M9 13h6M9 17h4"/></svg>
        文档摘要
      </h3>
      <div v-if="presentationLoading" class="local-loading">
        <span class="skeleton-line" /><span class="skeleton-line short" />
      </div>
      <p v-else-if="presentation.status === 'pending'" class="muted">摘要生成中</p>
      <p v-else-if="presentation.status === 'failed'" class="muted">暂未生成文档摘要</p>
      <p v-else class="summary-text">{{ presentation.summary }}</p>
    </section>

    <!-- 重点内容：文档重点，不做成处理步骤 -->
    <section v-if="keyPointsVisible" class="detail-section">
      <h3>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l2.4 5 5.6.8-4 4 1 5.6-5-2.7-5 2.7 1-5.6-4-4 5.6-.8Z"/></svg>
        重点内容
      </h3>
      <div v-if="presentationLoading" class="local-loading">
        <span class="skeleton-line" /><span class="skeleton-line" /><span class="skeleton-line short" />
      </div>
      <ul v-else class="key-points">
        <li v-for="(point, index) in presentation.keyPoints" :key="index">{{ point }}</li>
      </ul>
    </section>

    <!-- 当前查询命中的相关片段 -->
    <section class="detail-section">
      <div class="section-head">
        <h3>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.8 1.8"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.8-1.8"/></svg>
          相关命中片段（{{ snippets.length }}）
        </h3>
        <button type="button" class="link-btn" @click="emit('view-source')">查看原文片段 ›</button>
      </div>
      <div v-for="snippet in snippets" :key="snippet.chunkId" class="snippet" :class="{ current: snippet.current }">
        <p v-if="snippet.heading" class="snippet-title">{{ snippet.heading }}</p>
        <KnowledgeMarkdown :text="snippet.text" :query="query" />
        <div class="snippet-foot">
          <span class="snippet-source">
            <i v-if="snippet.current" class="hit-flag">当前命中</i>
            来源：{{ result.documentName }}
          </span>
          <span v-if="snippet.page" class="page-chip">第 {{ snippet.page }} 页</span>
        </div>
      </div>
    </section>

    <section class="detail-section">
      <button type="button" class="text-action" :disabled="contextLoading" @click="emit('toggle-context')">
        {{ contextOpen ? '收起上下文' : '展开上下文' }}
      </button>
      <div v-if="contextLoading" class="local-loading">
        <span class="skeleton-line" /><span class="skeleton-line short" />
      </div>
      <div v-else-if="contextOpen" class="context-list">
        <div v-for="chunk in contextChunks" :key="chunk.position" class="context-block" :class="{ current: chunk.position === 'current' }">
          <p class="snippet-meta">
            <span>{{ chunk.label }}</span>
            <span v-if="chunk.page">第 {{ chunk.page }} 页</span>
          </p>
          <KnowledgeMarkdown :text="chunk.text" :query="query" />
        </div>
      </div>
    </section>

    <footer class="source-info">
      来源：{{ collectionName }} · {{ result.documentName }}
      <span class="source-note">页面仅展示知识内容与派生图片，不提供原文件预览与下载</span>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import KnowledgeMarkdown from '@/components/knowledge/KnowledgeMarkdown.vue'
import type { KnowledgeContextChunk, KnowledgePresentation, KnowledgeSearchResult, KnowledgeSnippet } from '@/types/knowledge'

const props = withDefaults(defineProps<{
  result: KnowledgeSearchResult
  presentation: KnowledgePresentation
  presentationLoading?: boolean
  snippets?: KnowledgeSnippet[]
  contextChunks?: KnowledgeContextChunk[]
  contextOpen?: boolean
  contextLoading?: boolean
  collectionName?: string
  query?: string
  favorite?: boolean
}>(), {
  presentationLoading: false,
  snippets: () => [],
  contextChunks: () => [],
  contextOpen: false,
  contextLoading: false,
  collectionName: '',
  query: '',
  favorite: false,
})

const emit = defineEmits<{
  (event: 'toggle-context'): void
  (event: 'toggle-favorite'): void
  (event: 'open-window'): void
  (event: 'view-source'): void
}>()

const summaryVisible = computed(() => {
  if (props.presentationLoading) return true
  if (props.presentation.status === 'pending' || props.presentation.status === 'failed') return true
  return props.presentation.status === 'ready' && !!props.presentation.summary
})
const keyPointsVisible = computed(() => {
  if (props.presentationLoading) return true
  return props.presentation.keyPoints.length > 0
})
</script>

<style scoped>
.detail-pane { min-width: 0; color: #1a2635; }
.detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding: 0 0 14px; }
.head-main { min-width: 0; }
.detail-head h2 { margin: 0; font-size: 16px; font-weight: 700; line-height: 1.45; }
.detail-meta { margin: 7px 0 0; color: #8490a2; font-size: 12px; }
.meta-tag { display: inline-block; margin-right: 7px; border-radius: 3px; padding: 2px 7px; background: #f0f2e8; color: #777b46; font-size: 11px; }
.head-actions { display: flex; gap: 9px; flex: none; }
.ghost-btn, .primary-btn { min-height: 32px; border-radius: 4px; padding: 6px 11px; font-size: 12px; cursor: pointer; white-space: nowrap; }
.ghost-btn { border: 1px solid #e4e9ed; background: #fff; color: #344257; }
.ghost-btn:hover { background: #f8f9fa; }
.primary-btn { display: inline-flex; align-items: center; gap: 6px; border: 1px solid #797b47; background: #797b47; color: #fff; }
.primary-btn:hover { background: #676b38; }
.primary-btn.active { background: #ecede5; border-color: #a4aa80; color: #62683a; }
.plus { font-size: 17px; line-height: 12px; }
.detail-section { margin-top: 12px; }
.detail-section:first-of-type { margin-top: 0; }
.detail-section h3 { display: flex; align-items: center; gap: 9px; margin: 0 0 9px; font-size: 14px; font-weight: 700; color: #1b2634; }
.detail-section h3 svg { width: 22px; height: 22px; padding: 3px; border-radius: 5px; background: #f7f3e4; color: #ab842c; }
.detail-section:has(.summary-text), .detail-section:has(.muted) { border: 1px solid #d6dfc5; background: #fafbf8; border-radius: 5px; padding: 12px 14px; }
.detail-section:has(.key-points) { background: #f8f9fa; border-radius: 5px; padding: 13px 14px; }
.summary-text { margin: 0 0 0 31px; font-size: 12.5px; line-height: 1.8; color: #374253; }
.muted { margin: 0 0 0 31px; font-size: 12px; color: #7c8996; }
.key-points { margin: 0 0 0 34px; padding-left: 15px; }
.key-points li { margin: 3px 0; font-size: 12.5px; line-height: 1.55; color: #46546a; }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.section-head h3 { font-size: 14px; }
.section-head h3 svg { display: none; }
.link-btn { border: 0; background: transparent; padding: 0; font-size: 12px; color: #738099; cursor: pointer; }
.link-btn:hover { color: #646b3c; }
.snippet { position: relative; margin-bottom: 9px; padding: 13px 14px 13px 44px; border: 1px solid #e6eaed; border-radius: 5px; background: #fff; }
.snippet::before { content: '1'; position: absolute; left: 12px; top: 13px; width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; background: #e3e7eb; font-size: 12px; font-weight: 700; color: #455264; }
.snippet.current { background: #fbfcfd; }
.snippet-title { margin: 0 0 5px; font-size: 13px; font-weight: 650; }
.snippet-foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 7px; color: #8995a6; font-size: 11px; }
.snippet-source { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
.hit-flag, .page-chip { font-style: normal; color: #7d8a98; }
.text-action { border: 1px solid #dfe4e8; background: #fff; border-radius: 4px; padding: 7px 11px; font-size: 12px; color: #526176; cursor: pointer; }
.text-action:hover:not(:disabled) { background: #f7f8f5; }
.context-list { margin-top: 10px; }
.context-block { padding: 12px 14px; border: 1px solid #e6eaed; border-radius: 5px; margin-bottom: 8px; }
.context-block.current { background: #f8f9f6; }
.snippet-meta { display: flex; gap: 8px; margin: 0 0 6px; color: #8995a6; font-size: 11px; }
.local-loading { display: flex; flex-direction: column; gap: 8px; }
.skeleton-line { display: block; height: 10px; width: 100%; border-radius: 4px; background: #edf0f2; }
.skeleton-line.short { width: 55%; }
.source-info { margin-top: 18px; padding-top: 12px; border-top: 1px solid #e9ecee; color: #8995a6; font-size: 11px; line-height: 1.7; }
.source-note { display: block; }
@media (max-width: 650px) { .detail-head { flex-direction: column; } .head-actions { flex-wrap: wrap; } }
</style>
