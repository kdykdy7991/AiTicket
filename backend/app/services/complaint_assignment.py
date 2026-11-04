"""Complaint responsibility choices and department-specific leaders."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.models.group import SkillGroup, UserSkillGroup
from app.models.user import User

OPTIONS = {
    2102: ["客户服务组负责人"],
    2103: ["渠道相关的重要投诉", "媒体相关的重要投诉", "产品中心重要投诉", "售前与解决方案业务投诉", "交付&售后业务投诉", "海洋应用业务投诉", "政企业务投诉", "产品线投诉", "车载应用投诉", "高精定位应用投诉"],
    2104: ["部门负责人分管领导"],
}

# Names and organisation labels are reference information from the supplied
# roster. Account binding is managed independently through user management.
ROSTER = {
    "客户服务组负责人": ("系统与网络运维", "杨冰"),
    "渠道相关的重要投诉": ("时空道宇副总经理", "陈国昌"),
    "媒体相关的重要投诉": ("品牌传播与大客户", "陈宁宁"),
    "产品中心重要投诉": ("产品中心", "贺巨方"),
    "售前与解决方案业务投诉": ("售前与解决方案部", "邱庆举"),
    "交付&售后业务投诉": ("交付&售后", "张华"),
    "海洋应用业务投诉": ("星座营销中心", "金国雍"),
    "政企业务投诉": ("星座营销中心", "黄贤格"),
    "产品线投诉": ("星座营销中心", "傅常海"),
    "车载应用投诉": ("星座营销中心", "朱武倩"),
    "高精定位应用投诉": ("星座营销中心", "曲苏超"),
    "部门负责人分管领导": ("时空道宇CTO", "丁晟"),
}

async def departments(db, category_id):
    flag = UserSkillGroup.complaint_division_leader if category_id == 2104 else UserSkillGroup.complaint_leader
    now = datetime.now(timezone.utc)
    rows = (await db.execute(select(SkillGroup, User, UserSkillGroup).join(UserSkillGroup, UserSkillGroup.skill_group_id == SkillGroup.id).join(User, User.id == UserSkillGroup.user_id).where(
        flag.is_(True), User.is_active.is_(True),
        or_(UserSkillGroup.effective_from.is_(None), UserSkillGroup.effective_from <= now),
        or_(UserSkillGroup.effective_to.is_(None), UserSkillGroup.effective_to >= now),
    ).order_by(SkillGroup.name, User.name, User.id))).all()
    result = {}
    for group, user, membership in rows:
        if category_id == 2102 and group.name != "客户服务组":
            continue
        item = result.setdefault(group.id, {"id": group.id, "name": group.name, "people": []})
        item["people"].append({"id": user.id, "name": user.name, "responsibilities": membership.complaint_responsibilities})
    return list(result.values())

async def validate_assignment(db, category_id, responsibility, group_id, owner_id, *, draft=False):
    if not group_id and not owner_id and not responsibility and draft:
        return None
    if responsibility not in OPTIONS.get(category_id, []):
        raise HTTPException(422, detail="请选择当前投诉等级的责任部门")
    groups = await departments(db, category_id)
    group = next((g for g in groups if g["id"] == group_id), None)
    if group is None or owner_id not in {p["id"] for p in group["people"] if category_id != 2103 or responsibility in p["responsibilities"]}:
        raise HTTPException(422, detail="请选择已配置的部门及有效投诉负责人")
    return {"order": 1, "department_code": group["name"], "assigned_owner_id": owner_id,
            "complaint_responsibility": responsibility, "complaint_direct": True}
