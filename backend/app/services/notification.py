"""DingTalk group robot notification service."""

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import DingtalkNotification
from app.models.ticket import Article, Ticket

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


def _ticket_webhook(ticket: Ticket) -> str | None:
    """Skill-group robot takes precedence over customer-service group robot."""
    if ticket.skill_group and ticket.skill_group.dingtalk_webhook_url:
        return ticket.skill_group.dingtalk_webhook_url
    if ticket.group and ticket.group.dingtalk_webhook_url:
        return ticket.group.dingtalk_webhook_url
    return None


async def remind_hold_expiry(ticket: Ticket, hold_reason: str | None, db: AsyncSession) -> SendResult:
    """「预计恢复时间已到」提醒：只提示，不做任何状态变更，也不涉及 SLA。

    措辞刻意避开「超时 / SLA 超期」——预计恢复时间不是 deadline，只是处理人
    自己估计什么时候能继续处理。工单到达该时间后仍保持 on_hold，由处理人决定
    是否恢复。
    """
    webhook_url = _ticket_webhook(ticket)
    ticket_label = ticket.number or str(ticket.id)
    owner_mobile = ticket.owner.phone.strip() if ticket.owner and ticket.owner.phone else None
    at_line = f"\n当前处理人：@{owner_mobile}" if owner_mobile else ""
    hold_until_text = (
        ticket.hold_until.strftime("%Y-%m-%d %H:%M") if ticket.hold_until else "—"
    )
    content = (
        "【工单预计恢复时间已到】\n"
        f"工单编号：{ticket_label}\n"
        f"问题摘要：{ticket.title or '工单'}\n"
        f"暂缓原因：{(hold_reason or '—').strip()}\n"
        f"预计恢复时间：{hold_until_text}"
        f"{at_line}\n"
        "预计恢复时间已到，请确认是否恢复处理。"
    )

    if webhook_url:
        result = await send_dingtalk_text(
            webhook_url,
            content,
            at_mobiles=[owner_mobile] if owner_mobile else None,
        )
    else:
        result = SendResult(False, "工单所属技能组或客服组未配置钉钉 Webhook")

    db.add(DingtalkNotification(
        ticket_id=ticket.id,
        type="hold_expiry",
        target_user_id=ticket.owner_id,
        target_webhook=webhook_url,
        content=content,
        success=result.success,
        error_message=result.error_message,
    ))
    logger.info(
        "DingTalk hold-expiry reminder handled: ticket_id=%s success=%s",
        ticket.id,
        result.success,
    )
    return result


async def remind_handler(ticket: Ticket, article: Article, db: AsyncSession) -> SendResult:
    """Notify the ticket's group robot about a reminder."""
    webhook_url = _ticket_webhook(ticket)
    ticket_label = ticket.number or str(ticket.id)
    owner_mobile = ticket.owner.phone.strip() if ticket.owner and ticket.owner.phone else None
    at_line = f"\n处理人：@{owner_mobile}" if owner_mobile else ""
    content = (
        "【客服工单催办提醒】\n"
        f"工单编号：{ticket_label}\n"
        f"工单标题：{ticket.title or '工单'}\n"
        f"催办内容：{article.body.strip()}"
        f"{at_line}"
    )

    if webhook_url:
        result = await send_dingtalk_text(
            webhook_url,
            content,
            at_mobiles=[owner_mobile] if owner_mobile else None,
        )
    else:
        result = SendResult(False, "工单所属技能组或客服组未配置钉钉 Webhook")

    db.add(DingtalkNotification(
        ticket_id=ticket.id,
        type="reminder",
        target_user_id=ticket.owner_id,
        target_webhook=webhook_url,
        content=content,
        success=result.success,
        error_message=result.error_message,
    ))
    logger.info(
        "DingTalk reminder handled: ticket_id=%s success=%s",
        ticket.id,
        result.success,
    )
    return result
