"""Notification service — placeholders for future channels (DingTalk, etc.)."""

import logging

from app.models.ticket import Article, Ticket

logger = logging.getLogger(__name__)


async def remind_handler(ticket: Ticket, article: Article) -> None:
    """Notify the current handler that the ticket has been urged.

    This is a placeholder extension point. The actual DingTalk / enterprise
    WeChat / email integration can be wired here without changing the API
    controller.
    """
    logger.info(
        "reminder created: ticket_id=%s sender_id=%s body=%s",
        ticket.id, article.sender_id, article.body,
    )
