---
name: zammad_analysis_notes
description: Zammad codebase analysis summary - core abstractions, architecture, and positioning for internal service desk
type: project
originSessionId: 14623b2e-31d6-48fc-b48a-a4e56d5548d3
---
# Zammad 分析结论（2026/05/29）

## 1. Zammad 是什么

**Zammad 是一个以"对话线程"为核心组织的客服工单系统**——它的核心抽象不是"工单状态机"，而是 **Ticket（工单）+ Ticket::Article（对话条目）** 的结构，整个系统围绕一个"可以追加回复的会话线程"来构建，状态机、SLA、触发器、权限都是这个线程的附属能力，而不是核心。

## 2. 核心抽象及作用

| 抽象 | 一句话解释 |
|---|---|
| **Ticket** | 一次客户请求的容器，记录 title、state、priority、owner、customer、group、escalation 时间，以及和这个请求相关的所有往来记录 |
| **Ticket::Article** | Ticket 内的一条对话记录（客户来信、客服回复、内部备注、聊天消息），每个 Article 有 type（email/note/chat）和 sender（customer/agent/system） |
| **User** | 系统的用户角色实体，同时承载 Agent（客服）和 Customer（客户），通过 Role 区分权限 |
| **Group** | 客服团队/队列的抽象，工单归属到 Group，Agent 通过 Group 获得工单访问权限，支持树状嵌套 |
| **Organization** | 客户的组织实体，一个 Organization 下可以关联多个 User，用于客户统一管理和共享上下文 |
| **Role / Permission** | 基于角色的访问控制，Permission 是细粒度能力（如 `ticket.agent`），Role 是权限的打包集合 |
| **Ticket::State / Ticket::Priority** | 可配置的工单状态机（new/open/pending/closed/merged）和优先级，通过 state_type 做状态分类 |
| **Trigger** | 基于条件的事件驱动自动化（当 X 状态+Y 条件时，执行 Z 操作），在 TransactionDispatcher 中被触发 |
| **SLA + Calendar** | 基于日历的升级时间管理（first_response_time、update_time、solution_time），通过 Calendar 定义工作时段 |
| **Overview** | 保存的查询视图，给客服人员提供 dashboard 分组（如"我的待处理"、"紧急"） |
| **Channel** | 消息输入渠道的抽象（Email/Web/Chat/Telephone/Facebook/Twitter），每个 Channel 绑定到 Group |
| **Link** | 任意两个对象（如 Ticket↔Ticket、Ticket↔KnowledgeBase::Answer）的关联，支持 parent/child/block 等关系类型 |
| **TransactionDispatcher** | 变更事件的分发中枢，所有 Model 的 create/update 回调汇入 EventBuffer，再批量 dispatch 到 sync backends（触发器、通知）和 async TransactionJob |

## 3. Zammad 不解决什么问题

- **项目管理**：没有 Sprint、看板、Story Point、Epic 概念。多工单关联只能靠 Link 手动维护
- **复杂流程编排**：Trigger 只做"条件→动作"，无分支/循环/审批流，无 BPMN 级别设计器
- **多租户隔离**：Group 做团队隔离，但不解决"租户 A 数据对租户 B 完全不可见"的合规要求——所有 Group 共享同一数据库实例和 Schema
- **独立知识库**：Knowledge Base 是附属功能，不能作为独立产品使用
- **结构化数据采集**：表单能力弱，没有复杂表单逻辑，主要靠自由文本 + Article

## 4. 运行架构

**进程模型**：一个 Rails 主进程（Web）+ 一个 BackgroundServices 进程（fork/thread 两种模式）。进程间通过 Signal（TERM/INT）优雅关闭，30s SHUTDOWN_GRACE_PERIOD。

**配置加载**：`Setting` 模型用类变量做进程内缓存，15 秒 TTL。`Setting.get(name)` 是主要读取接口，写入后广播到前端和 GraphQL 订阅。

**状态管理**：所有 Model 的 create/update 通过 `HasTransactionDispatcher` 混入，在 `after_commit` 时将事件写入 `EventBuffer`，`TransactionDispatcher` 批量消费。实时更新通过 WebSocket + ActionCable（走 Redis pub/sub）。

**数据库**：PostgreSQL，~500 个 migration，tickets 表 30+ 索引，主要覆盖 `(group_id, state_id, owner_id, created_at)` 组合。

## 5. 与内部客服工单需求的匹配度

**方向一致**：客服工单的创建/分配/回复/关闭、多渠道接入、SLA 监控、Trigger 自动化、基础工作量报表，均原生支持。

**明显不匹配**：
- 多租户严格隔离 → Group 模型无法满足
- ITSM 之外的工单类型（HR工单、采购审批流）→ Ticket 模型针对客服优化，做其他类型需大量 hack
- 项目级任务分解（需求拆 sub-task）→ Link 模型能做但勉强，无原生支持
- 国产化信创兼容 → 主要跑在 Debian/Ubuntu + PostgreSQL + Redis，国产 OS/数据库无官方支持