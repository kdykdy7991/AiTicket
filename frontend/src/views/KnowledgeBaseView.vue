<template>
  <div class="knowledge-view">
    <header class="page-heading">
      <div>
        <h1>知识库</h1>
        <p>按知识库浏览文档，或检索问题并查看原文出处</p>
      </div>
      <el-tag v-if="knowledgeMode === 'mock'" type="warning" effect="plain">模拟数据</el-tag>
    </header>

    <el-alert v-if="knowledgeMode === 'mock'" type="info" :closable="false" show-icon class="demo-notice"
      title="当前仅用于页面和接口结构测试；尚未连接 RAG Server 的真实文档。" />

    <div class="workspace">
      <aside class="collection-panel">
        <div class="panel-title">知识库</div>
        <div v-if="loadingCollections" class="muted">加载中…</div>
        <button v-for="item in collections" :key="item.id" type="button"
          class="collection-item" :class="{ selected: selectedCollection === item.id }"
          @click="chooseCollection(item.id)">
          <span class="collection-name">{{ item.name }}</span>
          <span class="collection-count">{{ item.document_count }} 篇</span>
        </button>
        <el-empty v-if="!loadingCollections && collections.length === 0" description="暂无知识库" :image-size="64" />
      </aside>

      <main class="document-panel">
        <template v-if="selectedCollection">
          <div class="toolbar">
            <div>
              <h2>{{ selectedCollectionName }}</h2>
              <span>浏览文档与原文来源</span>
            </div>
            <div class="toolbar-filters">
              <el-input v-model="filterText" clearable placeholder="按文件名筛选" @keyup.enter="loadDocuments()" />
              <el-select v-model="fileType" placeholder="全部格式" style="width: 130px" @change="loadDocuments()">
                <el-option label="全部格式" value="" />
                <el-option label="PDF" value="pdf" />
                <el-option label="SVG" value="svg" />
                <el-option label="文本" value="txt" />
                <el-option label="DOCX" value="docx" />
              </el-select>
              <el-button @click="loadDocuments()">筛选</el-button>
            </div>
          </div>

          <div class="query-bar">
            <el-input v-model="queryText" placeholder="检索当前知识库内容" clearable @keyup.enter="searchKnowledge" />
            <el-button type="primary" :loading="searching" @click="searchKnowledge">检索</el-button>
          </div>

          <section v-if="searchVisible" class="results">
            <div class="section-heading"><h3>检索结果</h3><el-button text @click="searchVisible = false">收起</el-button></div>
            <el-empty v-if="citations.length === 0" description="没有找到相关片段" :image-size="60" />
            <button v-for="item in citations" :key="item.chunk_id" class="citation" type="button" @click="openDocument(item.document_id)">
              <strong>{{ item.document_name }}</strong>
              <p>{{ item.text }}</p>
            </button>
          </section>

          <section class="document-list" v-loading="loadingDocuments">
            <div class="section-heading"><h3>文档</h3><span>{{ documents.length }} 篇</span></div>
            <el-empty v-if="!loadingDocuments && documents.length === 0" description="暂无文档" :image-size="68" />
            <button v-for="item in documents" :key="item.id" class="document-row" type="button" @click="openDocument(item.id)">
              <span class="file-icon">{{ item.file_type.toUpperCase() }}</span>
              <span class="file-main"><strong>{{ item.filename }}</strong><small>{{ formatSize(item.size_bytes) }} · {{ item.status === 'ready' ? '已索引' : item.status }}</small></span>
              <span class="open-label">查看原文 ›</span>
            </button>
            <el-button v-if="nextCursor" class="more-btn" :loading="loadingDocuments" @click="loadMore">加载更多</el-button>
          </section>
        </template>
        <el-empty v-else description="选择一个知识库" />
      </main>
    </div>

    <el-drawer v-model="previewOpen" :title="activeDocument?.filename || '原文预览'" size="min(980px, 92vw)"
      append-to-body modal-class="knowledge-preview-modal" :lock-scroll="true" @closed="clearPreview">
      <div v-loading="loadingPreview" class="preview-body">
        <div v-if="activeDocument" class="preview-meta">
          <span>{{ activeDocument.file_type.toUpperCase() }} · {{ formatSize(activeDocument.size_bytes) }}</span>
          <a v-if="previewUrl" :href="previewUrl" :download="activeDocument.filename">下载原文件</a>
        </div>
        <iframe v-if="activeDocument?.file_type === 'pdf' && previewUrl" :src="previewUrl" class="file-frame" title="PDF 原文" />
        <img v-else-if="activeDocument && ['svg', 'png', 'jpg', 'jpeg', 'gif', 'webp'].includes(activeDocument.file_type) && previewUrl" :src="previewUrl" class="preview-image" alt="原文图片" />
        <pre v-else-if="activeDocument?.file_type === 'txt' && previewText" class="preview-text">{{ previewText }}</pre>
        <div v-else-if="activeDocument?.file_type === 'docx' && previewUrl" class="docx-fallback">
          <p>DOCX 原文已获取。在线渲染效果将在接入真实样本时评估。</p>
          <a :href="previewUrl" :download="activeDocument.filename">下载 DOCX 文件</a>
        </div>
        <el-empty v-else-if="!loadingPreview" description="此文档暂不可预览" />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { knowledgeApi, type KnowledgeCollection, type KnowledgeDocument, type KnowledgeCitation } from '@/api/knowledge'

