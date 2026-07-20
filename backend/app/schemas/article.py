"""Pydantic schemas for articles."""

from datetime import datetime

from pydantic import BaseModel, Field


class AttachmentOut(BaseModel):
    id: int
    filename: str
    original_filename: str
    content_type: str
    size: int
    url: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ArticleCreate(BaseModel):
    type: str = Field(default="reply")  # reply / addition / reminder
    body: str = Field(..., min_length=1)
    append_reason: str | None = None  # required when type=addition


class ArticleOut(BaseModel):
    id: int
    ticket_id: int
    type: str
    sender_id: int
    sender_name: str | None = None
    subject: str | None = None
    body: str
    state_key: str | None = None
    append_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    attachments: list[AttachmentOut] = []

    model_config = {"from_attributes": True}
