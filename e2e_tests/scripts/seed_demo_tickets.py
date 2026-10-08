"""DEMO 工单生成器(列表 / 筛选 / 报表 / Dashboard 验收用)。

设计原则:
- 不修改生产业务逻辑;所有状态机走真实 PATCH /tickets/{id} 流转
- 工单 customer_name 前缀 DEMO-,description 前缀 [DEMO]
- 不写死数据库主键;按业务属性查 category_id / dispatcher_id / owner_id
- DEMO 数据长期保留;可由 cleanup_demo_tickets.py 安全清理
- 生成的 created_at / solved_at / closed_at 用 DB 直写
  (API 不暴露这两个字段),靠 customer_name LIKE 'DEMO-%' 严格限定

跑法:
    # 默认 100 张
    python scripts/seed_demo_tickets.py
    # 自定义数量
    python scripts/seed_demo_tickets.py --count 50

DEMO 工单特征:
- 状态分布严格按规格:pending 10 / open 25 / resolved 20 /
  on_hold 10 / returned 5 / archived 25 / cancelled 5
- 分类分布:咨询 20 / 业务运营 20 / 业务保障 40 / 服务投诉 20
- 业务保障下细分到叶子
- 创建时间分布:今天 30 / 近 7 天 40 / 近 30 天 30
- SLA 状态由 created_at / solution_deadline / solved_at 推算
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API_BASE = os.environ.get("SKDY_API_BASE", "http://127.0.0.1:8001")
ADMIN_USER = os.environ.get("SKDY_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("SKDY_ADMIN_PASS", "admin123")

DOCKER_CONTAINER = "skdy-ticket-dev-db-1"
DB_USER = "skdy"
DB_NAME = "skdy_ticket"

CUSTOMER_COMPANIES = [
    "星河通信", "远航科技", "北斗应用中心", "天枢信息", "蓝海卫星",
    "海格电子", "银河航天", "极地物联网", "东方测控", "南方通信",
    "拓远导航", "瑞驰系统", "宏图遥感", "飞鸿智能", "凌霄物联",
    "云海算力", "极昼光电", "北极星通信", "天玑空间", "鲲鹏海事",
    "玄铁装备", "千寻位置", "彗星遥测", "翼展物流", "星耀测绘",
    "领航勘探", "神州卫星", "双鱼物联网", "天信终端", "原点遥感",
]

DEMO_DESC_POOL = [
    "客户来电咨询业务开通流程",
    "后台数据未及时同步到客户端",
    "终端设备上报异常告警",
    "客户反馈账单金额与预期不符",
    "套餐使用量临近上限",
    "请求协助远程配置设备参数",
    "链路偶发中断需排查",
    "升级到企业版套餐",
    "投诉客服响应时长",
    "新员工入职账号开通",
]

ROOT_CAUSE_POOL = [
    "链路配置漂移",
    "客户终端缓存失效",
    "计费参数未同步",
    "权限校验时序竞争",
    "第三方接口超时",
    "数据分区不一致",
]

SOLUTION_POOL = [
    "重新下发链路配置并回归测试",
    "清理缓存后重启服务",
    "重新校准计费参数并补发差额",
    "回滚权限变更并加互斥锁",
    "切换备用接口并配置熔断",
    "重建数据分区并校验一致性",
]


# ── API 调用 ──────────────────────────────────────────
def _http(method: str, url: str, *, token: str | None = None, body: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.load(r)
            return payload.get("data", payload) if isinstance(payload, dict) else payload
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="ignore")[:300]
        raise RuntimeError(f"HTTP {e.code} {method} {url}: {body_text}")


def login() -> str:
    return _http("POST", f"{API_BASE}/api/v1/auth/login",
                 body={"username": ADMIN_USER, "password": ADMIN_PASS})["access_token"]


def list_categories(token: str) -> list[dict]:
    body = _http("GET", f"{API_BASE}/api/v1/categories?include_inactive=true", token=token)
    flat: list[dict] = []

    def _walk(nodes: list[dict]) -> None:
        for n in nodes:
            flat.append(n)
            _walk(n.get("children") or [])

    _walk(body if isinstance(body, list) else [])
    return flat


def list_skill_groups(token: str) -> list[dict]:
    body = _http("GET", f"{API_BASE}/api/v1/skill-groups?page_size=100", token=token)
    return body if isinstance(body, list) else body.get("data", [])


def find_user_by_name(token: str, name: str) -> dict | None:
    body = _http("GET", f"{API_BASE}/api/v1/users?page_size=200", token=token)
    items = body if isinstance(body, list) else body.get("data", [])
    for u in items:
        if u.get("name") == name and u.get("is_active"):
            return u
    return None


def find_dispatcher(token: str, sg_id: int) -> dict | None:
    body = _http("GET", f"{API_BASE}/api/v1/skill-groups/{sg_id}/dispatchers", token=token)
    items = body if isinstance(body, list) else body.get("data", [])
    return items[0] if items else None


def create_ticket(token: str, payload: dict) -> dict:
    return _http("POST", f"{API_BASE}/api/v1/tickets", token=token, body=payload)


def patch_ticket(token: str, ticket_id: int, payload: dict) -> dict:
    return _http("PATCH", f"{API_BASE}/api/v1/tickets/{ticket_id}", token=token, body=payload)


# ── DB 直写(仅 DEMO 范围,严格 LIKE 限定) ────────────
def _psql(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", DOCKER_CONTAINER, "psql",
         "-U", DB_USER, "-d", DB_NAME, "-tA", "-c", sql],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        raise RuntimeError(f"psql failed: {r.stderr}")
    return r.stdout


def adjust_demo_timestamps(ticket_ids: list[int], created_at: datetime,
                            solved_at: datetime | None,
                            closed_at: datetime | None) -> None:
    """调整指定 ticket_ids 的 created_at / solved_at / closed_at。

    只对 customer_name LIKE 'DEMO-%' 的工单生效(双重保险)。
    """
    if not ticket_ids:
        return
    id_list = ",".join(str(i) for i in ticket_ids)
    sets = [f"created_at = '{created_at.isoformat()}'::timestamptz"]
    if solved_at:
        sets.append(f"solved_at = '{solved_at.isoformat()}'::timestamptz")
    if closed_at:
        sets.append(f"closed_at = '{closed_at.isoformat()}'::timestamptz")
    sql = (
        f"UPDATE tickets SET {', '.join(sets)} "
        f"WHERE id IN ({id_list}) "
        f"  AND customer_name LIKE 'DEMO-%';"
    )
    _psql(sql)


# ── 业务分布 ──────────────────────────────────────────
def choose_category(cats: list[dict], kind: str) -> dict | None:
    """按 kind 在 categories 中随机挑一个 leaf。"""
    name_map = {
        "consult": ["即时办结咨询", "品牌合作", "产品使用/参数咨询", "渠道/代理合作"],
        "ops": ["套餐变更", "业财对账"],
        "support": ["核心网系统", "测运控系统", "卫星系统", "终端软件", "硬件故障", "应用平台"],
        "complaint": ["一般投诉", "重要投诉", "重大投诉"],
    }
    candidates = name_map[kind]
    pool = [c for c in cats if c.get("name") in candidates and c.get("level", 1) >= 3]
    return random.choice(pool) if pool else None


def state_distribution() -> list[tuple[str, int]]:
    """按规格返回 [(state, count)] 列表,合计 100。"""
    return [
        ("pending", 10), ("open", 25), ("resolved", 20),
        ("on_hold", 10), ("returned", 5), ("archived", 25),
        ("cancelled", 5),
    ]


def kind_for_index(i: int, total: int) -> str:
    """按比例分类:咨询 20 / 业务运营 20 / 业务保障 40 / 服务投诉 20。"""
    pct = i / total
    if pct < 0.20:
        return "consult"
    if pct < 0.40:
        return "ops"
    if pct < 0.80:
        return "support"
    return "complaint"


def random_created_at() -> datetime:
    """30% 今天 / 40% 近 7 天 / 30% 近 30 天。"""
    now = datetime.now(timezone.utc)
    r = random.random()
    if r < 0.30:
        delta = timedelta(minutes=random.randint(0, 24 * 60))
    elif r < 0.70:
        delta = timedelta(days=random.randint(1, 7))
    else:
        delta = timedelta(days=random.randint(8, 30))
    return now - delta


# ── 主流程 ──────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="DEMO 工单生成器")
    p.add_argument("--count", type=int, default=100, help="生成工单数(默认 100)")
    p.add_argument("--seed", type=int, default=None, help="随机种子,便于复现")
    args = p.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    print(f"== DEMO 工单生成器 target={args.count} ==")
    token = login()
    cats = list_categories(token)
    print(f"  加载 {len(cats)} 个 categories")

    # 按 state 配额分配
    states: list[str] = []
    for state, n in state_distribution():
        states.extend([state] * n)
    # 截断 / 扩展到 args.count
    if len(states) < args.count:
        states.extend(["pending"] * (args.count - len(states)))
    states = states[:args.count]
    random.shuffle(states)

    # 按总索引分类 (咨询/业务运营/业务保障/服务投诉)
    by_kind: dict[str, list[str]] = {
        "consult": [], "ops": [], "support": [], "complaint": [],
    }
    for i in range(args.count):
        by_kind[kind_for_index(i, args.count)].append(states[i])

    created_ids: list[int] = []
    stats: dict[str, int] = {}

    for kind, state_list in by_kind.items():
        for state in state_list:
            cat = choose_category(cats, kind)
            if not cat:
                print(f"[!] 没有可用的 {kind} 分类,跳过")
                continue
            customer = f"DEMO-{random.choice(CUSTOMER_COMPANIES)}-{random.randint(1000, 9999)}"
            description = f"[DEMO] {random.choice(DEMO_DESC_POOL)}"
            priority = random.choice(["p1_urgent", "p2_important", "p3_normal", "p4_low"])
            complaint_level = None
            if kind == "complaint":
                complaint_level = {"一般投诉": "一般", "重要投诉": "重要", "重大投诉": "重大"}.get(cat["name"])

            payload = {
                "customer_name": customer,
                "description": description,
                "category_id": cat["id"],
                "priority": priority,
                "channel": random.choice(["phone", "email", "web"]),
                "customer_type": random.choice(["personal", "enterprise"]),
                "customer_phone": "1390000" + str(random.randint(1000, 9999)),
            }
            if complaint_level:
                payload["complaint_level"] = complaint_level

            try:
                ticket = create_ticket(token, payload)
            except Exception as e:
                print(f"[!] 建单失败: {e}")
                continue
            tid = ticket["id"]
            created_ids.append(tid)
            stats[cat["name"]] = stats.get(cat["name"], 0) + 1

            # 状态机推进
            try:
                if state == "open":
                    patch_ticket(token, tid, {"state": "open"})
                elif state == "resolved":
                    patch_ticket(token, tid, {"state": "open"})
                    patch_ticket(token, tid, {
                        "state": "resolved",
                        "root_cause": random.choice(ROOT_CAUSE_POOL),
                        "solution": random.choice(SOLUTION_POOL),
                    })
                elif state == "on_hold":
                    patch_ticket(token, tid, {"state": "open"})
                    patch_ticket(token, tid, {
                        "state": "on_hold",
                        "hold_until": (datetime.now(timezone.utc) + timedelta(days=3)).date().isoformat(),
                        "reason": "客户出差,暂缓至下周",
                    })
                elif state == "returned":
                    patch_ticket(token, tid, {
                        "state": "returned",
                        "reason": "信息不足,需补充客户联系方式",
                    })
                elif state == "archived":
                    patch_ticket(token, tid, {"state": "open"})
                    patch_ticket(token, tid, {
                        "state": "resolved",
                        "root_cause": random.choice(ROOT_CAUSE_POOL),
                        "solution": random.choice(SOLUTION_POOL),
                    })
                    patch_ticket(token, tid, {
                        "state": "archived",
                        "is_callbacked": True,
                        "callback_required": False,
                        "callback_details": "DEMO:已回访,客户满意",
                    })
                elif state == "cancelled":
                    patch_ticket(token, tid, {
                        "state": "cancelled",
                        "reason": "DEMO:客户主动撤销",
                    })
            except Exception as e:
                print(f"[!] 工单 {tid} 状态流转失败 ({state}): {e}")

            # 调整时间戳,让数据有"今天/近 7 天/近 30 天"分布
            created_at = random_created_at()
            solved_at = closed_at = None
            if state in ("resolved", "archived"):
                solved_at = created_at + timedelta(hours=random.randint(1, 48))
            if state == "archived":
                closed_at = solved_at + timedelta(hours=random.randint(1, 24))
            try:
                adjust_demo_timestamps([tid], created_at, solved_at, closed_at)
            except Exception as e:
                print(f"[!] 工单 {tid} 时间戳调整失败: {e}")

    print(f"\n== 生成完成 ==")
    print(f"   共 {len(created_ids)} 张 DEMO 工单")
    print(f"   分类分布:")
    for k, v in sorted(stats.items()):
        print(f"     {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())