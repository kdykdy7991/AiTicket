"""通过开发 API 和真实非管理员账号生成一批工单；不直接写入业务表。"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("SKDY_API_BASE", "http://127.0.0.1:8001")
PASSWORD = os.environ.get("SKDY_SEED_PASSWORD", "skdy123")
CREATOR_PASSWORD = os.environ.get("SKDY_CREATOR_PASSWORD", PASSWORD)
# 实名客服账号；协调人账号只负责对应业务节点，不用于创建工单。
CREATORS = ["wangyaozong"]

CASES = [
    (1204, "渠道合作申请", "咨询渠道合作的申请材料与办理流程", "pending"),
    (1202, "企业品牌合作咨询", "询问联合品牌活动合作方式和负责部门", "pending"),
    (2203, "企业套餐升档申请", "客户申请下月起升级企业通信套餐", "transfer"),
    (2204, "跨月账单金额核对", "客户反馈账单与合同约定金额不一致", "transfer"),
    (2311, "核心网接入异常", "终端注册失败，需排查核心网鉴权链路", "open"),
    (2312, "测运控链路抖动", "地面站回传链路间歇性中断", "resolved"),
    (2102, "服务响应时效投诉", "客户投诉首次回复等待时间较长", "pending"),
    (2103, "重点客户服务投诉", "重点客户反馈问题处理进度不透明", "open"),
    (2301, "业务保障系统告警", "监控发现业务保障平台告警需人工核实", "hold"),
    (2203, "套餐降档申请", "客户希望调整下一计费周期套餐档位", "returned"),
    (1203, "终端参数配置疑问", "客户咨询终端固件参数及配置步骤", "cancelled"),
    (2313, "卫星遥测数据延迟", "遥测数据到达平台存在明显延迟", "resolved"),
]


def call(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(BASE + "/api/v1" + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.load(response)
            return result.get("data", result) if isinstance(result, dict) else result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:350]
        raise RuntimeError(f"{method} {path}: HTTP {exc.code} {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="实际创建；默认仅预检")
    args = parser.parse_args()
    if os.environ.get("APP_ENV", "").lower() in {"prod", "production"}:
        raise RuntimeError("拒绝在生产环境生成测试工单")

    tokens: dict[str, str] = {}
    users: dict[int, dict] = {}

    def login(username: str) -> str:
        if username not in tokens:
            password = CREATOR_PASSWORD if username in CREATORS else PASSWORD
            result = call("POST", "/auth/login", body={"username": username, "password": password})
            if result["user"]["role"] == "admin":
                raise RuntimeError(f"禁止使用管理员账号: {username}")
            tokens[username] = result["access_token"]
        return tokens[username]

    for username in CREATORS:
        login(username)
    first_token = tokens[CREATORS[0]]
    for user in call("GET", "/users", first_token):
        users[user["id"]] = user

    routes: dict[int, dict] = {}
    for category_id in {case[0] for case in CASES}:
        route = call("POST", "/routing-rules/resolve", first_token, {"category_id": category_id})
        if not route.get("matched") or not route.get("dispatcher_id"):
            raise RuntimeError(f"分类 {category_id} 没有有效对接人路由: {route}")
        routes[category_id] = route
        for key in ("dispatcher_id", "owner_id"):
            user_id = route.get(key)
            if user_id and user_id not in users:
                raise RuntimeError(f"分类 {category_id} 的 {key}={user_id} 不在当前组用户列表")
            if user_id:
                login(users[user_id]["username"])

    print(f"预检通过：{len(CASES)} 个场景，{len(tokens)} 个非管理员账号，{len(routes)} 个分类")
    if not args.apply:
        print("未创建工单；加 --apply 执行")
        return 0

    created: list[tuple[str, str, str]] = []
    for index, (category_id, title, description, target) in enumerate(CASES, 1):
        creator = CREATORS[(index - 1) % len(CREATORS)]
        route = routes[category_id]
        payload = {
            "description": f"[API测试] {title}：{description}",
            "priority": "p3_normal", "channel": "phone",
            "customer_type": "enterprise" if index % 3 == 0 else "personal",
            "customer_name": f"API测试-{title}",
            "customer_phone": f"1390000{index:04d}",
            "contact_phone": f"1390000{index:04d}",
            "category_id": category_id,
        }
        ticket = call("POST", "/tickets", login(creator), payload)
        ticket_id = ticket["id"]
        state = ticket["state"]
        created.append((ticket["number"], target, creator))
        try:
            if target == "instant" or target == "pending":
                pass
            elif target == "cancelled":
                ticket = call("PATCH", f"/tickets/{ticket_id}", login(creator), {"state": "cancelled", "reason": "客户取消配置咨询"})
                state = ticket["state"]
            elif target == "returned":
                dispatcher = users[ticket["dispatcher_id"]]["username"]
                ticket = call("PATCH", f"/tickets/{ticket_id}", login(dispatcher), {"state": "returned", "reason": "需补充套餐变更授权材料"})
                state = ticket["state"]
            else:
                dispatcher = users[ticket["dispatcher_id"]]["username"]
                owner_id = route.get("owner_id") or ticket["dispatcher_id"]
                ticket = call("PATCH", f"/tickets/{ticket_id}", login(dispatcher), {"state": "open", "owner_id": owner_id})
                state = ticket["state"]
                owner = users[owner_id]["username"]
                if target == "transfer":
                    ticket = call("POST", f"/tickets/{ticket_id}/transfer", login(owner), {"reason": "本部门审核完成，转下一部门处理"})
                    state = ticket["state"]
                    next_dispatcher_id = ticket["dispatcher_id"]
                    next_dispatcher = users[next_dispatcher_id]["username"]
                    ticket = call("PATCH", f"/tickets/{ticket_id}", login(next_dispatcher), {"state": "open", "owner_id": next_dispatcher_id})
                    state = ticket["state"]
                elif target == "hold":
                    ticket = call("PATCH", f"/tickets/{ticket_id}", login(owner), {"state": "on_hold", "reason": "等待客户提供告警日志"})
                    state = ticket["state"]
                elif target == "resolved":
                    ticket = call("PATCH", f"/tickets/{ticket_id}", login(owner), {"state": "resolved", "root_cause": "配置与现场参数不一致", "solution": "已校正配置并验证链路恢复"})
                    state = ticket["state"]
            if state != {"instant": "archived", "transfer": "open", "hold": "on_hold"}.get(target, target):
                raise RuntimeError(f"状态不符: {state}")
            print(f"{index:02d} {ticket['number']} {title} → {state}（创建：{creator}）")
        except Exception:
            print(f"第 {index} 张工单 {ticket['number']} 已创建，但后续流转失败")
            raise
    print(f"完成：{len(created)} 张工单，全部通过非管理员账号调用 API 创建")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
