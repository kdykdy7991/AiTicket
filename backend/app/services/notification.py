"""POC 流程钉钉通知服务。

只负责“动作后通知下一责任人”：
- 机器人未配置或发送失败一律不得阻断业务动作，但必须留下发送记录。
"""

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import DingtalkNotification

logger = logging.getLogger(__name__)

_DINGTALK_HOSTS = {"oapi.dingtalk.com"}


@dataclass(frozen=True)
class SendResult:
    success: bool
    error_message: str | None = None


def _is_valid_webhook(webhook_url: str) -> bool:
    """Only allow official DingTalk robot endpoints."""
    parsed = urlparse(webhook_url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in _DINGTALK_HOSTS
        and parsed.path == "/robot/send"
        and bool(parsed.query)
    )


async def send_dingtalk_text(
    webhook_url: str,
    content: str,
    at_mobiles: list[str] | None = None,
) -> SendResult:
    """Send a text message and interpret DingTalk's JSON response."""
    if not _is_valid_webhook(webhook_url):
        return SendResult(False, "钉钉 Webhook 地址无效")

    try:
        # Robot webhooks are called directly; ignore process-level proxy settings,
        # which are frequently developer-machine SOCKS proxies unsupported by httpx.
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            payload: dict = {"msgtype": "text", "text": {"content": content}}
            mobiles = [mobile.strip() for mobile in (at_mobiles or []) if mobile.strip()]
            if mobiles:
                payload["at"] = {"atMobiles": mobiles, "isAtAll": False}
            response = await client.post(webhook_url, json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("errcode") != 0:
            return SendResult(False, str(data.get("errmsg") or "钉钉返回未知错误")[:1000])
        return SendResult(True)
    except (httpx.HTTPError, ValueError) as exc:
        # Never log the URL: it contains the robot access token.
        logger.warning("DingTalk robot request failed: %s", type(exc).__name__)
        return SendResult(False, f"钉钉请求失败：{type(exc).__name__}")


def _poc_webhook(ticket) -> str | None:
    """POC 通知走分系统机器人。"""
    if ticket.skill_group and ticket.skill_group.dingtalk_webhook_url:
        return ticket.skill_group.dingtalk_webhook_url
    return None


def build_action_message(ticket, action, actor, to_state: str) -> str:
    from app.services.poc_workflow import responsible_role, responsible_user_id

    role = responsible_role(ticket)
    role_label = {
        "presales": "售前",
        "approver": "批准人",
        "taskforce": "专项小组",
        "subsystem": "分系统",
        "quality": "质量",
        None: "无",
    }.get(role, role or "无")
    assignee = ""
    uid = responsible_user_id(ticket)
    if uid:
        for attr in ("creator", "approver", "subsystem_owner"):
            person = getattr(ticket, attr, None)
            if person is not None and person.id == uid:
                assignee = f"（{person.name}）"
                break
    actor_label = "系统管理员代操作" if actor.role == "admin" else f"{actor.name}（{actor.role}）"
    return (
        "【POC 质量问题流转】\n"
        f"问题编号：{ticket.number or ticket.id}\n"
        f"问题名称：{ticket.title or '未填写'}\n"
        f"操作：{actor_label} 执行「{action.value}」\n"
        f"当前阶段：{to_state}\n"
        f"下一责任角色：{role_label}{assignee}"
    )


async def notify_poc_action(
    db: AsyncSession,
    ticket,
    action,
    actor,
    from_state,
    to_state,
) -> SendResult:
    """动作成功后通知下一责任人。异常由调用方兜底，绝不回滚业务。"""
    webhook_url = _poc_webhook(ticket)
    content = build_action_message(ticket, action, actor, to_state.value)

    if webhook_url:
        result = await send_dingtalk_text(webhook_url, content)
    else:
        result = SendResult(False, "分系统未配置钉钉 Webhook")

    from app.services.poc_workflow import responsible_user_id

    db.add(
        DingtalkNotification(
            ticket_id=ticket.id,
            type=f"poc_{action.value}"[:30],
            target_user_id=responsible_user_id(ticket),
            target_webhook=webhook_url,
            content=content,
            success=result.success,
            error_message=result.error_message,
        )
    )
    await db.flush()
    logger.info(
        "POC 通知已处理：ticket_id=%s action=%s success=%s",
        ticket.id,
        action.value,
        result.success,
    )
    return result
