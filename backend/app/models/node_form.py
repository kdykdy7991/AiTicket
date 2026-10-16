"""Published node forms and immutable submission records."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, event, func, select
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import inspect

from app.core.database import Base


class FormDefinition(Base):
    __tablename__ = "form_definitions"
    __table_args__ = (UniqueConstraint("code", "version"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    node_type: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fields = relationship("FormFieldDefinition", lazy="selectin", order_by="FormFieldDefinition.sort_order")


class FormFieldDefinition(Base):
    __tablename__ = "form_field_definitions"
    __table_args__ = (UniqueConstraint("form_definition_id", "field_key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    form_definition_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("form_definitions.id", ondelete="RESTRICT"), nullable=False)
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    field_type: Mapped[str] = mapped_column(String(40), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    options: Mapped[list | None] = mapped_column(JSON)
    validation: Mapped[dict | None] = mapped_column(JSON)
    visibility_condition: Mapped[dict | None] = mapped_column(JSON)
    required_condition: Mapped[dict | None] = mapped_column(JSON)
    storage_type: Mapped[str] = mapped_column(String(30), nullable=False, default="submission")
    storage_key: Mapped[str | None] = mapped_column(String(100))


class FormBinding(Base):
    __tablename__ = "form_bindings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    node_type: Mapped[str] = mapped_column(String(40), nullable=False)
    department_code: Mapped[str | None] = mapped_column(String(100))
    category_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ticket_categories.id", ondelete="RESTRICT"))
    category_match_type: Mapped[str] = mapped_column(String(30), nullable=False, default="exact")
    form_definition_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("form_definitions.id", ondelete="RESTRICT"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    form = relationship("FormDefinition", lazy="selectin")


class TicketNodeSubmission(Base):
    __tablename__ = "ticket_node_submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    node_type: Mapped[str] = mapped_column(String(40), nullable=False)
    form_definition_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("form_definitions.id", ondelete="RESTRICT"), nullable=False)
    form_version: Mapped[int] = mapped_column(Integer, nullable=False)
    department_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("skill_groups.id", ondelete="SET NULL"))
    operator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    field_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    state_log_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ticket_state_logs.id", ondelete="SET NULL"))
    article_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("articles.id", ondelete="RESTRICT"))


@event.listens_for(FormDefinition, "before_update")
@event.listens_for(FormDefinition, "before_delete")
def _protect_published_form(_mapper, connection, target) -> None:
    previously_published = connection.execute(
        select(FormDefinition.published_at).where(FormDefinition.id == target.id)
    ).scalar_one_or_none()
    changed = {name for name in ("code", "name", "node_type", "version", "enabled", "published_at")
               if inspect(target).attrs[name].history.has_changes()}
    first_publication = previously_published is None and changed == {"published_at"} and target.published_at is not None
    if previously_published is not None or (target.published_at is not None and not first_publication):
        raise ValueError("已发布表单版本不可原地修改或删除；请创建新版本")


@event.listens_for(FormFieldDefinition, "before_insert")
@event.listens_for(FormFieldDefinition, "before_update")
@event.listens_for(FormFieldDefinition, "before_delete")
def _protect_published_field(_mapper, connection, target) -> None:
    published = connection.execute(
        select(FormDefinition.published_at).where(FormDefinition.id == target.form_definition_id)
    ).scalar_one_or_none()
    if published is not None:
        raise ValueError("已发布表单字段不可原地修改或删除；请创建新版本")
