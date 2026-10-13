# 工单知识库与 RAG Server 对接设计（待双方确认）

## 边界与现状

- RAG Server 保存原文件、文档信息、知识库关系、检索片段和最终文档授权；工单系统不复制文件或片段，不解析文档入库。
- 工单系统实现知识库页面及同源后端代理。当前工单库没有 RAG `collection_id` / `document_id` 字段，也没有知识库或文档级 ACL。
- 下表中的 RAG 路径是对方已有的 Web 接口草案，**尚未具备面向接入项目的服务认证和授权，不可直接接入或暴露给浏览器**。
- 工单前端使用 Vue 3、Element Plus；API 请求当前带本地 JWT Bearer。原生 PDF 阅读器发起的文件请求不能自动携带该请求头。

## 页面与接口映射

| 页面动作 | 工单后端拟提供的同源接口 | RAG Server 草案接口 |
| --- | --- | --- |
| 知识库首页 | `GET /api/v1/knowledge/collections` | `GET /api/v1/collections` |
| 文档列表、文件名/格式筛选 | `GET /api/v1/knowledge/collections/{collection_id}/documents` | `GET /api/v1/collections/{collection_id}/documents` |
| 知识库内检索 | `POST /api/v1/knowledge/collections/{collection_id}/queries` | `POST /api/v1/collections/{collection_id}/queries` |
| 文档详情 | `GET /api/v1/knowledge/documents/{document_id}` | `GET /api/v1/documents/{document_id}` |
| 片段来源位置 | `GET /api/v1/knowledge/documents/{document_id}/chunks/{chunk_id}` | `GET /api/v1/documents/{document_id}/chunks/{chunk_id}` |
| 原文件 | `GET /api/v1/knowledge/documents/{document_id}/file` | `GET /api/v1/documents/{document_id}/preview` |

工单后端只接受固定配置的 RAG Server 基址和以上路径；`collection_id`、`document_id`、`chunk_id` 作为路径参数校验，不能接受任意目标 URL。列表保留 `limit`、`cursor`、`q`、`file_type` 等约定参数，检索保留 `query`、`top_k`、`mode`。分页、排序和允许的取值范围待正式契约确认。

知识库首页、列表、搜索、详情、片段和文件各自都要由 RAG Server 按接入项目做授权过滤。项目无权访问的知识库、文档、片段统一向工单侧返回 404；工单登录失效返回工单自身的 401。RAG 服务凭证失效不能透传成工单侧 401，否则当前前端会误以为用户登录失效并清除本地会话；应转为集成故障响应并记录服务端日志与 `request_id`。

## 身份与权限

1. 浏览器只向工单后端发送现有登录凭证。工单后端调用 `get_current_user` 验证用户处于启用状态且会话版本有效。
2. 工单后端用本项目专用的 RAG 服务凭证调用 RAG Server。服务凭证不得进入前端或 URL。后续接入系统各使用独立凭证。
3. RAG Server 根据已认证的服务凭证识别接入项目，由其管理员维护“项目 → 可访问知识库”的授权关系。文档首版继承所属知识库权限，所有读取接口使用同一规则。
4. 工单后端决定本系统哪些登录用户可以进入知识库，并可向 RAG Server 传递经过验证的用户 ID 用于审计；该 ID 首版不参与 RAG 授权。RAG Server 不接受未认证客户端自行声明的项目或用户身份。

同一项目内获准进入知识库的用户共享该项目的知识库范围。服务凭证格式、轮换、审计用户 ID 的传递方式、项目授权维护界面与 401/403/404 错误映射仍待 RAG Server 固化。正式授权可用前，不开放真实知识库数据页面。若先做工单侧页面测试，只使用本地模拟数据。

## 工单侧模拟实现

工单项目现有 `/knowledge` 页面及同源 `/api/v1/knowledge/*` 模拟接口，用于验证知识库浏览、文件名与格式筛选、检索来源、详情和原文件展示。模拟数据仅包含代码中固定的示例知识库和文件，不调用 RAG Server。前后端均限制管理员访问；后端需设置 `KNOWLEDGE_MOCK_ENABLED=true`，开发 Compose 默认启用，应用配置默认关闭。页面明确标注“模拟数据”。DOCX 暂提供下载回退。

