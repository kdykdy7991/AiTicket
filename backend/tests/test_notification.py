"""Unit tests for DingTalk group robot notifications."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.notification import send_dingtalk_text


VALID_WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=test-token"


@pytest.mark.asyncio
async def test_send_dingtalk_text_success():
    response = httpx.Response(
        200,
        json={"errcode": 0, "errmsg": "ok"},
        request=httpx.Request("POST", VALID_WEBHOOK),
    )
    post = AsyncMock(return_value=response)

    with patch("app.services.notification.httpx.AsyncClient.post", post):
        result = await send_dingtalk_text(VALID_WEBHOOK, "测试消息")

    assert result.success is True
    post.assert_awaited_once_with(
        VALID_WEBHOOK,
        json={"msgtype": "text", "text": {"content": "测试消息"}},
    )


@pytest.mark.asyncio
async def test_send_dingtalk_text_at_mobile():
    response = httpx.Response(
        200,
        json={"errcode": 0, "errmsg": "ok"},
        request=httpx.Request("POST", VALID_WEBHOOK),
    )
    post = AsyncMock(return_value=response)

    with patch("app.services.notification.httpx.AsyncClient.post", post):
        result = await send_dingtalk_text(
            VALID_WEBHOOK,
            "【客服工单催办提醒】\n处理人：@13800138000",
            at_mobiles=["13800138000"],
        )

    assert result.success is True
    post.assert_awaited_once_with(
        VALID_WEBHOOK,
        json={
            "msgtype": "text",
            "text": {"content": "【客服工单催办提醒】\n处理人：@13800138000"},
            "at": {"atMobiles": ["13800138000"], "isAtAll": False},
        },
    )


@pytest.mark.asyncio
async def test_send_dingtalk_text_handles_dingtalk_error():
    response = httpx.Response(
        200,
        json={"errcode": 310000, "errmsg": "keywords not in content"},
        request=httpx.Request("POST", VALID_WEBHOOK),
    )

    with patch(
        "app.services.notification.httpx.AsyncClient.post",
        AsyncMock(return_value=response),
    ):
        result = await send_dingtalk_text(VALID_WEBHOOK, "测试消息")

    assert result.success is False
    assert result.error_message == "keywords not in content"


@pytest.mark.asyncio
async def test_send_dingtalk_text_rejects_non_dingtalk_url():
    with patch("app.services.notification.httpx.AsyncClient.post", AsyncMock()) as post:
        result = await send_dingtalk_text("https://example.com/robot/send?token=x", "测试")

    assert result.success is False
    assert result.error_message == "钉钉 Webhook 地址无效"
    post.assert_not_awaited()
