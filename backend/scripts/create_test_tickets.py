"""创建 3 个测试工单：1 个待受理、2 个处理中。

约束：
- 创建者最终设为客服账号 wyz（id=12）
- 技能组用技术组（id=1）
- 部门对接人用技术组对接人 handler01（id=5）
- 处理中工单的处理人用同技能组处理人 tech02（id=10）
- 待受理工单无 owner，等待分派

实现方式：先用 admin 账号走完整 API 创建/流转（保证编号、SLA、状态日志正确），
再用 psql 把 creator_id 改成 wyz。
"""

import os
import subprocess
import sys

import requests

BASE = "http://127.0.0.1:8001/api/v1"
ADMIN = {"username": "admin", "password": "admin123"}
WYZ_ID = 12
COMPOSE_FILE = "/home/skdy/server/Skdy_Ticket_System/backend/docker-compose.yml"


def login():
    r = requests.post(f"{BASE}/auth/login", json={
        "username": ADMIN["username"],
        "password": ADMIN["password"],
    })
    r.raise_for_status()
    return r.json()["access_token"]


def create_ticket(token, title_suffix):
    payload = {
        "description": f"这是一个用于测试的测试工单：{title_suffix}。",
        "priority": "p4_enterprise",
        "channel": "web",
        "customer_type": "personal",
        "customer_name": "测试客户",
        "customer_phone": "13800138000",
        "category_id": 1,
        "symptom": "测试故障现象",
        "group_id": 1,
        "skill_group_id": 1,
        "dispatcher_id": 5,
    }

    r = requests.post(
        f"{BASE}/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    return r.json()["data"]


def set_open(token, ticket_id):
    r = requests.patch(
        f"{BASE}/tickets/{ticket_id}",
        json={"state": "open", "owner_id": 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    return r.json()


def update_creator(ticket_ids):
    ids = ",".join(str(i) for i in ticket_ids)
    sql = f"UPDATE tickets SET creator_id = {WYZ_ID} WHERE id IN ({ids});"
    cmd = [
        "docker", "compose", "-f", COMPOSE_FILE,
        "exec", "-T", "db", "psql", "-U", "skdy", "-d", "skdy_ticket", "-c", sql,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("更新 creator_id 失败：", result.stderr)
        sys.exit(1)
    print(f"已将 {len(ticket_ids)} 个工单的创建者更新为 wyz(id={WYZ_ID})")


def main():
    token = login()

    pending = create_ticket(token, "待受理")
    print(f"待受理工单：{pending['number']} (id={pending['id']})")

    open1 = create_ticket(token, "处理中-1")
    set_open(token, open1["id"])
    print(f"处理中工单：{open1['number']} (id={open1['id']}, owner_id=10)")

    open2 = create_ticket(token, "处理中-2")
    set_open(token, open2["id"])
    print(f"处理中工单：{open2['number']} (id={open2['id']}, owner_id=10)")

    update_creator([pending["id"], open1["id"], open2["id"]])
    print("测试工单创建完成。")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print("请求失败：", e)
        try:
            print(e.response.json())
        except Exception:
            print(e.response.text)
        sys.exit(1)
