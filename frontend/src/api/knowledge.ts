import type { AxiosError } from 'axios'
import api from './index'

export interface KnowledgeCollection { id: string; name: string; description?: string; document_count: number }
export interface KnowledgeDocument {
  id: string; collection_id: string; filename: string; file_type: string
  size_bytes: number; status: string; page_count: number | null
  title?: string | null; updated_at?: string | null; created_at?: string | null; tags?: string[] | null
}
export interface KnowledgeChunk {
  chunk_id: string; index: number; heading?: string | null; page?: number | null; text: string
  previous_chunk_id?: string | null; next_chunk_id?: string | null
  source_locator?: { kind: string; page?: number; heading?: string }
}
export interface Page<T> { items: T[]; page_info: { next_cursor: string | null; has_more: boolean } }
export interface KnowledgeChunkRow { chunk_id: string; index: number; heading?: string | null; text_preview: string }
export interface KnowledgeChunkPage { items: KnowledgeChunkRow[]; page: number; page_size: number; total: number; has_next: boolean }

/** RAG 检索返回的原始 citation。scores 只用于检索排序，不进入页面。 */
export interface RagCitation extends KnowledgeChunk {
  document_id: string
  document_name: string
  scores?: Record<string, number>
  images?: (string | RagAssetRef)[]
  asset_ids?: string[]
  has_presentation?: boolean
  document_summary_preview?: string | null
}
export interface RagAssetRef {
  asset_id: string
  caption?: string | null
  description?: string | null
  source_chunk_id?: string | null
  content_type?: string | null
  thumbnail_asset_id?: string | null
}
/** RAG Document Presentation 原始结构。 */
export interface RagPresentation {
  presentation_status?: 'pending' | 'ready' | 'failed' | string | null
  summary?: string | null
  key_points?: string[] | null
  related_assets?: RagAssetRef[] | null
}

export interface KnowledgeSearchPayload { citations: RagCitation[] }

export const knowledgeApi = {
  status: () => api.get('/knowledge/status') as unknown as Promise<{ mode: 'rag' }>,
  collections: (cursor?: string) => api.get('/knowledge/collections', { params: { limit: 20, cursor } }) as unknown as Promise<Page<KnowledgeCollection>>,
  documents: (collectionId: string, params: { q?: string; file_type?: string; cursor?: string }) =>
    api.get(`/knowledge/collections/${encodeURIComponent(collectionId)}/documents`, { params: { limit: 20, ...params } }) as unknown as Promise<Page<KnowledgeDocument>>,
  query: (collectionId: string, query: string) =>
    api.post(`/knowledge/collections/${encodeURIComponent(collectionId)}/queries`, { query, top_k: 20, mode: 'hybrid' }) as unknown as Promise<KnowledgeSearchPayload>,
  detail: (documentId: string) =>
    api.get(`/knowledge/documents/${encodeURIComponent(documentId)}`) as unknown as Promise<KnowledgeDocument>,
  chunks: (documentId: string, page: number, pageSize: number) =>
    api.get(`/knowledge/documents/${encodeURIComponent(documentId)}/chunks`, { params: { page, page_size: pageSize } }) as unknown as Promise<KnowledgeChunkPage>,
  chunk: (documentId: string, chunkId: string) =>
    api.get(`/knowledge/documents/${encodeURIComponent(documentId)}/chunks/${encodeURIComponent(chunkId)}`) as unknown as Promise<KnowledgeChunk>,
  /** 404 表示该文档暂无 presentation，按 null 返回，不弹错误提示。 */
  presentation: async (documentId: string): Promise<RagPresentation | null> => {
    try {
      const data = await api.get(`/knowledge/documents/${encodeURIComponent(documentId)}/presentation`, { silent: true })
      return data as RagPresentation
    } catch (error) {
      if ((error as AxiosError)?.response?.status === 404) return null
      throw error
    }
  },
  /** 图片资产只经后端代理读取，浏览器不接触原始文件地址。 */
  assetUrl: (assetId: string) => `/api/v1/knowledge/assets/${encodeURIComponent(assetId)}`,
}
