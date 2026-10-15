/**
 * RAG 原始结构 → 客服项目内部视图模型。
 * 页面组件只消费这里产出的结构，RAG 字段调整时改本文件即可。
 */
import { knowledgeApi, type RagAssetRef, type RagCitation, type RagPresentation } from '@/api/knowledge'
import {
  EMPTY_PRESENTATION,
  type KnowledgeAsset,
  type KnowledgeContextChunk,
  type KnowledgePresentation,
  type KnowledgeRelatedDocument,
  type KnowledgeSearchResult,
  type KnowledgeSnippet,
} from '@/types/knowledge'
import { knowledgeListSnippet } from '@/utils/knowledgeMarkdown'

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function assetId(value: RagAssetRef | string): string {
  return typeof value === 'string' ? value : text(value?.asset_id)
}

export function toAsset(value: RagAssetRef | string): KnowledgeAsset {
  const id = assetId(value)
  const caption = typeof value === 'string' ? '' : text(value?.description) || text(value?.caption)
  return {
    id,
    caption,
    sourceChunkId: typeof value === 'string' ? null : text(value?.source_chunk_id) || null,
    contentType: typeof value === 'string' ? 'image' : text(value?.content_type) || 'image',
    url: knowledgeApi.assetUrl(id),
  }
}

export function toPresentation(raw: RagPresentation | null | undefined): KnowledgePresentation {
  if (!raw) return { ...EMPTY_PRESENTATION }
  const status = text(raw.presentation_status)
  const assets = (raw.related_assets || []).map(toAsset).filter(asset => asset.id)
  const summary = text(raw.summary)
  const keyPoints = (raw.key_points || []).map(point => text(point)).filter(Boolean)
  if (status === 'pending') {
    return { status: 'pending', summary: '', keyPoints: [], assets }
  }
  if (status === 'failed') {
    return { status: 'failed', summary: '', keyPoints: [], assets }
  }
  if (status !== 'ready' && !summary && !keyPoints.length && !assets.length) {
    return { status: 'none', summary, keyPoints, assets }
  }
  return { status: 'ready', summary, keyPoints, assets }
}

export function toSearchResult(raw: RagCitation): KnowledgeSearchResult {
  const documentId = text(raw.document_id)
  const chunkId = text(raw.chunk_id)
  const body = raw.text || ''
  return {
    key: `${documentId}:${chunkId}`,
    documentId,
    documentName: text(raw.document_name) || '未命名文档',
    chunkId,
    snippet: knowledgeListSnippet(body),
    text: body,
    page: typeof raw.page === 'number' ? raw.page : null,
    heading: text(raw.heading) || null,
    // 检索分数不进入视图模型：页面不展示相关度百分比或原始 score
    summaryPreview: text(raw.document_summary_preview),
    hasPresentation: typeof raw.has_presentation === 'boolean' ? raw.has_presentation : null,
  }
}

export function toSearchResults(raw: RagCitation[] | null | undefined): KnowledgeSearchResult[] {
  return (raw || []).map(toSearchResult).filter(result => result.documentId)
}

/** 同一文档在当前查询下的全部命中片段。 */
export function toSnippets(results: KnowledgeSearchResult[], documentId: string, currentChunkId: string): KnowledgeSnippet[] {
  return results
    .filter(result => result.documentId === documentId)
    .map(result => ({
      chunkId: result.chunkId,
      page: result.page,
      heading: result.heading,
      text: result.text,
      current: result.chunkId === currentChunkId,
    }))
}

/** 右侧“相关文档”：同一查询结果里的其他文档，按首次命中顺序去重。 */
export function toRelatedDocuments(results: KnowledgeSearchResult[], currentDocumentId: string): KnowledgeRelatedDocument[] {
  const seen = new Set<string>()
  const items: KnowledgeRelatedDocument[] = []
  for (const result of results) {
    if (result.documentId === currentDocumentId || seen.has(result.documentId)) continue
    seen.add(result.documentId)
    items.push({
      documentId: result.documentId,
      documentName: result.documentName,
      summaryPreview: result.summaryPreview,
      tag: result.heading,
    })
  }
  return items
}

export function toContextChunks(
  previous: { text: string; page?: number | null } | null,
  current: { text: string; page?: number | null } | null,
  next: { text: string; page?: number | null } | null,
): KnowledgeContextChunk[] {
  const chunks: KnowledgeContextChunk[] = []
  if (previous) chunks.push({ position: 'previous', label: '上一片段', text: previous.text, page: previous.page ?? null })
  if (current) chunks.push({ position: 'current', label: '当前命中', text: current.text, page: current.page ?? null })
  if (next) chunks.push({ position: 'next', label: '下一片段', text: next.text, page: next.page ?? null })
  return chunks
}
