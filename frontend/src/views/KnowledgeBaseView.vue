<template>
  <main class="knowledge-page"><div class="knowledge-content">
    <header class="page-header"><h1>知识库</h1></header>
    <form class="search-bar" @submit.prevent="search"><el-input v-model="queryInput" clearable size="large" placeholder="搜索知识库（文档标题、内容、关键词）" @clear="search"><template #prefix><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg></template></el-input><button type="submit" :disabled="searching">{{ searching ? '搜索中…' : '搜索' }}</button></form>
    <div class="toolbar"><div class="collection-chips"><button type="button" :class="{ active: collectionId === ALL }" @click="selectCollection(ALL)">全部</button><button v-for="collection in collections" :key="collection.id" type="button" :class="{ active: collectionId === collection.id }" @click="selectCollection(collection.id)">{{ collection.name }}</button></div><label class="sort-control"><span class="sr-only">排序方式</span><select v-model="sortMode"><option value="recent">最近更新</option><option value="name">文档名称</option></select></label></div>
    <div class="result-count" aria-live="polite">{{ searching ? '正在搜索…' : loading ? '正在加载文档…' : `共 ${visibleDocuments.length} 个文档` }}</div>
    <div v-if="accessDenied" class="page-state"><h2>暂无知识库访问权限</h2><p>请联系管理员开通知识库权限。</p></div>
    <div v-else-if="error" class="page-state"><h2>知识库加载失败</h2><p>暂时无法获取文档，请稍后重试。</p><button type="button" @click="reload">重试</button></div>
    <div v-else-if="loading" class="document-grid" aria-label="文档加载中"><div v-for="index in 6" :key="index" class="card-skeleton"><div class="cover-skeleton"/><div class="line-skeleton"/><div class="line-skeleton short"/></div></div>
    <div v-else-if="searching" class="page-state"><h2>正在搜索知识库…</h2><p>正在查找与关键词相关的文档。</p></div>
    <div v-else-if="!visibleDocuments.length" class="page-state"><h2>{{ activeQuery ? '没有找到相关文档' : '暂无文档' }}</h2><p>{{ activeQuery ? '试试更换关键词，或切换知识库范围。' : '当前知识库中还没有可浏览的文档。' }}</p></div>
    <div v-else class="document-grid"><DocumentCard v-for="document in visibleDocuments" :key="document.id" :title="documentTitle(document)" :file-type="fileType(document)" :summary="presentationCache[document.id]?.summary || ''" :presentation-state="presentationCache[document.id]?.status || 'loading'" :tags="documentTags(document)" :updated-at="dateLabel(document)" @visible="ensurePresentation(document.id)" @open="openDocument(document)" /></div>
  </div>
    <DocumentDetailDrawer :visible="drawerVisible" :document="selectedDocument" :presentation="selectedDocument ? presentationCache[selectedDocument.id] || null : null" :loading="selectedDocument ? !!presentationLoading[selectedDocument.id] : false" :title="selectedDocument ? documentTitle(selectedDocument) : ''" :file-type="selectedDocument ? fileType(selectedDocument) : ''" :updated-at="selectedDocument ? dateLabel(selectedDocument) : ''" :tags="selectedDocument ? documentTags(selectedDocument) : []" @close="drawerVisible = false" @copy="copyContent" @quote="quoteToTicket" @preview-asset="openAsset" />
    <KnowledgeAssetViewer :asset="previewAsset" :visible="previewVisible" @close="previewVisible = false" />
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { AxiosError } from 'axios'
import { knowledgeApi, type KnowledgeCollection, type KnowledgeDocument } from '@/api/knowledge'
import DocumentCard from '@/components/knowledge/DocumentCard.vue'
import DocumentDetailDrawer from '@/components/knowledge/DocumentDetailDrawer.vue'
import KnowledgeAssetViewer from '@/components/knowledge/KnowledgeAssetViewer.vue'
import type { KnowledgeAsset, KnowledgePresentation } from '@/types/knowledge'
import { toPresentation } from '@/utils/knowledgeAdapter'

