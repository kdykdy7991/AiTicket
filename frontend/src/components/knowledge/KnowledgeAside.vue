<template>
  <aside class="knowledge-aside">
    <!-- 仅在存在图片资产时渲染，没有图片则整个模块消失 -->
    <section v-if="assets.length" class="aside-section">
      <h3>相关图片（{{ assets.length }}）</h3>
      <ul class="asset-grid">
        <li v-for="asset in assets" :key="asset.id">
          <button type="button" class="asset-item" @click="emit('preview-asset', asset)">
            <img
              v-if="!failed.has(asset.id)"
              :src="asset.url"
              :alt="asset.caption || '知识图片'"
              loading="lazy"
              @error="failed.add(asset.id)"
            />
            <span v-else class="asset-failed">图片加载失败</span>
          </button>
          <p v-if="asset.caption" class="asset-caption">{{ asset.caption }}</p>
        </li>
      </ul>
    </section>

    <section v-if="relatedDocuments.length" class="aside-section">
      <h3>相关文档（{{ relatedDocuments.length }}）</h3>
      <ul class="doc-list">
        <li v-for="document in relatedDocuments" :key="document.documentId">
          <button type="button" class="doc-item" @click="emit('select-document', document.documentId)">
            <span class="doc-name">{{ document.documentName }}</span>
            <span v-if="document.tag" class="doc-tag">{{ document.tag }}</span>
          </button>
        </li>
      </ul>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import type { KnowledgeAsset, KnowledgeRelatedDocument } from '@/types/knowledge'

defineProps<{ assets: KnowledgeAsset[]; relatedDocuments: KnowledgeRelatedDocument[] }>()
const emit = defineEmits<{
  (event: 'preview-asset', asset: KnowledgeAsset): void
  (event: 'select-document', documentId: string): void
}>()

const failed = reactive(new Set<string>())
</script>

<style scoped>
.knowledge-aside { min-width: 0; }
.aside-section { padding: 15px 15px 17px; background: #fff; border-radius: 7px; }
.aside-section + .aside-section { margin-top: 10px; }
.aside-section h3 { margin: 0 0 12px; font-size: 14px; font-weight: 700; color: #1c2836; }
.asset-grid { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.asset-item { display: block; width: 100%; padding: 0; border: 1px solid #edf0f2; border-radius: 5px; background: #f6f7f8; overflow: hidden; cursor: pointer; }
.asset-item:hover { border-color: #aeb992; }
.asset-item img { display: block; width: 100%; height: 76px; object-fit: cover; }
.asset-failed { display: block; padding: 24px 8px; color: #8d98a6; font-size: 11px; }
.asset-caption { margin: 6px 0 0; color: #47566a; font-size: 11.5px; line-height: 1.45; text-align: center; }
.doc-list { list-style: none; margin: 0; padding: 0; }
.doc-item { display: flex; align-items: center; justify-content: space-between; gap: 7px; width: 100%; border: 0; background: transparent; text-align: left; padding: 10px 0; color: #223143; cursor: pointer; }
.doc-item::before { content: '▤'; flex: none; color: #3e5166; font-size: 17px; }
.doc-item:hover .doc-name { color: #6d753f; }
.doc-name { min-width: 0; flex: 1; font-size: 12px; line-height: 1.45; }
.doc-tag { flex: none; border-radius: 4px; background: #f5f1e7; padding: 2px 6px; color: #96804d; font-size: 10px; }
</style>
