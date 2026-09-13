"""附件上传与鉴权下载测试。"""

from pathlib import Path

from app.core.config import settings
from app.models.ticket import TicketAttachment
from helpers import run_steps

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"poc-evidence" * 10


def _file(name: str = "现场照片.png", content: bytes = PNG_BYTES, mime: str = "image/png"):
    return {"files": (name, content, mime)}


async def _upload(api, ticket_id: int, *, files=None, stage: str | None = None):
    data = {"stage": stage} if stage is not None else None
    return await api.c.post(
        f"/api/v1/tickets/{ticket_id}/attachments",
        files=files or _file(),
        data=data,
    )


async def test_creator_uploads_on_draft_and_downloads(api):
    api.as_("presales01")
    draft_id = (await api.create_ticket(draft=True)).json()["data"]["id"]

    resp = await _upload(api, draft_id)
    assert resp.status_code == 201, resp.text
    attachment = resp.json()["data"][0]
    assert attachment["stage"] == "pending_approval"  # 与上传时工单状态一致
    assert attachment["original_filename"] == "现场照片.png"
    assert attachment["uploader_id"] == api.uid("presales01")
    assert attachment["download_url"] == f"/api/v1/attachments/{attachment['id']}/download"
    assert attachment["size"] == len(PNG_BYTES)

    # 真实磁盘文件名被随机化，原始名只作为元数据
    stored = list((Path(settings.UPLOAD_DIR) / "tickets" / str(draft_id)).iterdir())
    assert len(stored) == 1
    assert stored[0].name != "现场照片.png"

    download = await api.c.get(attachment["download_url"])
    assert download.status_code == 200, download.text
    assert download.content == PNG_BYTES

    # 详情里带上鉴权下载地址
    detail = await api.detail(draft_id)
    assert detail["attachments"][0]["download_url"] == attachment["download_url"]

    # 提交后附件仍然可下载
    await api.c.post(f"/api/v1/tickets/drafts/{draft_id}/submit")
    assert (await api.c.get(attachment["download_url"])).status_code == 200


async def test_download_respects_ticket_scope(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 2)  # planning：已流转到系统总体

    api.as_("presales01")
    uploaded = await _upload(api, ticket_id)
    assert uploaded.status_code == 201, uploaded.text
    url = uploaded.json()["data"][0]["download_url"]

    # 同分系统同事可见可下载
    api.as_("subsystem06")
    assert (await api.c.get(url)).status_code == 200

    # 其他分系统、未指定批准人、其他售前一律 403
    for wrong in ("subsystem02", "approver02", "presales02"):
        api.as_(wrong)
        resp = await api.c.get(url)
        assert resp.status_code == 403, f"{wrong} 不应能下载：{resp.status_code}"

    # 质量与管理员可下载
    api.as_("quality01")
    assert (await api.c.get(url)).status_code == 200


async def test_upload_requires_node_permission(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]

    # 质量在待审批阶段不是当前责任人
    api.as_("quality01")
    resp = await _upload(api, ticket_id)
    assert resp.status_code == 403, resp.text

    # 无关售前连查看都做不到
    api.as_("presales02")
    resp = await _upload(api, ticket_id)
    assert resp.status_code == 403, resp.text


async def test_non_presales_cannot_upload_even_at_responsible_stage(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 5)  # pending_quality_review

    api.as_("quality01")
    resp = await _upload(
        api, ticket_id, files=_file("评审记录.pdf", b"%PDF-1.4 review", "application/pdf")
    )
    assert resp.status_code == 403, resp.text
    assert "售前" in resp.text


async def test_terminal_ticket_rejects_upload(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 7)  # closed

    api.as_("quality01")
    resp = await _upload(api, ticket_id)
    assert resp.status_code == 403, resp.text


async def test_upload_rejects_unsupported_extension(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    resp = await _upload(api, ticket_id, files=_file("恶意.exe", b"MZ", "application/octet-stream"))
    assert resp.status_code == 422, resp.text
    assert "不支持的文件类型" in resp.text


async def test_upload_rejects_mime_mismatch(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    resp = await _upload(api, ticket_id, files=_file("报告.pdf", b"%PDF-1.4", "image/png"))
    assert resp.status_code == 422, resp.text
    assert "MIME" in resp.text


async def test_upload_rejects_oversize(api, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_SIZE", 16)
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    resp = await _upload(api, ticket_id, files=_file("大文件.zip", b"0" * 64, "application/zip"))
    assert resp.status_code == 413, resp.text


async def test_upload_rejects_stage_mismatch(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    resp = await _upload(api, ticket_id, stage="processing")
    assert resp.status_code == 422, resp.text
    assert "stage" in resp.text


async def test_multiple_files_in_one_request(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    resp = await api.c.post(
        f"/api/v1/tickets/{ticket_id}/attachments",
        files=[
            ("files", ("照片.png", PNG_BYTES, "image/png")),
            ("files", ("日志.log", b"2026-09-01 ERROR timeout\n", "text/plain")),
        ],
    )
    assert resp.status_code == 201, resp.text
    names = sorted(item["original_filename"] for item in resp.json()["data"])
    assert names == ["日志.log", "照片.png"]


async def test_legacy_attachment_is_admin_only(api):
    """历史客服附件没有工单归属，仅管理员可下载。"""
    legacy_dir = Path(settings.UPLOAD_DIR) / "legacy"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "old.png").write_bytes(PNG_BYTES)

    async with api.session() as s:
        record = TicketAttachment(
            ticket_id=None,
            filename="old.png",
            original_filename="旧客服附件.png",
            content_type="image/png",
            size=len(PNG_BYTES),
            storage_path="legacy/old.png",
            stage=None,
            uploader_id=None,
        )
        s.add(record)
        await s.commit()
        attachment_id = record.id

    api.as_("presales01")
    assert (await api.c.get(f"/api/v1/attachments/{attachment_id}/download")).status_code == 403

    api.as_("admin")
    resp = await api.c.get(f"/api/v1/attachments/{attachment_id}/download")
    assert resp.status_code == 200, resp.text
    assert resp.content == PNG_BYTES


async def test_missing_attachment_returns_404(api):
    api.as_("presales01")
    resp = await api.c.get("/api/v1/attachments/999999/download")
    assert resp.status_code == 404
