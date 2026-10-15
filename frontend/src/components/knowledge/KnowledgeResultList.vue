<template>
  <div class="result-list">
    <div v-if="loading" class="skeleton-list" aria-busy="true">
      <div v-for="index in 4" :key="index" class="skeleton-item">
        <span class="skeleton-line title" />
        <span class="skeleton-line" />
        <span class="skeleton-line short" />
      </div>
    </div>
    <template v-else>
      <button
        v-for="result in results"
        :key="result.key"
        type="button"
        class="result-item"
        :class="{ selected: result.key === activeKey }"
        @click="emit('select', result)"
      >
        <span class="result-title">{{ result.documentName }}</span>
        <span class="result-sub">
          <span v-if="result.heading" class="result-tag">{{ result.heading }}</span>
          <span v-if="result.page">第 {{ result.page }} 页</span>
        </span>
        <p class="result-snippet">
          <i v-if="result.hasPresentation" class="ready-dot" title="已生成文档摘要" />
          <template v-for="(part, index) in parts(result.snippet)" :key="index">
            <mark v-if="part.hit">{{ part.text }}</mark><span v-else>{{ part.text }}</span>
          </template>
        </p>
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { KnowledgeSearchResult } from '@/types/knowledge'

const props = withDefaults(defineProps<{
  results: KnowledgeSearchResult[]
  activeKey: string
  loading: boolean
  query?: string
}>(), { query: '' })

const emit = defineEmits<{ (event: 'select', result: KnowledgeSearchResult): void }>()

function parts(value: string): { text: string; hit: boolean }[] {
  const needle = props.query.trim().toLocaleLowerCase()
  if (!needle) return [{ text: value, hit: false }]
  const lower = value.toLocaleLowerCase()
  const output: { text: string; hit: boolean }[] = []
  let start = 0
  while (start < value.length) {
    const match = lower.indexOf(needle, start)
    if (match < 0) { output.push({ text: value.slice(start), hit: false }); break }
    if (match > start) output.push({ text: value.slice(start, match), hit: false })
    output.push({ text: value.slice(match, match + needle.length), hit: true })
    start = match + needle.length
  }
  return output
}
</script>

<style scoped>
.result-list { display: flex; flex-direction: column; padding: 0 9px 10px 0; }
.result-item { position: relative; display: block; width: 100%; min-height: 96px; border: 0; border-left: 2px solid transparent; border-radius: 0 7px 7px 0; background: transparent; text-align: left; padding: 13px 15px 11px 64px; color: #1d2938; cursor: pointer; }
.result-item::before { content: ''; position: absolute; left: 22px; top: 16px; width: 28px; height: 28px; border-radius: 7px; background: #f6f7f8; }
.result-item::after { content: '▤'; position: absolute; left: 29px; top: 18px; font-size: 20px; line-height: 24px; color: #2c4056; }
.result-item:hover { background: #f8f9f7; }
.result-item.selected { background: #f1f4ef; border-left-color: #adb98e; }
.result-item.selected::after { color: #656b37; }
.result-title { display: block; font-size: 13.5px; font-weight: 650; line-height: 1.5; }
.result-sub { display: flex; align-items: center; gap: 8px; margin-top: 4px; color: #8995a7; font-size: 11.5px; }
.result-tag { border-radius: 4px; background: #f7f1e4; padding: 2px 6px; color: #9a7937; font-size: 11px; }
.result-snippet { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; margin: 6px 0 0; color: #7c8b9d; font-size: 12px; line-height: 1.5; }
.ready-dot { display: inline-block; width: 5px; height: 5px; margin-right: 4px; border-radius: 50%; background: #9da980; vertical-align: middle; }
mark { background: #e9eddd; color: #424b30; border-radius: 2px; }
.skeleton-item { padding: 16px 18px; border-bottom: 1px solid #edf0f2; }
.skeleton-line { display: block; height: 10px; border-radius: 4px; margin-top: 8px; background: #edf0f2; }
.skeleton-line.title { width: 62%; height: 13px; margin-top: 0; }
.skeleton-line.short { width: 40%; }
</style>