const ALL = 'all'
const collections = ref<KnowledgeCollection[]>([])
const documents = ref<KnowledgeDocument[]>([])
const collectionId = ref(ALL)
const queryInput = ref('')
const activeQuery = ref('')
const sortMode = ref<'recent' | 'name'>('recent')
const loading = ref(true)
const searching = ref(false)
const error = ref(false)
const accessDenied = ref(false)
const searchIds = ref<string[] | null>(null)
const selectedDocument = ref<KnowledgeDocument | null>(null)
const drawerVisible = ref(false)
const previewAsset = ref<KnowledgeAsset | null>(null)
const previewVisible = ref(false)
const presentationCache = reactive<Record<string, KnowledgePresentation>>({})
const presentationLoading = reactive<Record<string, boolean>>({})
const presentationRequests = new Map<string, Promise<void>>()
let requestVersion = 0

const scopedDocuments = computed(() => collectionId.value === ALL ? documents.value : documents.value.filter(item => item.collection_id === collectionId.value))
const visibleDocuments = computed(() => {
  const rows = searchIds.value ? scopedDocuments.value.filter(item => searchIds.value?.includes(item.id)) : scopedDocuments.value
  return [...rows].sort((a, b) => sortMode.value === 'name'
    ? documentTitle(a).localeCompare(documentTitle(b), 'zh-Hans-CN')
    : (Date.parse(b.updated_at || b.created_at || '') || 0) - (Date.parse(a.updated_at || a.created_at || '') || 0) || documentTitle(a).localeCompare(documentTitle(b), 'zh-Hans-CN'))
})
function documentTitle(document: KnowledgeDocument): string { return (document.title || document.filename || '未命名文档').replace(/\.[^.]+$/, '') }
function fileType(document: KnowledgeDocument): string { return (document.file_type || document.filename?.split('.').pop() || '').toUpperCase() }
function dateLabel(document: KnowledgeDocument): string { const date = document.updated_at || document.created_at; if (!date) return ''; const parsed = new Date(date); return Number.isNaN(parsed.getTime()) ? '' : `${parsed.getFullYear()}-${String(parsed.getMonth() + 1).padStart(2, '0')}-${String(parsed.getDate()).padStart(2, '0')}` }
function documentTags(document: KnowledgeDocument): string[] { return Array.isArray(document.tags) ? document.tags.filter(Boolean).slice(0, 3) : [] }
async function allPages<T>(load: (cursor?: string) => Promise<{ items: T[]; page_info: { has_more: boolean; next_cursor: string | null } }>): Promise<T[]> {
  const rows: T[] = []; const seen = new Set<string>(); let cursor: string | undefined
  do { const page = await load(cursor); rows.push(...page.items); if (!page.page_info?.has_more || !page.page_info.next_cursor || seen.has(page.page_info.next_cursor)) break; cursor = page.page_info.next_cursor; seen.add(cursor) } while (true)
  return rows
}
async function reload() {
  const version = ++requestVersion; loading.value = true; error.value = false; accessDenied.value = false
  try {
    const foundCollections = await allPages(cursor => knowledgeApi.collections(cursor)); if (version !== requestVersion) return
    collections.value = foundCollections
    const pages = await Promise.all(foundCollections.map(collection => allPages(cursor => knowledgeApi.documents(collection.id, { cursor })))); if (version !== requestVersion) return
    documents.value = Array.from(new Map(pages.flat().map(document => [document.id, document])).values())
    if (activeQuery.value) await runSearch(version)
  } catch (cause) { if (version !== requestVersion) return; accessDenied.value = (cause as AxiosError)?.response?.status === 403; error.value = !accessDenied.value }
  finally { if (version === requestVersion) loading.value = false }
}
async function ensurePresentation(id: string): Promise<void> {
  if (presentationCache[id] || presentationRequests.has(id)) return presentationRequests.get(id)
  presentationLoading[id] = true
  const pending = knowledgeApi.presentation(id).then(raw => { presentationCache[id] = toPresentation(raw) }).catch(() => { presentationCache[id] = { status: 'failed', summary: '', keyPoints: [], assets: [] } }).finally(() => { presentationLoading[id] = false; presentationRequests.delete(id) })
  presentationRequests.set(id, pending); return pending
}
async function runSearch(version: number) {
  const query = activeQuery.value; if (!query) { searchIds.value = null; searching.value = false; return }
  searching.value = true
  try {
    const scope = collectionId.value === ALL ? collections.value : collections.value.filter(item => item.id === collectionId.value)
    const titleIds = scopedDocuments.value.filter(item => documentTitle(item).toLocaleLowerCase().includes(query.toLocaleLowerCase())).map(item => item.id)
    const responses = await Promise.allSettled(scope.map(collection => knowledgeApi.query(collection.id, query)))
    if (version !== requestVersion) return
    const hits = responses.filter((result): result is PromiseFulfilledResult<Awaited<ReturnType<typeof knowledgeApi.query>>> => result.status === 'fulfilled').flatMap(result => result.value.citations || []).map(hit => hit.document_id)
    if (responses.length && responses.every(result => result.status === 'rejected') && !titleIds.length) throw new Error('search failed')
    searchIds.value = [...new Set([...titleIds, ...hits])]
  } catch { if (version === requestVersion) { error.value = true; searchIds.value = [] } }
  finally { if (version === requestVersion) searching.value = false }
}
function search() { activeQuery.value = queryInput.value.trim(); const version = ++requestVersion; if (!activeQuery.value) { searchIds.value = null; searching.value = false; error.value = false; return }; void runSearch(version) }
function selectCollection(id: string) { collectionId.value = id; if (activeQuery.value) search(); else searchIds.value = null }
function openDocument(document: KnowledgeDocument) { selectedDocument.value = document; drawerVisible.value = true; void ensurePresentation(document.id) }
function openAsset(asset: KnowledgeAsset) { if (!asset.contentType.startsWith('image')) return; previewAsset.value = asset; previewVisible.value = true }
function contentText(): string { const document = selectedDocument.value; const presentation = document && presentationCache[document.id]; if (!document || !presentation) return ''; return [documentTitle(document), presentation.summary, presentation.keyPoints.length ? `关键要点\n${presentation.keyPoints.map((point, index) => `${index + 1}. ${point}`).join('\n')}` : ''].filter(Boolean).join('\n\n') }
async function copyContent() { try { await navigator.clipboard.writeText(contentText()); ElMessage.success('文档内容已复制') } catch { ElMessage.error('复制失败，请检查剪贴板权限') } }
async function quoteToTicket() { const document = selectedDocument.value; if (!document) return; try { await navigator.clipboard.writeText(`【知识库引用：${documentTitle(document)}】\n${contentText()}`); ElMessage.success('引用内容已复制，可粘贴到工单') } catch { ElMessage.error('复制失败，请检查剪贴板权限') } }
onMounted(reload)
</script>

