"""E2E pytest fixtures.

提供:
- e2e_client: httpx.Client 指向真实 dev API (默认 http://127.0.0.1:8001)
- batch_id: 一次 pytest 进程一个,所有工单 description 都带这个 id
- token: admin token
- result_collector: 收集场景结果,供 run_e2e.py 生成报告
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import pytest

# 把项目根加进 path,确保能 import e2e_tests.tests 与 backend.app
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from e2e_tests.tests import helpers  # noqa: E402


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    return os.environ.get("SKDY_API_BASE", "http://127.0.0.1:8001")


@pytest.fixture(scope="session")
def api_reachable(e2e_base_url) -> bool:
    try:
        # trust_env=False:忽略 ALL_PROXY=socks://... 否则 httpx 抛 ValueError
        r = httpx.get(
            f"{e2e_base_url}/healthz", timeout=5.0, trust_env=False
        )
        return r.status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="session", autouse=True)
def require_dev_api(api_reachable, e2e_base_url):
    if not api_reachable:
        pytest.exit(
            f"\nE2E aborted: dev backend {e2e_base_url}/healthz 不可达.\n"
            f"  → 启动: cd backend && docker compose up -d db redis api\n"
            f"  → 或设 SKDY_API_BASE 指向实际 API。\n",
            returncode=2,
        )


@pytest.fixture(scope="session")
def batch_id() -> str:
    return helpers.new_batch_id()


@pytest.fixture(scope="session")
def e2e_client(e2e_base_url) -> httpx.Client:
    """所有场景共享一个 httpx.Client,避免连接池浪费。"""
    timeout = httpx.Timeout(30.0, connect=5.0)
    with httpx.Client(
        base_url=e2e_base_url, timeout=timeout, trust_env=False
    ) as c:
        yield c


@pytest.fixture(scope="session")
def token(e2e_client) -> str:
    return helpers.admin_token(e2e_client)


@pytest.fixture(scope="session")
def result_collector() -> list[helpers.ScenarioResult]:
    """收集所有 ScenarioResult。run_e2e.py 用它生成报告。"""
    return []