工单后端另已实现真实 RAG 读取代理：配置 `RAG_API_URL` 和 `RAG_SERVICE_TOKEN` 并重启 API 后，使用真实代理替换模拟接口。开发 Compose 的 RAG 地址默认指向 `http://10.113.114.88:8770`，凭证需在工单项目根目录 `.env` 中设置，不能提交到 Git。代理按当前登录用户生成 `X-Audit-User-ID: ticket:<用户ID>`，RAG 按项目凭证授权。PDF 预览会话和 Range 请求转发已在真实接口上验证；浏览器阅读器的视觉效果仍需人工验收。

从项目根目录启动开发 API 时使用 `docker compose --env-file .env -f backend/docker-compose.yml up -d --no-deps --force-recreate api`，明确让 Compose 读取根目录凭证。2026-10-13 已用 ticket 项目凭证验证 `skdy-common` 列表（13 篇）和文件代理：2 篇 PDF 的原文件可读，Range 返回 206，越界返回 416；其余 11 篇原文件接口返回 `DOCUMENT_NOT_FOUND`，原因是 RAG 侧未保存原上传文件。页面因此将 `ready` 表述为“已索引”，无法预览时明确提示重新上传。检索结果点击后只打开文档，不展示页码或额外的“来源位置”区域。

## 原文件预览

- **PDF**：使用浏览器原生阅读器，从文档首页打开。工单页面不提供页码输入、自动跳页或片段高亮。
- **图片**：浏览器内展示原文件。**TXT/CSV**：按文本读取、保留换行并限制过大文件的浏览器渲染量。
- **DOCX**：在 Vue 页面评估框架无关的 `docx-preview` 对原文件的渲染效果；渲染失败时提供原文件下载。RAG Server 转 PDF/HTML 是后续可选能力，不作为首版前置条件。
- **章节定位**：首版不展示片段的章节定位；检索结果只显示片段文字及所属文档。
- 文档详情需稳定提供或可推断 `filename`、媒体类型/文件类型、`size_bytes`、`status`、`page_count` 与原文件是否可用；其中 `preview_available` 尚不存在，需在正式契约中确定是否新增。无原文件的 404 应有明确错误码。

### 原生 PDF 的同源预览会话

工单后端提供经 JWT 认证的 `POST /api/v1/knowledge/documents/{document_id}/preview-session`，为当前用户和指定文档建立五分钟的只读预览会话。浏览器随后通过同源 `GET .../documents/{document_id}/file` 请求文件；会话凭证放在限定该文档文件路径的 `HttpOnly`、`SameSite=Lax` Cookie 中，不把 JWT、RAG 服务凭证或会话凭证放到文件 URL。服务端会话绑定用户、文档、会话版本与过期时间；每次文件请求仍由工单后端用本项目凭证向 RAG Server 读取，工单后端负责校验本地用户的预览会话。Cookie 的 `Secure` 属性在 HTTPS 环境启用。

文件代理流式转发，不一次性读入内存。已在真实 PDF 上验证 `Range` 请求、`206 Partial Content`、`416 Range Not Satisfiable`、`Content-Range` 和 `Accept-Ranges`；浏览器中的手动翻页与大文件加载仍需界面验收。

## 双方进入联调的条件

1. RAG Server 完成项目服务认证、“项目 → 知识库”授权和六类接口的一致授权过滤，提供凭证轮换方式与 OpenAPI 契约。
2. 双方确认列表、检索、详情、片段及文件的必要字段、分页、错误码；尤其确认媒体类型、原文件缺失和无权访问的行为。
3. 工单侧完成后端代理、预览会话、页面和 DOCX 渲染评估；凭证只配置在后端。
4. 用有权/无权项目验证 RAG 授权隔离，用获准/未获准的工单用户验证本地入口与预览会话；再用 PDF 大文件实测页码跳转、Range 全链路与会话过期行为。
