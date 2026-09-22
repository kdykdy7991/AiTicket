"""E2E 工单安全清理工具。

硬约束:
- 默认预览模式(dry-run),打印将删除的工单数,不动 DB
- 加 --confirm 才执行删除
- 严格按 customer_name LIKE 'E2E-%' 限定,绝不写 DELETE FROM tickets
- 同样拒绝 production 环境
- 先删依赖表(articles / reminders / dingtalk_notifications /
  ticket_state_logs),再删 tickets 本身(避开 FK 报错)
- 支持 --batch-id 只清某个 batch

跑法:
    # 预览
    python scripts/cleanup_e2e.py
    # 真的删
    python scripts/cleanup_e2e.py --confirm
    # 只清某个批次
    python scripts/cleanup_e2e.py --confirm --batch-id 20260923-074451
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


def _count(prefix: str, batch_id: str | None) -> int:
    where = f"customer_name LIKE '{prefix}%'"
    if batch_id:
        where += f" AND customer_name LIKE '%{batch_id}%'"
    rc, out, err = _psql(f"SELECT count(*) FROM tickets WHERE {where};")
    if rc != 0:
        _fail(f"查询工单数失败: {err}")
    return int(out.strip() or "0")


def _ticket_ids(prefix: str, batch_id: str | None) -> list[int]:
    where = f"customer_name LIKE '{prefix}%'"
    if batch_id:
        where += f" AND customer_name LIKE '%{batch_id}%'"
    rc, out, err = _psql(
        f"SELECT id FROM tickets WHERE {where} ORDER BY id;"
    )
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
    # psql -tA 返回 "DELETE <n>"
    m = re.search(r"DELETE\s+(\d+)", out)
    return int(m.group(1)) if m else 0


def main() -> int:
    assert_not_production()
    p = argparse.ArgumentParser(description="E2E 工单清理工具")
    p.add_argument("--confirm", action="store_true",
                   help="真的删(默认只预览)")
    p.add_argument("--batch-id", default=None,
                   help="只清某个 batch_id(包含此子串)")
    p.add_argument("--prefix", default="E2E-",
                   help="customer_name 前缀(默认 E2E-)")
    args = p.parse_args()

    if not re.match(r"^[A-Z0-9-]+$", args.prefix):
        _fail(f"非安全前缀:{args.prefix}(只允许 A-Z 0-9 -)")

    # 1) 预览
    total = _count(args.prefix, args.batch_id)
    print(f"==> 工单扫描结果")
    print(f"    prefix = {args.prefix}")
    if args.batch_id:
        print(f"    batch  = {args.batch_id}")
    print(f"    count  = {total}")
    if total == 0:
        print("[ok] 没有可清理的 E2E 工单。")
        return 0

    ids = _ticket_ids(args.prefix, args.batch_id)
    print(f"    ticket ids (前 20): {ids[:20]}{' ...' if len(ids) > 20 else ''}")

    if not args.confirm:
        print("\n[!] 仅预览模式,未删除。加 --confirm 才会执行。")
        return 0

    # 2) 真删:先删依赖表,再删 tickets 本身
    # 按 FK 顺序
    id_list = ",".join(str(i) for i in ids)
    delete_chain = [
        ("articles", f"DELETE FROM articles WHERE ticket_id IN ({id_list});"),
        ("reminders", f"DELETE FROM reminders WHERE ticket_id IN ({id_list});"),
        ("dingtalk_notifications",
         f"DELETE FROM dingtalk_notifications WHERE ticket_id IN ({id_list});"),
        ("ticket_state_logs",
         f"DELETE FROM ticket_state_logs WHERE ticket_id IN ({id_list});"),
        ("tickets (E2E only)",
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