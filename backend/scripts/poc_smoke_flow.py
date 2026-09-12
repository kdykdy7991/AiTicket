"""POC 质量问题闭环：端到端联调脚本。

用五个业务角色账号（+ 隐藏管理员）真实走一遍总约定主流程：

    售前提交 → 批准人审批 → 专项小组确认 → 专项小组流转分系统
    → 分系统接收 → 分系统提交闭环计划 → 售前确认计划
    → 分系统提交分析验证 → 质量评审 → 质量登记缺陷 → 已闭环

前置：`alembic upgrade head` + `python scripts/seed.py`，并已启动 API。

用法：
    python scripts/poc_smoke_flow.py
    python scripts/poc_smoke_flow.py --base-url http://127.0.0.1:8000 --password skdy123
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import httpx

API_PREFIX = "/api/v1"

ACCOUNTS = {
    "presales": ("presales01", "skdy123"),
    "approver": ("approver01", "skdy123"),
    "taskforce": ("taskforce01", "skdy123"),
    "subsystem": ("subsystem01", "skdy123"),
    "quality": ("quality01", "skdy123"),
    "admin": ("admin", "admin123"),
}

SUBSYSTEM_NAME = "系统总体"


class SmokeFailure(RuntimeError):
    pass


class POCSmokeFlow:
    def __init__(self, base_url: str, password_override: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.password_override = password_override
        self.tokens: dict[str, str] = {}
        self.user_ids: dict[str, int] = {}
        self.skill_group_ids: dict[str, int] = {}
        # trust_env=False：忽略开发机上不可用的系统代理（常见为 SOCKS）
        self.client = httpx.AsyncClient(
            base_url=self.base_url, timeout=20.0, trust_env=False
        )

    async def close(self) -> None:
        await self.client.aclose()

    # ── 基础设施 ──────────────────────────────────────────
    def _headers(self, role: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[role]}"}

    async def _request(self, role: str, method: str, path: str, **kwargs) -> dict:
        resp = await self.client.request(
            method, f"{API_PREFIX}{path}", headers=self._headers(role), **kwargs
        )
        if resp.status_code >= 400:
            raise SmokeFailure(f"{method} {path} -> {resp.status_code} {resp.text}")
        return resp.json() if resp.content else {}

    async def login_all(self) -> None:
        for role, (username, default_password) in ACCOUNTS.items():
            password = self.password_override or default_password
            resp = await self.client.post(
                f"{API_PREFIX}/auth/login",
                json={"username": username, "password": password},
            )
            if resp.status_code != 200:
                raise SmokeFailure(
                    f"登录失败 {username}: {resp.status_code} {resp.text}\n"
                    "请先执行：python scripts/seed.py"
                )
            body = resp.json()
            self.tokens[role] = body["access_token"]
            self.user_ids[role] = body["user"]["id"]
            print(f"  登录成功 {username:14s} role={body['user']['role']}")

        skill_groups = await self._request("admin", "GET", "/skill-groups")
        self.skill_group_ids = {g["name"]: g["id"] for g in skill_groups["data"]}
        if SUBSYSTEM_NAME not in self.skill_group_ids:
            raise SmokeFailure(f"分系统「{SUBSYSTEM_NAME}」不存在，请先执行 scripts/seed.py")

    # ── 流程步骤 ──────────────────────────────────────────
    async def step(self, role: str, label: str, method: str, path: str, **kwargs) -> dict:
        body = await self._request(role, method, path, **kwargs)
        state = body.get("state") or body.get("data", {}).get("state")
        suffix = f" → state={state}" if state else ""
        print(f"  [{role:9s}] {label}{suffix}")
        return body

    async def act(self, role: str, ticket_id: int, action: str, *, payload=None, comment=None) -> dict:
        detail = await self._request(role, "GET", f"/tickets/{ticket_id}")
        version = detail["state_version"]
        resp = await self._request(
            role,
            "POST",
            f"/tickets/{ticket_id}/actions",
            json={
                "action": action,
                "payload": payload or {},
                "comment": comment,
                "expected_version": version,
            },
        )
        print(
            f"  [{role:9s}] {action:22s} {detail['state']:>28s} → {resp['state']}"
            + (f"  ({comment})" if comment else "")
        )
        return resp

    async def run(self) -> None:
        print(f"1) 登录五个业务角色账号（{self.base_url}）")
        await self.login_all()

        print("\n2) 售前提交 POC 问题")
        planned = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        created = await self._request(
            "presales",
            "POST",
            "/tickets",
            json={
                "title": "POC 现场终端反复掉线",
                "product_line": "卫星通信终端",
                "customer_name": "某省应急厅",
                "priority": "p1_critical",
                "problem_type": "终端故障",
                "closure_requirement": "两周内给出闭环计划",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "location": "广东省深圳市南山区",
                "device_info": "终端 X1 / SN 0001 / 固件 3.2.1",
                "description": "现场终端每 30 分钟掉线一次，重启后恢复",
                "approver_id": self.user_ids["approver"],
            },
        )
        ticket = created["data"]
        ticket_id = ticket["id"]
        print(
            f"  [{ticket['number']}] state={ticket['state']} "
            f"责任角色={ticket['current_responsible_role']} 版本={ticket['state_version']}"
        )

        print("\n3) 主流程流转")
        await self.act("approver", ticket_id, "approve", comment="同意，转专项小组确认并流转")
        await self.act(
            "taskforce",
            ticket_id,
            "route",
            payload={
                "skill_group_id": self.skill_group_ids[SUBSYSTEM_NAME],
                "subsystem_owner_id": self.user_ids["subsystem"],
            },
            comment="问题描述准确，判定为终端系统问题",
        )
        await self.act(
            "subsystem",
            ticket_id,
            "submit_plan",
            payload={
                "temporary_measure": "现场临时重启终端并切换备用链路",
                "long_term_measure": "修复心跳重连逻辑，补充回归用例",
                "planned_completion_at": planned,
            },
        )
        await self.act("presales", ticket_id, "confirm_plan", comment="闭环计划认可")
        await self.act(
            "subsystem",
            ticket_id,
            "submit_analysis",
            payload={
                "initial_investigation": "初步排除链路与电源因素",
                "root_cause": "固件心跳定时器溢出导致重连失败",
                "analysis_report": "三次复现记录 + 日志定位到定时器溢出点",
            },
        )
        await self.act(
            "quality",
            ticket_id,
            "pass_review",
            payload={
                "verification_status": "resolved",
                "verification_conclusion": "现场验证通过，连续 72 小时无掉线",
                "quality_review_result": "同意纳入缺陷库",
            },
            comment="评审通过",
        )
        await self.act(
            "quality",
            ticket_id,
            "register_defect",
            payload={
                "defect_id": "BUG-POC-0001",
                "defect_repository_path": "svn://svn.example.com/poc/trunk/defects#1001",
            },
        )

        print("\n4) 闭环结果校验")
        final = await self._request("quality", "GET", f"/tickets/{ticket_id}")
        checks = [
            ("终态为 closed", final["state"] == "closed"),
            ("无可用动作", final["allowed_actions"] == []),
            ("缺陷 ID 已登记", bool(final["defect_id"])),
            ("SVN 路径已登记", bool(final["defect_repository_path"])),
            ("状态版本递增", final["state_version"] >= 10),
            ("流程日志完整", len(final["state_logs"]) >= 10),
            ("已逾期标记为否", final["is_overdue"] is False),
        ]
        for label, ok in checks:
            print(f"  {'✅' if ok else '❌'} {label}")
        if not all(ok for _, ok in checks):
            raise SmokeFailure("闭环校验未通过")

        logs = await self._request("quality", "GET", f"/tickets/{ticket_id}/state-logs")
        print("\n5) 流程时间线")
        for log in logs["data"]:
            action = log["action"] or "submit"
            print(
                f"  {log['created_at'][:19]}  {action:22s} "
                f"{str(log['from_state']):>26s} → {log['to_state']:<28s} "
                f"by {log['operator_name']}({log['operator_role']})"
            )

        print("\n6) 导出 POC 跟踪表（前 3 行）")
        resp = await self.client.get(
            f"{API_PREFIX}/tickets/export", headers=self._headers("quality")
        )
        for line in resp.text.splitlines()[:3]:
            print(f"  {line[:160]}")

        print(f"\n✅ 主流程联调通过，问题编号 {final['number']}（id={ticket_id}）")


async def main() -> int:
    parser = argparse.ArgumentParser(description="POC 主流程端到端联调")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="后端地址")
    parser.add_argument("--password", default=None, help="统一覆盖业务账号密码")
    args = parser.parse_args()

    flow = POCSmokeFlow(args.base_url, args.password)
    try:
        await flow.run()
    except SmokeFailure as exc:
        print(f"\n❌ 联调失败：{exc}")
        return 1
    finally:
        await flow.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
