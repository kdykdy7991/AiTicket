# 工单知识库与 RAG Server 对接

知识库页面是**只读的知识消费入口**。RAG Server 管理知识库与文档、执行检索、生成 Document Presentation；工单侧只负责展示：检索结果、文档摘要、文档重点、命中片段和图片资产。不提供文档管理、知识条目编写、AI 汇总回答、原文件预览或下载。

## 接口

工单后端用 `RAG_API_URL`、`RAG_SERVICE_TOKEN` 和 `X-Audit-User-ID: ticket:<用户ID>` 调用项目只读 API；浏览器只调用同源的 `/api/v1/knowledge/*`。知识库目前仅管理员可见。

| 页面动作 | 工单接口 | RAG 项目接口 |
| --- | --- | --- |
| 选择授权知识库 | `GET /api/v1/knowledge/collections` | `GET /api/v1/collections` |
| 检索选定知识库 | `POST /api/v1/knowledge/collections/{collection_id}/queries` | `POST /api/v1/collections/{collection_id}/queries` |
| 读取文档摘要 / 重点 / 图片 | `GET /api/v1/knowledge/documents/{document_id}/presentation` | `GET /api/v1/documents/{document_id}/presentation` |
| 读取图片资产 | `GET /api/v1/knowledge/assets/{asset_id}` | `GET /api/v1/assets/{asset_id}` |
| 展开命中上下文 | `GET /api/v1/knowledge/documents/{document_id}/chunks/{chunk_id}` | `GET /api/v1/documents/{document_id}/chunks/{chunk_id}` |

检索结果直接使用 `document_id`、`chunk_id`、`document_name`、可选 `page`、`text`，以及可选的 `document_summary_preview`、`has_presentation`、`images` / `asset_ids`。页面不显示相关度、检索分数、总结果数或 AI 回答。知识库选择器只列项目凭证获准的知识库，每次只检索当前选中的知识库，不支持“全部知识库”。

`presentation` 接口：

- `presentation_status = ready`：展示 `summary`（文档摘要）、`key_points`（文档重点）、`related_assets`（图片资产）
- `pending`：摘要区显示“摘要生成中”，不锁死页面
- `failed`：不暴露技术错误，显示“暂未生成文档摘要”
- `404`（该文档没有 presentation）：摘要区整体不渲染，不留空卡片
- `key_points` 为空：重点内容区不渲染

`assets` 接口只转发 `image/*`，非图片返回 415；不代理原文件，不返回文件路径或下载地址。

片段可能包含 Markdown。列表页把表格折叠成提示文字；详情与相邻片段按 Markdown 渲染，包括表格、标题、列表、引用和代码。渲染器禁用原始 HTML、链接和图片，表格超宽时在卡片内横向滚动；关键词在解析后的文字节点上高亮。RAG 原文保持不变。

工单侧不代理原文件接口，也不提供下载；不展示 `source_path`。片段文本发送到浏览器后仍可被复制；当前设计只保护原始文件及其版式。

## 前端结构

页面组件只依赖内部视图模型，RAG 字段调整只改 adapter：

- `src/api/knowledge.ts`：RAG 原始类型与接口调用（`RagCitation` / `RagPresentation`）
- `src/utils/knowledgeAdapter.ts`：原始结构 → `KnowledgeSearchResult` / `KnowledgePresentation` / `KnowledgeAsset` / `KnowledgeSnippet`
- `src/types/knowledge.ts`：页面视图模型
- `src/views/KnowledgeBaseView.vue`：页面状态机（未查询 / 查询中 / 有结果 / 无结果 / 检索失败 / 无权限）
- `src/components/knowledge/`：结果列表、详情区、右侧辅助栏、Markdown 渲染、图片查看器

页面状态：

1. 初始未查询：轻量示例词，不做插画
2. 查询中：列表 skeleton，详情保持上一个内容
3. 有结果：三栏（结果 / 详情 / 辅助）
4. 无结果：不展示低相关度结果，提供改词与换库
5. 检索失败 / 无权限：单独提示
6. 切换知识库：清空结果与选中态

知识库筛选 chips 中的“全部”不是让 RAG 跨库检索：前端按顺序对每个授权知识库分别调用检索接口，按文档去重后合并展示；任一库失败只回退到失败提示（全部失败时）。

详情头部提供两个前端操作：`在新窗口打开` 以 `?collection=&doc=&chunk=` 深链打开当前命中片段（只读取片段详情与 presentation，不重新检索）；`加入常用` 把 document_id 存入浏览器 localStorage，仅本地记住常用文档。结果列表支持“相关度优先 / 文档名称”排序，不涉及检索分数展示。

右侧辅助栏只在有图片资产或相关文档时出现；两者都为空时隐藏整栏，主区域自动扩宽。
