"""E2E tests that hit the live dev backend on port 8001.

默认运行模式:
- 使用当前本地开发数据库 (docker 容器 skdy-ticket-dev-db-1)
- 不删除创建的工单,数据保留供人工复查
- 失败不中断,继续跑后续场景,统一汇总

跑法:
    python scripts/run_e2e.py
或直接:
    cd e2e_tests && pytest -s -v
"""