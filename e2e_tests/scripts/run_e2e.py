"""E2E 总入口:环境检查 + 运行 pytest + 生成报告。

硬约束:
- 默认拒绝任何 production 环境(无 --force 类绕过)
- 不删除工单;数据保留供人工复查
- 失败不中断,继续跑后续场景

跑法:
    python scripts/run_e2e.py
或:
    SKDY_API_BASE=http://127.0.0.1:8001 python scripts/run_e2e.py

报告输出到:
    artifacts/e2e-report-<batch_id>.md
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── 路径配置 ─────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
E2E_ROOT = SCRIPT_DIR.parent  # e2e_tests/
BACKEND_ROOT = E2E_ROOT.parent / "backend"
ARTIFACTS_DIR = E2E_ROOT / "artifacts"

API_BASE = os.environ.get("SKDY_API_BASE", "http://127.0.0.1:8001")
ADMIN_USER = os.environ.get("SKDY_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("SKDY_ADMIN_PASS", "admin123")

PYTEST_BIN = BACKEND_ROOT / ".venv" / "bin" / "python"


# ── A. 生产环境硬拒 ─────────────────────────────────────
def assert_not_production() -> None:
    for k in ("APP_ENV", "ENV"):
        v = os.environ.get(k, "").lower()
        if v in ("production", "prod"):
            sys.exit(f"Refusing to run: {k}={v}")
    db = os.environ.get("DATABASE_URL", "").lower()
    if any(token in db for token in ("prod", "production")):
        sys.exit(f"Refusing to run: DATABASE_URL contains 'prod': {db}")


# ── B. 健康检查 ─────────────────────────────────────────
def check_api() -> bool:
    import urllib.request
    import urllib.error
    try:
        with urllib.request.urlopen(f"{API_BASE}/healthz", timeout=5) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError) as e:
        print(f"[X] API 不可达: {API_BASE}/healthz — {e}")
        return False


# ── C. 运行 pytest ─────────────────────────────────────
PASS_LINE = re.compile(r"^tests/[^\s]+::(\S+)\s+PASSED", re.M)
FAIL_LINE = re.compile(r"^tests/[^\s]+::(\S+)\s+FAILED", re.M)


# 透传给 pytest 的环境需要剥掉 socks 代理(httpx 不支持 socks scheme);
# 保留 HTTPS_PROXY 等方便其他工具用代理;只去掉 ALL_PROXY
def _sanitized_env(extra: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.lower() != "all_proxy"}
    env.update(extra)
    return env


def run_pytest(batch_id: str) -> tuple[int, list[str], set[str], set[str], float]:
    started = time.time()
    proc = subprocess.run(
        [
            str(PYTEST_BIN), "-m", "pytest", "tests/", "-v",
            "--tb=short", "-p", "no:cacheprovider",
            f"--rootdir={E2E_ROOT}",
        ],
        cwd=str(E2E_ROOT),
        capture_output=True,
        text=True,
        env=_sanitized_env({"E2E_BATCH_ID": batch_id}),
    )
    duration = time.time() - started
    output = proc.stdout + "\n" + proc.stderr
    passed = set(PASS_LINE.findall(output))
    failed = set(FAIL_LINE.findall(output))
    order: list[str] = []
    for line in output.splitlines():
        m = re.match(r"^tests/[^\s]+::(\S+)\s+(PASSED|FAILED)", line)
        if m:
            name = m.group(1)
            if name not in order:
                order.append(name)
    return proc.returncode, order, passed, failed, duration


# ── D. 列出本批次 E2E 工单 ──────────────────────────────
def list_e2e_tickets(batch_id: str) -> list[dict]:
    import urllib.request
    import urllib.parse
    import json

    def _post(url, payload):
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    def _get(url, token):
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)

    login = _post(f"{API_BASE}/api/v1/auth/login",
                  {"username": ADMIN_USER, "password": ADMIN_PASS})
    token = login["access_token"]

    # keyword 在 list 接口里 ilike 匹配;取所有 E2E 工单,二次过滤本 batch
    qs = urllib.parse.urlencode({"keyword": "E2E-", "page_size": 100})
    body = _get(f"{API_BASE}/api/v1/tickets?{qs}", token)
    items = body.get("data", body) if isinstance(body, dict) else body
    return [t for t in (items or []) if batch_id in (t.get("customer_name") or "")]


# ── E. 报告生成 ────────────────────────────────────────
def render_report(
    batch_id: str,
    started_at: datetime,
    duration: float,
    order: list[str],
    passed: set[str],
    failed: set[str],
    tickets: list[dict],
    alembic_head: str | None,
) -> str:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS_DIR / f"e2e-report-{batch_id}.md"

    total = len(order)
    pass_rate = (len(passed) / total * 100) if total else 0.0
    lines = [
        f"# E2E 报告 — batch {batch_id}",
            "",
            f"- **Batch ID**: `{batch_id}`",
            f"- **Start**: {started_at.isoformat()}",
            f"- **Duration**: {duration:.2f}s",
            f"- **API**: {API_BASE}",
            f"- **Alembic head**: {alembic_head or '(unknown)'}",
            "",
            "## 环境",
            "",
            f"- Database:dev DB (`skdy-ticket-dev-db-1`)",
            f"- Alembic revision:{alembic_head or 'n/a'}",
            f"- Total scenarios:{total}",
            f"- Pass rate:{pass_rate:.1f}%",
            "",
            "## Results",
            "",
            "| # | Scenario | Result | Ticket # |",
            "| --- | --- | --- | --- |",
        ]
    # 提取 test function 名 → customer_suffix 关键字映射
    # customer_name 形如 E2E-<suffix>-<batch_id>,suffix 由场景拼出
    def _customer_suffix(test_name: str) -> str | None:
        n = test_name.removeprefix("test_")
        # 取第一个下划线段作为业务后缀(测试名习惯: <scenario>_<flow>)
        # 但实际数据里 customer_suffix 在测试函数里硬编码,做映射:
        name_map = {
            "instant_consultation": "即时咨询",
            "brand_collaboration_routing": "品牌合作",
            "product_consultation_routing": "产品咨询",
            "plan_change_business_operation": "套餐变更",
            "finance_reconciliation_business_operation": "业财对账",
            "core_network_business_support": "核心网",
            "tt_and_control_business_support": "测运控",
            "satellite_business_support": "卫星",
            "terminal_software_parent_walk": "终端软件",
            "complaint_general": "一般投诉",
            "complaint_important": "重要投诉",
            "complaint_major": "重大投诉",
            # 13 是 multiplier 校验,无工单
            "complaint_multiplier_policy_seeded": None,
            # 14a-14e 不建工单,只走 resolve
            "parent_chain_l4_direct_hit": None,
            "parent_chain_l3_walks_to_l2": None,
            "parent_chain_l2_direct_hit": None,
            "parent_chain_all_miss": None,
            "parent_chain_complaint_l3_to_l2": None,
        }
        return name_map.get(n)

    for i, name in enumerate(order, 1):
        result = "PASS" if name in passed else "FAIL"
        ticket_no = ""
        suffix = _customer_suffix(name)
        if suffix:
            for t in tickets:
                cn = t.get("customer_name", "") or ""
                if cn.startswith(f"E2E-{suffix}-"):
                    ticket_no = t.get("number", "")
                    break
        lines.append(f"| {i:02d} | `{name}` | {result} | {ticket_no or '—'} |")

    lines += [
        "",
        "## Failures",
        "",
    ]
    if not failed:
        lines += ["(无)", ""]
    else:
        for f in failed:
            lines.append(f"- `{f}`")
        lines.append("")

    lines += [
        "## Created Tickets",
        "",
        f"共 **{len(tickets)}** 张 E2E 工单(保留在 dev DB,不打 rollback)。",
        "",
        "| Number | Customer | Category | State | Dispatcher |",
        "| --- | --- | --- | --- | --- |",
    ]
    for t in tickets:
        lines.append(
            f"| {t.get('number')} | `{t.get('customer_name')}` | "
            f"{t.get('category_name')} | {t.get('state')} | "
            f"{t.get('dispatcher_name') or '—'} |"
        )
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return str(out)


# ── F. 主流程 ─────────────────────────────────────────
def main() -> int:
    assert_not_production()

    batch_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    started_at = datetime.now(timezone.utc)
    print(f"== E2E batch {batch_id} ==")
    print(f"  API_BASE = {API_BASE}")

    if not check_api():
        print("[X] dev API 不可达;中止。")
        print("    启动: cd backend && docker compose up -d db redis api")
        return 2

    # 跑 pytest
    rc, order, passed, failed, duration = run_pytest(batch_id)
    print(f"\n== pytest rc={rc} pass={len(passed)} fail={len(failed)} dur={duration:.1f}s ==\n")

    # 拉本批次工单
    try:
        tickets = list_e2e_tickets(batch_id)
    except Exception as e:
        print(f"[!] 拉工单失败: {e}")
        tickets = []

    # 读 alembic head(通过 psql 在容器里查;若不可用留空)
    alembic_head = None
    try:
        import subprocess as sp
        r = sp.run(
            ["docker", "exec", "skdy-ticket-dev-db-1", "psql",
             "-U", "skdy", "-d", "skdy_ticket",
             "-c", "SELECT version_num FROM alembic_version;"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                line = line.strip()
                if re.match(r"^[a-z0-9]{10,}$", line):
                    alembic_head = line
                    break
    except Exception:
        pass

    # 生成报告
    path = render_report(
        batch_id=batch_id,
        started_at=started_at,
        duration=duration,
        order=order,
        passed=passed,
        failed=failed,
        tickets=tickets,
        alembic_head=alembic_head,
    )
    print(f"== report → {path} ==")
    return rc if failed else 0


if __name__ == "__main__":
    sys.exit(main())