import api from './index'

export interface KnowledgeCollection { id: string; name: string; description?: string; document_count: number }
export interface KnowledgeDocument {
  id: string; collection_id: string; filename: string; file_type: string
  size_bytes: number; status: string; page_count: number | null; preview_available?: boolean | null
}
export interface KnowledgeChunk {
  chunk_id: string; heading?: string | null; page?: number | null; text: string
  source_locator?: { kind: string; page?: number; heading?: string }
}
export interface KnowledgeCitation extends KnowledgeChunk { document_id: string; document_name: string }
export interface Page<T> { items: T[]; page_info: { next_cursor: string | null; has_more: boolean } }

export const knowledgeApi = {
  status: () => api.get('/knowledge/status') as unknown as Promise<{ mode: 'mock' | 'rag' }>,
  collections: (cursor?: string) => api.get('/knowledge/collections', { params: { limit: 20, cursor } }) as unknown as Promise<Page<KnowledgeCollection>>,
  documents: (collectionId: string, params: { q?: string; file_type?: string; cursor?: string }) =>
    api.get(`/knowledge/collections/${encodeURIComponent(collectionId)}/documents`, { params: { limit: 20, ...params } }) as unknown as Promise<Page<KnowledgeDocument>>,
  query: (collectionId: string, query: string) =>
    api.post(`/knowledge/collections/${encodeURIComponent(collectionId)}/queries`, { query, top_k: 5, mode: 'hybrid' }) as unknown as Promise<{ citations: KnowledgeCitation[] }>,
  detail: (documentId: string) =>
    api.get(`/knowledge/documents/${encodeURIComponent(documentId)}`) as unknown as Promise<KnowledgeDocument & { chunks: KnowledgeChunk[] }>,
  previewSession: (documentId: string) =>
    api.post(`/knowledge/documents/${encodeURIComponent(documentId)}/preview-session`) as unknown as Promise<{ expires_in: number }>,
  previewUrl: (documentId: string) => `/api/v1/knowledge/documents/${encodeURIComponent(documentId)}/file`,
  file: (documentId: string) =>
    api.get(`/knowledge/documents/${encodeURIComponent(documentId)}/file`, { responseType: 'blob' }) as unknown as Promise<Blob>,
}
