# 文档归档（2026-09-30）

本目录存放**分派设计大版本（V0.21 / V0.85 流程）之前**的历史文档，仅作存档，不再维护、不代表当前系统状态。

| 文件 | 时期 | 被谁取代 |
|---|---|---|
| 00_overview ~ 07_requirements_supplement（8 篇） | 2026-05 ~ 06 初版设计 | `ticket_business_flow.md` + `ticket_dispatch_design.md` |
| api_design_v2.md | 2026-06 | 现行 API 以 `backend/app/api/v1/` 代码为准 |
| superpowers/specs/*（6 篇） | 2026-06 ~ 07 单点功能设计 spec | 各功能已实现，spec 仅留档 |
| ticket_architecture_audit.md | 2026-09-23 架构审计 | 后续 refactor 已落地 |
| ticket_architecture_refactor_result.md | 2026-09-24 重构结果 | 同上 |
| ticket_v086_gap_analysis.md | 2026-09-29 V0.86 差距分析 | 由 `ticket_dispatch_design.md` §9 现状差距取代 |

**现行文档（docs/ 根目录）**：

- `ticket_dispatch_design.md` —— 分派设计定稿（三级判断 + 两张解耦表）
- `ticket_business_flow.md` —— 当前代码的全链路状态机事实（改造期间的基线参照）
