# 节点字段归属（代码审计，2026-10-16）

依据：`backend/app/models/ticket.py`、`backend/app/schemas/ticket.py`、`backend/app/api/v1/articles.py`、`backend/app/services/state_machine.py`。历史数据风险指现存列或文章可能已有记录；未查询生产库，不能断言记录数量。

| 字段 | 当前是否已有 | 当前存储位置 | 历史数据风险 | 流程/报表依赖 | 最终归属 |
|---|---|---|---|---|---|
| 初步核查意见 | 否 | 无 | 无 | 无 | C Submission.initial_opinion |
| 目标流转部门 | 有，系统派生 | Ticket.skill_group_id、dispatch_chain_steps | 有 | 派单核心 | E 选择下一分类后由 refine 计算 |
| 终端名称 | 否 | 无 | 无 | 无 | C terminal_name |
| 终端 SN | 是 | Ticket.device_sn | 有 | 详情/筛选可用 | A Ticket.device_sn |
| ICCID | 否 | 无 | 无 | 无 | C iccid |
| IMSI | 否 | 无 | 无 | 无 | C imsi |
| 终端固件版本号 | 否 | 无 | 无 | 无 | C firmware_version |
| 上位机软件类型 | 否 | 无 | 无 | 无 | C host_software_type |
| 选星规则 | 否 | 无 | 无 | 无 | C satellite_selection_rule |
| 遮挡判定 | 否 | 无 | 无 | 无 | C obstruction_assessment |
| 新套餐名称 | 否 | 无 | 无 | 无 | C new_package_name（后续节点） |
| 变更申请单附件 | 有通用附件 | ArticleAttachment | 可能 | 文章附件 | B 附件结构（本期不接） |
| 开票申请流程批准附件 | 有通用附件 | ArticleAttachment | 可能 | 文章附件 | B 附件结构（本期不接） |
| 原因分类 | 否 | 无 | 无 | 无 | C cause_category（处理节点后续） |
| 根因分析 | 是 | Ticket.root_cause | 有 | 处理说明 | A Ticket.root_cause |
| 临时处置措施 | 否 | 无 | 无 | 无 | C temporary_measure（后续） |
| 长期整改方案 | 否 | 无 | 无 | 无 | C long_term_plan（后续） |
| 相关材料附件 | 有通用附件 | ArticleAttachment | 可能 | 文章附件 | B 附件结构 |
| 处理意见 | 是，叙述记录 | Article.body | 有 | 处理日志 | B Article.body |
| 最终处理结论 | 是 | Ticket.solution、Ticket.resolution（语义重叠） | 有 | resolve 路径 | A 暂定 Ticket.solution；接入 processing 前核定 resolution 迁移关系 |
| 是否为有效线索 | 不完全等价 | Ticket.is_opportunity 表示“是否线索” | 有 | 建单字段 | C 有效性判断（后续，先区分语义） |
| 客户初步评级 | 不完全等价 | Ticket.customer_level 表示客户等级 | 有 | 客户信息 | C 销售评级（后续，先区分语义） |
| 销售处理意见 | 是，通用记录 | Article.body | 有 | 文章日志 | B Article.body |
| 暂缓原因 | 是，动作原因 | TicketStateLog.reason | 有 | hold 动作 | B 状态日志原因（停用动作，未接表单） |
| 预计完成时间 | 是 | Ticket.hold_until | 有 | hold 动作 | A Ticket.hold_until |
| 验证状态 | 否 | 无 | 无 | 无独立验证节点 | C 后续核定 |
| 验证结论 | 否 | 无 | 无 | 无独立验证节点 | C 后续核定 |
| 致电反馈结果 | 是，通用记录 | Article.body、Ticket.callback_details（回访语义） | 有 | 反馈/回访 | B Article.body；与 callback_details 不混用 |
| 回访标记 | 是 | Ticket.is_callbacked、callback_required | 有 | 归档前置 | A 现有字段 |
| 关单结果 | 是，文本说明 | Ticket.archive_notes | 有 | archive 动作 | A Ticket.archive_notes；若需枚举另行建模 |
| 客户是否认可 | 无独立布尔语义 | Ticket.satisfaction 为满意度 | 有 | 归档限制 | C 独立认可判断（后续） |
| 满意度评分 | 是，分档而非数值评分 | Ticket.satisfaction | 有 | 不满意分支 | A Ticket.satisfaction（若需数值评分须先确认语义） |
| 客户不满原因 | 是 | Ticket.unsatisfied_reason | 有 | 归档限制 | A Ticket.unsatisfied_reason |
| 办结时间 | 是 | Ticket.closed_at | 有 | 归档时间 | D 系统生成 |
| 办结人工号 | 是 | TicketStateLog.operator_id | 有 | 审计日志 | D 归档动作操作人生成 |

A=Ticket 正式字段；B=Article/Attachment/日志等已有结构；C=Submission 扩展字段；D=系统生成；E=业务动作结果。`Ticket.device_sn` 为当前唯一权威值，Submission 仅留字段定义快照，不在 `data` 内复制 SN。

## 本期落地边界

仅发布 `after_sales_triage` v1：售后 + triage + 业务保障及其后代。固定必填 `initial_opinion`；按目标子分类祖先关系展示终端字段或选星/遮挡字段。`device_sn` 映射 Ticket 正式列；其余已接分诊字段写入 Submission。条件字段首版非必填，待业务核定后以新版本发布。

部署时先运行 `alembic upgrade head`，再运行 `python scripts/seed.py --phase9`（现有种子命令会补充 v1 表单）。已有基础数据的环境也可单独运行 `python scripts/seed_triage_form.py`。新版本只新增定义与绑定，旧 Submission 通过 `field_snapshot` 和 `GET /tickets/{id}/node-submissions` 按当时字段解释。