const collections = ref<KnowledgeCollection[]>([])
const knowledgeMode = ref<'mock' | 'rag' | null>(null)
const selectedCollection = ref('')
const documents = ref<KnowledgeDocument[]>([])
const nextCursor = ref<string | null>(null)
const filterText = ref('')
const fileType = ref('')
const queryText = ref('')
const citations = ref<KnowledgeCitation[]>([])
const searchVisible = ref(false)
const loadingCollections = ref(false)
const loadingDocuments = ref(false)
const searching = ref(false)
const previewOpen = ref(false)
const loadingPreview = ref(false)
const activeDocument = ref<KnowledgeDocument | null>(null)
const previewUrl = ref('')
const previewText = ref('')
const selectedCollectionName = computed(() => collections.value.find(c => c.id === selectedCollection.value)?.name || '')

function formatSize(bytes: number) { return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB` }
function clearPreview() {
  if (previewUrl.value.startsWith('blob:')) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  previewText.value = ''
  activeDocument.value = null
}
function chooseCollection(id: string) {
  selectedCollection.value = id
  filterText.value = ''
  fileType.value = ''
  searchVisible.value = false
  citations.value = []
  loadDocuments()
}
async function loadCollections() {
  loadingCollections.value = true
  try {
    knowledgeMode.value = (await knowledgeApi.status()).mode
    const result = await knowledgeApi.collections()
    collections.value = result.items
    if (result.items[0]) chooseCollection(result.items[0].id)
  } catch { /* API interceptor displays the error */ }
  finally { loadingCollections.value = false }
}
async function loadDocuments(cursor?: string) {
  if (!selectedCollection.value) return
  loadingDocuments.value = true
  try {
    const result = await knowledgeApi.documents(selectedCollection.value, { q: filterText.value, file_type: fileType.value, cursor })
    documents.value = cursor ? [...documents.value, ...result.items] : result.items
    nextCursor.value = result.page_info.next_cursor
  } catch { /* API interceptor displays the error */ }
  finally { loadingDocuments.value = false }
}
function loadMore() { if (nextCursor.value) loadDocuments(nextCursor.value) }
async function searchKnowledge() {
  if (!selectedCollection.value || !queryText.value.trim()) return
  searching.value = true
  try {
    const result = await knowledgeApi.query(selectedCollection.value, queryText.value.trim())
    citations.value = result.citations
    searchVisible.value = true
  } catch { /* API interceptor displays the error */ }
  finally { searching.value = false }
}
async function openDocument(id: string) {
  clearPreview()
  previewOpen.value = true
  loadingPreview.value = true
  try {
    const detail = await knowledgeApi.detail(id)
    activeDocument.value = detail
    if (knowledgeMode.value === 'rag' && detail.file_type === 'pdf') {
      await knowledgeApi.previewSession(id)
      previewUrl.value = knowledgeApi.previewUrl(id)
    } else {
      const file = await knowledgeApi.file(id)
      previewUrl.value = URL.createObjectURL(file)
      if (detail.file_type === 'txt') previewText.value = await file.text()
    }
  } catch { /* API interceptor displays the server error */ }
  finally { loadingPreview.value = false }
}
watch(previewOpen, open => document.body.classList.toggle('knowledge-preview-open', open))
onMounted(loadCollections)
onUnmounted(() => {
  document.body.classList.remove('knowledge-preview-open')
  clearPreview()
})
</script>

<style scoped>
.knowledge-view { padding: 26px 30px 40px; color: var(--color-text-primary); }
.page-heading, .toolbar, .section-heading, .preview-meta { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.page-heading h1 { margin: 0; font-size: 26px; }
.page-heading p, .toolbar span { margin: 5px 0 0; color: var(--color-text-secondary); font-size: 13px; }
.demo-notice { margin: 20px 0; }
.workspace { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 18px; align-items: start; }
.collection-panel, .document-panel { background: var(--color-bg-card); border: 1px solid var(--color-border-light); border-radius: 14px; padding: 18px; }
.panel-title { font-size: 15px; font-weight: 700; margin-bottom: 12px; }
.collection-item { width: 100%; display: flex; flex-direction: column; align-items: flex-start; gap: 5px; border: 0; border-radius: 10px; padding: 12px; margin: 2px 0; background: transparent; color: inherit; cursor: pointer; text-align: left; }
.collection-item:hover, .collection-item.selected { background: #f0efff; }
.collection-item.selected .collection-name { color: #5146c9; }
.collection-name { font-weight: 650; }
.collection-count, .muted { color: var(--color-text-tertiary); font-size: 12px; }
.toolbar { flex-wrap: wrap; }
.toolbar h2 { font-size: 20px; margin: 0; }
.toolbar-filters, .query-bar { display: flex; gap: 9px; }
.toolbar-filters { align-items: center; }
.toolbar-filters .el-input { width: 180px; }
.query-bar { margin: 22px 0; }
.query-bar .el-input { flex: 1; }
.section-heading { margin-bottom: 12px; }
.section-heading h3 { margin: 0; font-size: 16px; }
.section-heading span { color: var(--color-text-tertiary); font-size: 12px; }
.results { border: 1px solid var(--color-border-light); border-radius: 10px; padding: 15px; margin-bottom: 22px; }
.citation { width: 100%; display: block; background: #f8f8fd; border: 1px solid transparent; border-radius: 9px; padding: 12px; text-align: left; margin: 8px 0; cursor: pointer; color: inherit; }
.citation:hover, .document-row:hover { border-color: #bbb5f4; }
.citation p { color: var(--color-text-secondary); font-size: 13px; margin: 7px 0 0; }
.document-row { width: 100%; display: flex; align-items: center; gap: 14px; text-align: left; border: 1px solid var(--color-border-light); border-radius: 10px; background: white; padding: 14px; margin-bottom: 9px; cursor: pointer; color: inherit; }
.file-icon { flex: none; min-width: 52px; text-align: center; background: #eeedff; color: #5547ca; border-radius: 7px; padding: 10px 4px; font-size: 11px; font-weight: 750; }
.file-main { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.file-main strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-main small { color: var(--color-text-tertiary); }
.open-label { margin-left: auto; color: #594ec5; font-size: 12px; flex: none; }
.more-btn { width: 100%; margin-top: 10px; }
.preview-body { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.preview-meta { color: var(--color-text-secondary); font-size: 12px; padding-bottom: 12px; }
.preview-meta a, .docx-fallback a { color: #5547ca; }
.file-frame { flex: 1; width: 100%; min-height: 0; border: 1px solid var(--color-border-light); border-radius: 8px; }
.preview-image { display: block; max-width: 100%; max-height: 100%; object-fit: contain; margin: auto; }
.preview-text { flex: 1; min-height: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; background: #f7f8fb; border-radius: 10px; padding: 20px; line-height: 1.75; }
.docx-fallback { padding: 40px 18px; text-align: center; background: #f7f8fb; border-radius: 10px; }
@media (max-width: 850px) { .knowledge-view { padding: 16px; } .workspace { grid-template-columns: 1fr; } .toolbar-filters { width: 100%; flex-wrap: wrap; } }
</style>

<style>
body.knowledge-preview-open .main-content { overflow-y: hidden; }
.knowledge-preview-modal .el-drawer__body { min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
</style>