<style scoped>
.knowledge-page{min-height:100%;background:#f8f9f8;color:#1e2938}.knowledge-content{max-width:1640px;margin:0 auto;padding:30px clamp(22px,2.5vw,46px) 60px}.page-header{display:flex;align-items:baseline;gap:18px;margin-bottom:26px}.page-header h1{font-size:23px;line-height:1.3;margin:0;font-weight:750}.page-header span{color:#8c96a4;font-size:13px}.search-bar{display:flex;gap:12px}.search-bar :deep(.el-input){flex:1}.search-bar :deep(.el-input__wrapper){min-height:40px;border-radius:6px;box-shadow:0 0 0 1px #e2e6e9 inset!important}.search-bar button{width:88px;border:0;border-radius:6px;background:#777f4e;color:#fff;font-size:14px;cursor:pointer}.search-bar button:hover:not(:disabled){background:#666e3f}.search-bar button:disabled{opacity:.65;cursor:wait}.toolbar{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-top:16px}.collection-chips{display:flex;flex-wrap:wrap;gap:8px}.collection-chips button{border:1px solid transparent;border-radius:6px;background:#fff;padding:6px 12px;color:#394459;font-size:12px;cursor:pointer}.collection-chips button.active{border-color:#a9ad84;background:#f2f2e9;color:#555d3b}.sort-control select{border:0;background:transparent;color:#677182;font-size:12px;cursor:pointer}.result-count{margin:22px 0 15px;color:#7a8492;font-size:13px}.document-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}.page-state{min-height:260px;display:flex;align-items:center;justify-content:center;flex-direction:column;text-align:center;border:1px solid #e9ecea;border-radius:10px;background:#fff}.page-state h2{font-size:16px;margin:0 0 8px}.page-state p{font-size:13px;color:#85909f;margin:0}.page-state button{margin-top:17px;border:1px solid #a8ad83;border-radius:6px;background:#fff;padding:7px 18px;color:#666e41;cursor:pointer}.card-skeleton{border:1px solid #e9ecea;border-radius:11px;background:#fff;padding:20px}.cover-skeleton{aspect-ratio:1.78;border-radius:8px;background:#eef0ec}.line-skeleton{height:14px;margin-top:17px;border-radius:4px;background:#eef0ec}.line-skeleton.short{width:65%;margin-top:11px}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}@media(min-width:1700px){.document-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}@media(max-width:1199px){.document-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){.knowledge-content{padding:24px 16px 40px}.page-header{display:block}.page-header span{display:block;margin-top:5px}.document-grid{grid-template-columns:1fr}.search-bar button{width:72px}.toolbar{align-items:flex-start}.sort-control{white-space:nowrap}}
</style>
<style scoped>
.knowledge-page { min-height: 100%; background: #020d20; color: #eaf4ff; }
.knowledge-content { max-width: 1640px; padding: 20px clamp(16px, 1.7vw, 30px) 60px; }
.page-header { margin-bottom: 20px; }
.page-header h1 { color: #f1f8ff; font-size: 28px; text-shadow: 0 0 17px #40aaff38; }
.search-bar { gap: 12px; padding: 12px 14px; border: 1px solid #176496; border-radius: 6px; background: #06213e; box-shadow: 0 0 12px #0064ae2b; }
.search-bar :deep(.el-input__wrapper) { min-height: 40px; border: 1px solid #1b547f; border-radius: 4px; background: #061b34; box-shadow: none !important; }
.search-bar :deep(.el-input__wrapper:focus-within) { border-color: #37a7e7; box-shadow: 0 0 0 2px #2188d140 !important; }
.search-bar :deep(.el-input__inner) { color: #eaf4ff; }
.search-bar :deep(.el-input__prefix) { color: #87c8f1; }
.search-bar button { width: 92px; border: 1px solid #168cea; border-radius: 4px; background: linear-gradient(180deg, #0b74d5, #074eae); color: #fff; font-weight: 600; box-shadow: 0 0 12px #075dc662; }
.search-bar button:hover:not(:disabled) { border-color: #39a2eb; background: linear-gradient(180deg, #1083e6, #075fc6); }
.toolbar { gap: 18px; margin-top: 18px; }
.collection-chips { gap: 8px; }
.collection-chips button { min-height: 34px; padding: 6px 13px; border: 1px solid #15436c; border-radius: 4px; background: #061c39; color: #c5d8ee; }
.collection-chips button:hover { border-color: #2d90d0; color: #eff8ff; }
.collection-chips button.active { border-color: #278cdb; background: linear-gradient(180deg, #0a6ac6, #084ba7); color: #fff; box-shadow: 0 0 11px #075fc56b; }
.sort-control select { min-height: 34px; padding: 0 28px 0 11px; border: 1px solid #1b547f; border-radius: 4px; background: #061f3d; color: #c9e2f6; color-scheme: dark; }
.result-count { margin: 20px 0 14px; color: #91b5d2; }
.document-grid { gap: 16px; }
.page-state { border: 1px solid #176496; border-radius: 8px; background: linear-gradient(135deg, #082646, #061d39 78%); box-shadow: 0 0 12px #0064ae30; }
.page-state h2 { color: #eaf6ff; }
.page-state p { color: #91b5d2; }
.page-state button { border: 1px solid #278cdb; border-radius: 4px; background: #092c4e; color: #cce9ff; }
.page-state button:hover { background: #0d406b; }
.card-skeleton { border: 1px solid #176496; border-radius: 8px; background: #082646; }
.cover-skeleton, .line-skeleton { background: #123a5c; }
@media (max-width: 680px) { .knowledge-content { padding: 16px 14px 40px; } .page-header h1 { font-size: 24px; } .search-bar { padding: 10px; } .toolbar { flex-wrap: wrap; } }
</style>
