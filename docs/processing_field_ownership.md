# Processing 节点字段审计与归属（2026-10-16）

代码证据：`backend/app/models/ticket.py`、`backend/app/schemas/ticket.py`、`backend/app/api/v1/tickets.py`、`backend/app/api/v1/articles.py`、`backend/app/services/state_machine.py`、`frontend/src/components/ticket/TicketDetailInformation.vue`。历史数据数量未查询生产库，下表的风险表示存量字段/文章可能已有记录。

| 字段 | 当前真实语义与写入入口 | 读取、导出或统计 | 历史兼容风险 | Processing 归属 |
|---|---|---|---|---|
| `Ticket.root_cause` | “根本原因”；建单和 PATCH 可写 | 详情、Overview；不见 CSV/统计依赖 | 可有存量值，不能删 | `ticket_field`，根因分析唯一当前真值 |
| `Ticket.solution` | “解决办法”；建单和 PATCH 可写 | 详情及 Overview 优先于 resolution；不见 CSV/统计依赖 | 可有存量值，不能与处理意见混写 | 本期不写，保留原义 |
| `Ticket.resolution` | 老“解决方案内容”字段；现行代码未发现写入入口 | 详情、侧栏、CSV 导出只读此列 | 历史值和导出依赖，不能废弃 | 本期不写，不作猜测性迁移 |
| `Article.body` | `type=reply` 的处理说明；原入口创建时调用 `apply_transition(...allow_intermediate_transfer=True)` | 时间线、文章接口、MCP 读取 | 历史主要处理记录，必须保留 | `article`，本次处理意见唯一正文 |
| `ArticleAttachment` | FK `article_id`；旧上传仅用于 addition 图片 | 文章接口和时间线 | 旧 Article 附件不得转换 | `attachment`，挂本次处理 Article，Submission 通过 `article_id` 追溯 |

`Ticket.root_cause` 是根因当前真值；Submission 的字段快照只保留提交时的历史值。`Article.body` 是本次处理意见的唯一正文，Submission 的 `data` 不保存第二份 processing opinion；`solution` 与 `resolution` 本期保持原状。

## 首版表单

| 字段 | 必填 | 存储 |
|---|---|---|
| 原因分类 | 是 | Submission `cause_category`，受控 select：软件缺陷、硬件故障、配置错误、网络/环境、操作问题、其他 |
| 根因分析 | 是 | Ticket.root_cause；Submission 仅留历史快照 |
| 临时处置措施 | 是 | Submission `temporary_measure` |
| 根因无法短期解决 | 是 | Submission `requires_long_term_action` 布尔值 |
| 长期整改方案 | 上项为是时必填 | Submission `long_term_plan` |
| 相关材料附件 | 否 | ArticleAttachment；不入 JSON |
| 处理意见（结论） | 是 | Article.body；Submission.article_id 关联 |

所有处理部门共用 `node=processing` 的基础 FormBinding。后续部门差异再增加覆盖绑定，不复制四份表单。首版原因分类由用户确认，保存在已发布表单的 `options` 中，Vue 只读取后端 schema。

部署顺序：`alembic upgrade head` 后运行现有 `python scripts/seed.py --phase9`，或在已有业务种子的环境单独运行 `python scripts/seed_processing_form.py`。表单绑定启用后，处理节点会开始执行新的必填校验。

## 提交边界

`POST /tickets/{id}/node-submit` 锁定 Ticket，检查客户端期望的分类/部门/步骤/状态与数据库一致，重算 NodeContext、处理人权限和已发布表单。单次数据库事务写 Article、ArticleAttachment、Ticket.root_cause、TicketNodeSubmission，然后调用现有 `apply_transition(..., allow_intermediate_transfer=True)`，由其决定链内 transfer 或末节点 resolve。数据库失败全部回滚；上传文件采用现有存储目录并在异常时清理。进程崩溃可能留下未引用文件，这是当前本地文件存储与数据库无法跨介质原子提交的固有限制，后续可用周期性清理未引用文件处理。

处理节点有表单绑定时，旧 `type=reply` 完成入口、直接 PATCH resolve/root_cause 和批量 resolve 被拒绝；处理人仍可通过 `type=note` 添加不推进状态的普通回复。旧工单不做数据迁移：有 Submission 时按字段快照展示结构化历史，无 Submission 时详情继续按已有 Ticket 字段和 Article 展示。

`ticket_node_submissions.article_id` 指向本次 Article；外键阻止删除仍被 Submission 引用的 Article。当前没有删除 Submission 的业务 API。相关材料首版沿用现有存储目录和大小限制，允许图片/PDF；既有 ArticleAttachment 记录保持原样。

**后续技术债（暂不实施）**：现有 CSV“解决方案内容”仍只读 `Ticket.resolution`，而新 processing 的处理意见以 `Article.body` 为权威。待 `triage → processing → phone_feedback → closure` 主链跑通后，再统一核定查询、导出和统计口径；不得为修补 CSV 而在 processing 中另写一份 `resolution`。
