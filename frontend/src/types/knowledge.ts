/** 知识库页面的内部视图模型：页面组件只依赖这里，不直接依赖 RAG 原始字段。 */

export type KnowledgePresentationStatus = 'none' | 'loading' | 'pending' | 'ready' | 'failed'

/** 知识派生资产（图片）。不承载原文件地址与路径。 */
export interface KnowledgeAsset {
  id: string
  caption: string
  sourceChunkId: string | null
  contentType: string
  url: string
}

/** Document Presentation 视图模型：文档摘要、文档重点、可选图片。 */
export interface KnowledgePresentation {
  status: KnowledgePresentationStatus
  summary: string
  keyPoints: string[]
  assets: KnowledgeAsset[]
}

/** 左侧列表项。不含任何检索分数。 */
export interface KnowledgeSearchResult {
  key: string
  documentId: string
  documentName: string
  chunkId: string
  snippet: string
  text: string
  page: number | null
  heading: string | null
  summaryPreview: string
  /** RAG 明确告知没有 presentation 时不再请求详情；未提供则为 null，仍按需拉取。 */
  hasPresentation: boolean | null
}

/** 同一文档下当前查询命中的片段。 */
export interface KnowledgeSnippet {
  chunkId: string
  page: number | null
  heading: string | null
  text: string
  current: boolean
}

/** 右侧“相关文档”：同一查询结果中的其他文档。 */
export interface KnowledgeRelatedDocument {
  documentId: string
  documentName: string
  summaryPreview: string
  tag: string | null
}

/** 上下文展开后的相邻片段。 */
export interface KnowledgeContextChunk {
  position: 'previous' | 'current' | 'next'
  label: string
  text: string
  page: number | null
}

export const EMPTY_PRESENTATION: KnowledgePresentation = {
  status: 'none',
  summary: '',
  keyPoints: [],
  assets: [],
}
