# 本地工单测试工作流

> 用途:E2E 回归 + DEMO 数据。本地 dev API (`http://127.0.0.1:8001`)
> 与 dev DB (`skdy-ticket-dev-db-1`)。
>
> 工单数据**保留**在 dev DB,不打 rollback。所有清理走专用工具。

---

## 0. 前置条件

- `cd backend && docker compose up -d db redis api`
- API 通: `curl http://127.0.0.1:8001/healthz`
- admin 账号 `admin / admin123`(默认;支持 `SKDY_ADMIN_USER/PASS` 覆盖)
- Phase 9 seed 已跑: `python backend/scripts/seed.py --phase9`

---

## 1. E2E 回归工单(`customer_name` 前缀 `E2E-`)

按 18 个业务场景生成工单并断言,失败不中断。

```bash
# 总入口
python e2e_tests/scripts/run_e2e.py
# 报告 → artifacts/e2e-report-<batch>.md
```

直接跑 pytest:
```bash
cd e2e_tests && pytest -v
```

### 场景清单(18 个)

| # | 场景 | 分类 | 路由目标 |
| --- | --- | --- | --- |
| 01 | 即时办结咨询 | 1102 即时办结咨询 | 即时办结咨询组(archived) |
| 02 | 品牌合作 | 1202 | 品牌传播与大客户 / 钟梦茜 |
| 03 | 产品使用/参数咨询 | 1203 | 产品 / 张朝娟 |
| 04 | 套餐变更 | 2203 | 业务运营组 / 业务运营协调人 / 业务运营处理人 |
| 05 | 业财对账 | 2204 | 客服指定陈可意 → 销售提交 → 时空道宇财务姜敏 |
| 06 | 核心网系统 | 2311 | 业务保障组 → 核心网组 / 核心网处理人 |
| 07 | 测运控系统 | 2312 | → 测运控组 / 测运控处理人 |
| 08 | 卫星系统 | 2313 | → 卫星组 / 卫星处理人 |
| 09 | 终端软件 | 2321 | 父链上溯到 2301 业务保障组 |
| 10 | 一般投诉 | 2102 / complaint_level=一般 | 服务投诉协调组(×1.0) |
| 11 | 重要投诉 | 2103 / complaint_level=重要 | (×0.75) |
| 12 | 重大投诉 | 2104 / complaint_level=重大 | (×0.5) |
| 13 | 投诉倍率策略校验 | complaint_escalation_policies | — |
| 14a | L4 直命中 | 2311 | — |
| 14b | L3 退回 L2 命中 | 2322 | — |
| 14c | L2 直命中 | 2301 | — |
| 14d | 全链路无 rule | 1101 | — |
| 14e | 投诉 L3 退回 L2 | 2103 | — |

### 清理 E2E 工单

```bash
# 预览
python e2e_tests/scripts/cleanup_e2e.py
# 真删
python e2e_tests/scripts/cleanup_e2e.py --confirm
# 只清某个 batch
python e2e_tests/scripts/cleanup_e2e.py --confirm --batch-id 20260923-074451
```

删除顺序按 FK:articles → reminders → dingtalk_notifications →
ticket_state_logs → tickets。严格按 `customer_name LIKE 'E2E-%'`
限定,绝不写 `DELETE FROM tickets`。

---

## 2. DEMO 模拟工单(`customer_name` 前缀 `DEMO-`)

为列表 / 筛选 / 报表 / Dashboard 验收生成大量数据,长期保留。

```bash
# 默认 100 张
python e2e_tests/scripts/seed_demo_tickets.py
# 自定义数量
python e2e_tests/scripts/seed_demo_tickets.py --count 50
# 复现(指定随机种子)
python e2e_tests/scripts/seed_demo_tickets.py --count 50 --seed 42
```

### 状态分布(默认 100 张)

| 状态 | 数量 | 说明 |
| --- | --- | --- |
| pending | 10 | 待受理 |
| open | 25 | 处理中 |
| resolved | 20 | 已处理 |
| on_hold | 10 | 暂缓 |
| returned | 5 | 已退回 |
| archived | 25 | 已归档 |
| cancelled | 5 | 已撤销 |

### 分类分布

- 客户咨询(即时办结咨询 / 品牌合作 / 产品使用 / 渠道代理):20%
- 业务运营(套餐查询 / 套餐变更 / 业财对账):20%
- 业务保障(核心网 / 测运控 / 卫星 / 终端软件 / 硬件故障 / 应用平台):40%
- 服务投诉(一般 / 重要 / 重大):20%

### 时间分布

- 今天 30%
- 近 7 天 40%
- 近 30 天 30%

`created_at` / `solved_at` / `closed_at` 通过 psql 直写
(API 不暴露时间戳字段),UPDATE 同时带 `customer_name LIKE 'DEMO-%'`
双重保险。

### 清理 DEMO 工单

```bash
# 预览
python e2e_tests/scripts/cleanup_demo_tickets.py
# 真删
python e2e_tests/scripts/cleanup_demo_tickets.py --confirm
```

---

## 3. 环境安全(硬约束)

所有脚本启动时会拒绝 production:

- `APP_ENV=production` 或 `ENV=production` → 立即退出
- `DATABASE_URL` 含 `prod` 或 `production` → 立即退出

**不提供 `--force-production` 绕过**。

---

## 4. 文件布局

```
e2e_tests/
├── pytest.ini                          # pytest 配置(asyncio auto)
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # session 级 fixtures
│   ├── helpers.py                      # 共享工具(login/patch/state polling)
│   ├── test_instant_consultation.py    # 01
│   ├── test_consultation_routing.py    # 02 03
│   ├── test_business_operation.py      # 04 05
│   ├── test_business_support.py        # 06 07 08 09
│   ├── test_complaint.py               # 10 11 12 13
│   └── test_routing_inheritance.py     # 14a-e
├── scripts/
│   ├── run_e2e.py                      # E2E 总入口 + 报告
│   ├── cleanup_e2e.py                  # E2E 清理
│   ├── seed_demo_tickets.py            # DEMO 生成器
│   └── cleanup_demo_tickets.py         # DEMO 清理
├── artifacts/
│   └── e2e-report-<batch>.md           # 报告输出
└── docs/
    └── local_ticket_test_workflow.md   # 本文件
```

---

## 5. 已知约束 / TODO

- **SLA 倍率**:`sla_policies` 表为空(用户已知,"SLA 策略未定暂不修"),
  E2E 测试不断言 `solution_deadline` 数值;只校验 `complaint_level`
  字段与倍率策略表本身的数据正确性。
- **on_hold + SLA**:旧记忆已知 on_hold 仍计时,E2E 不做 SLA 暂停/恢复
  校验,等 SLA 策略确定后补。
- **客户未解决自动退回**:不实现(E2E 测试也不触发)。
- **临时分类探测**:14 父链上溯场景改用现有分类(2311/2322/2301/1101/2103)
  验证,不再动态创建/删除 probe 分类(早期方案 fixture teardown 不稳)。
- **token_version**:admin 每次登录会 bump token_version,E2E fixture
  用 function-scope token + `get_ticket_until_state` / `get_state_logs_until`
  轮询避免偶发抢跑。
- **httpx socks proxy**:本地 `ALL_PROXY=socks://...` 会让 httpx 抛
  `ValueError: Unknown scheme`,conftest 与 run_e2e.py 都用
  `trust_env=False` / 剥 `ALL_PROXY` 规避。
