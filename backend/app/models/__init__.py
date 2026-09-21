"""Import all models so SQLAlchemy can resolve relationships."""

from app.models.group import Group, SkillGroup, UserSkillGroup
from app.models.user import User
from app.models.category import TicketCategory, Region
from app.models.ticket import Ticket, Article, TicketStateLog, Reminder
from app.models.sla import SLAPolicy
from app.models.notification import DingtalkNotification
from app.models.audit import AuditLog
from app.models.routing import CategoryRoutingRule
from app.models.complaint import ComplaintEscalationPolicy

__all__ = [
    "Group", "SkillGroup", "UserSkillGroup",
    "User",
    "TicketCategory", "Region",
    "Ticket", "Article", "TicketStateLog", "Reminder",
    "SLAPolicy",
    "DingtalkNotification",
    "AuditLog",
    "CategoryRoutingRule",
]
