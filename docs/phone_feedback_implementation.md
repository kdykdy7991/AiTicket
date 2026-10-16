# 售后致电反馈节点：v2 字段与历史兼容

## 原有链路

- `backend/scripts/seed.py` 的 `dispatch_chain_steps()` 将指定业务保障分类链的最后一个售后步骤标为 `stage="phone_feedback"`。Node Context 在 `backend/app/services/node_context.py:derive_node_type()` 优先据此识别职责，与部门名称无关。
- 旧入口 `backend/app/api/v1/articles.py:create_article()` 以 `type="reply"` 保存 `Article.body`，再调用 `apply_transition(..., to_state="resolved", allow_intermediate_transfer=True)`。链末反馈通常由 `open` 进入 `resolved`，写 `TicketStateLog(action_type="resolve")`。
- `Ticket.callback_details`、`satisfaction`、`archive_notes` 由后续客服回访/归档接口处理，不是本次售后致电反馈正文。旧工单只有 Article、没有 Submission 时，详情时间线仍按 Article 展示。
- 旧 Article 回复不带附件；当前节点提交复用 ArticleAttachment 及现有上传校验。Submission 的 `article_id` 指向本次 Article，历史查询可追溯附件。

## 当前数据归属

| 字段 | 权威位置 | 说明 |
|---|---|---|
| phone_feedback_result | Article.body | 必填致电反馈正文；Submission 用 `article_id` 关联，不复制第二份正文 |
| 附件（可选） | ArticleAttachment | 挂本次反馈 Article |

`backend/scripts/seed_phone_feedback_form.py` 保留已发布的 `phone_feedback_v1` 定义及历史 Submission，发布只含 `phone_feedback_result` 的 `phone_feedback_v2`，停用通用 v1 binding 并启用 v2 binding。旧 v1 的 `verification_status` 和 `verification_conclusion` 只用于解释历史记录，当前提交不接受这两个字段。`resolve_form()` 仍按既有优先级支持部门或分类覆盖。提交沿用 `POST /tickets/{id}/node-submit`：锁 Ticket、比对上下文、校验当前表单、创建 Article 和附件、保存 Submission、调用 `apply_transition()`、关联状态日志并统一提交。旧 `reply` 在存在已发布表单时拒绝；处理人仍可添加不推进状态的 `note`。

反馈提交后仍按现有领域流转进入 `resolved` 和后续客服闭环；v2 不新增验证状态或自动退回规则。
