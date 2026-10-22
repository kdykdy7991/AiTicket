"""DEMO 工单安全清理工具(结构与 cleanup_e2e.py 对称)。

硬约束与 cleanup_e2e.py 一致:
- 默认 dry-run,加 --confirm 才执行
- 严格按 customer_name LIKE 'DEMO-%' 限定
- 不写 DELETE FROM tickets(用 IN (id_list))
- 拒绝 production
- 删除顺序按 FK:articles → dingtalk_notifications →
  ticket_state_logs → tickets

跑法:
    python scripts/cleanup_demo_tickets.py            # 预览
    python scripts/cleanup_demo_tickets.py --confirm  # 真删
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

DOCKER_CONTAINER = "skdy-ticket-dev-db-1"
DB_USER = "skdy"
DB_NAME = "skdy_ticket"
PRODUCTION_TOKENS = ("prod", "production")


def _fail(msg: str) -> None:
    print(f"[X] {msg}", file=sys.stderr)
    sys.exit(1)


def assert_not_production() -> None:
    for k in ("APP_ENV", "ENV"):
        v = os.environ.get(k, "").lower()
        if v in PRODUCTION_TOKENS:
            _fail(f"Refusing to run: {k}={v}")
    db = os.environ.get("DATABASE_URL", "").lower()
    if any(t in db for t in PRODUCTION_TOKENS):
        _fail(f"Refusing to run: DATABASE_URL contains 'prod': {db}")


def _psql(sql: str) -> tuple[int, str, str]:
    r = subprocess.run(
        ["docker", "exec", DOCKER_CONTAINER, "psql",
         "-U", DB_USER, "-d", DB_NAME, "-tA", "-c", sql],
        capture_output=True, text=True, timeout=30,
    )
    return r.returncode, r.stdout, r.stderr


def _count(prefix: str) -> int:
    sql = f"SELECT count(*) FROM tickets WHERE customer_name LIKE '{prefix}%';"
    rc, out, err = _psql(sql)
    if rc != 0:
        _fail(f"查询工单数失败: {err}")
    return int(out.strip() or "0")


def _ticket_ids(prefix: str) -> list[int]:
    sql = f"SELECT id FROM tickets WHERE customer_name LIKE '{prefix}%' ORDER BY id;"
    rc, out, err = _psql(sql)
    if rc != 0:
        _fail(f"查询 ticket id 失败: {err}")
    ids = []
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            ids.append(int(line))
    return ids


def _exec_delete(sql: str) -> int:
    rc, out, err = _psql(sql)
    if rc != 0:
        _fail(f"SQL 执行失败:\n  SQL: {sql}\n  ERR: {err}")
    m = re.search(r"DELETE\s+(\d+)", out)
    return int(m.group(1)) if m else 0


def main() -> int:
    assert_not_production()
    p = argparse.ArgumentParser(description="DEMO 工单清理工具")
    p.add_argument("--confirm", action="store_true",
                   help="真的删(默认只预览)")
    p.add_argument("--prefix", default="DEMO-",
                   help="customer_name 前缀(默认 DEMO-)")
    args = p.parse_args()

    if not re.match(r"^[A-Z0-9-]+$", args.prefix):
        _fail(f"非安全前缀:{args.prefix}(只允许 A-Z 0-9 -)")

    total = _count(args.prefix)
    print(f"==> 工单扫描结果")
    print(f"    prefix = {args.prefix}")
    print(f"    count  = {total}")
    if total == 0:
        print("[ok] 没有可清理的 DEMO 工单。")
        return 0

    ids = _ticket_ids(args.prefix)
    print(f"    ticket ids (前 20): {ids[:20]}{' ...' if len(ids) > 20 else ''}")

    if not args.confirm:
        print("\n[!] 仅预览模式,未删除。加 --confirm 才会执行。")
        return 0

    id_list = ",".join(str(i) for i in ids)
    delete_chain = [
        ("articles", f"DELETE FROM articles WHERE ticket_id IN ({id_list});"),
        ("dingtalk_notifications",
         f"DELETE FROM dingtalk_notifications WHERE ticket_id IN ({id_list});"),
        ("ticket_state_logs",
         f"DELETE FROM ticket_state_logs WHERE ticket_id IN ({id_list});"),
        ("tickets (DEMO only)",
         f"DELETE FROM tickets WHERE id IN ({id_list});"),
    ]
    print(f"\n==> 开始删除")
    for label, sql in delete_chain:
        n = _exec_delete(sql)
        print(f"    {label}: {n} 行")
    print("\n[ok] 清理完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())