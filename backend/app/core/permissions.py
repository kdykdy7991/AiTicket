"""Capability grants: the single source of truth for role-additive permissions.

A user keeps exactly one ``role`` (which decides which business actions they
may perform) plus any number of grants:

* read-scope grants widen what the user may read, one data domain each;
* feature-entry grants (``assistant_access``) unlock a specific endpoint.

``observer`` is deliberately NOT a grant: it is a role that also forbids
writes, so feature-entry grants never apply to observers.

``global_read`` used to be a selectable "all read domains" bundle. It is no
longer assignable from user management; legacy rows, the env whitelist and
older clients are expanded into every read domain so existing accounts keep
exactly the same access.
"""

import re
from datetime import datetime, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.grant import UserGrant

# ── Keys ────────────────────────────────────────────────────────────────
ASSISTANT_ACCESS = "assistant_access"

TICKETS_READ_ALL = "tickets_read_all"
REPORTS_READ = "reports_read"
VISIT_READ = "visit_read"
KNOWLEDGE_READ = "knowledge_read"
ORG_READ = "org_read"

READ_GRANT_KEYS: frozenset[str] = frozenset({
    TICKETS_READ_ALL, REPORTS_READ, VISIT_READ, KNOWLEDGE_READ, ORG_READ,
})

# Compatibility-only key. Not in GRANT_KEYS and not shown in the UI.
LEGACY_GLOBAL_READ = "global_read"
_LEGACY_EXPANSIONS: dict[str, frozenset[str]] = {LEGACY_GLOBAL_READ: READ_GRANT_KEYS}

# Only known grants can be assigned through user management.
GRANT_KEYS: frozenset[str] = READ_GRANT_KEYS | frozenset({ASSISTANT_ACCESS})

# Single source of truth for labels and descriptions shown in user management.
GRANT_DEFINITIONS: list[dict] = [
    {
        "key": TICKETS_READ_ALL, "label": "全量工单", "kind": "read",
        "description": "列表 / 导出可看全量，不含草稿",
        "includes": [],
    },
    {
        "key": REPORTS_READ, "label": "统计报表", "kind": "read",
        "description": "统计、趋势与线索分析",
        "includes": [],
    },
    {
        "key": VISIT_READ, "label": "来访记录", "kind": "read",
        "description": "列表与 CSV 导出",
        "includes": [],
    },
    {
        "key": KNOWLEDGE_READ, "label": "知识库", "kind": "read",
        "description": "文档、资产与检索",
        "includes": [],
    },
    {
        "key": ORG_READ, "label": "组织与配置", "kind": "read",
        "description": "跨组用户、SLA 与管理页只读",
        "includes": [],
    },
    {
        "key": ASSISTANT_ACCESS, "label": "智能助手", "kind": "feature",
        "description": "单独授权，不随只读开启",
        "includes": [],
    },
]

GRANT_LABELS: dict[str, str] = {d["key"]: d["label"] for d in GRANT_DEFINITIONS}

# ── Explicit endpoint declarations ──────────────────────────────────────
# Patterns are matched with re.fullmatch. Every read endpoint that a grant can
# unlock must be listed here; adding a new endpoint no longer silently grants
# it to every read-scope holder.
READ_GRANT_ENDPOINTS: dict[str, tuple[tuple[str, str], ...]] = {
    REPORTS_READ: (
        ("GET", r"/api/v1/stats/dashboard"),
        ("GET", r"/api/v1/stats/report"),
        ("GET", r"/api/v1/stats/trend"),
        ("GET", r"/api/v1/stats/service-analysis"),
        ("GET", r"/api/v1/stats/opportunity-analysis"),
    ),
    VISIT_READ: (
        ("GET", r"/api/v1/visit-records"),
        ("GET", r"/api/v1/visit-records/export"),
    ),
    KNOWLEDGE_READ: (
        ("GET", r"/api/v1/knowledge/status"),
        ("GET", r"/api/v1/knowledge/collections"),
        ("GET", r"/api/v1/knowledge/collections/[^/]+/documents"),
        ("POST", r"/api/v1/knowledge/collections/[^/]+/queries"),
        ("GET", r"/api/v1/knowledge/documents/[^/]+"),
        ("GET", r"/api/v1/knowledge/documents/[^/]+/chunks"),
        ("GET", r"/api/v1/knowledge/documents/[^/]+/chunks/[^/]+"),
        ("GET", r"/api/v1/knowledge/documents/[^/]+/presentation"),
        ("GET", r"/api/v1/knowledge/assets/[^/]+"),
    ),
    ORG_READ: (
        ("GET", r"/api/v1/sla-policies"),
    ),
    # Ticket list/export are already reachable via get_current_user; this
    # domain only widens their SQL WHERE clause (see tickets.py).
    TICKETS_READ_ALL: (),
}

FEATURE_GRANTS: dict[str, frozenset[tuple[str, str]]] = {
    ASSISTANT_ACCESS: frozenset({("POST", "/api/v1/agent/embed/code")}),
}

# Drafts are agent-only data, never exposed by a read grant.
_EXCLUDED_READ_PATHS = {"/api/v1/tickets/drafts"}
_KNOWLEDGE_QUERY_PATH = re.compile(r"/api/v1/knowledge/collections/[^/]+/queries")


def _env_global_read_ids() -> set[str]:
    return {value.strip() for value in settings.EXTRA_OBSERVER_USER_IDS.split(",") if value.strip()}


def env_grant_keys(user_id: int) -> set[str]:
    """Legacy env whitelist now expands straight into all read domains."""
    return set(READ_GRANT_KEYS) if str(user_id) in _env_global_read_ids() else set()


def effective_grants(user) -> set[str]:
    """Active grants of a user, with legacy bundle keys expanded.

    The legacy env whitelist only applies while a user has no grant history at
    all. Once user management saves grants (including a revocation), the DB is
    the single source of truth.
    """
    grants = set(getattr(user, "_effective_grants", ()) or ())
    if not getattr(user, "_has_grant_history", False):
        grants |= env_grant_keys(getattr(user, "id", 0))
    for legacy, members in _LEGACY_EXPANSIONS.items():
        if legacy in grants:
            grants |= members
            grants.discard(legacy)
    return grants


def has_grant(user, grant_key: str) -> bool:
    """Works with ORM users and the lightweight fake users used in tests."""
    return grant_key in effective_grants(user)


def has_full_read(user) -> bool:
    """Whether the user holds every read domain (the old bundle equivalent)."""
    return READ_GRANT_KEYS <= effective_grants(user)


def full_read_allowed(user, method: str, path: str) -> bool:
    """Legacy broad read behaviour for users holding every read domain.

    Keeps the previous "any GET except drafts, plus the knowledge query POST"
    behaviour for accounts that used to have the global_read bundle. Users with
    only some domains go through :func:`read_grant_allowed` instead.
    """
    if not has_full_read(user):
        return False
    if method in {"GET", "HEAD", "OPTIONS"}:
        return path not in _EXCLUDED_READ_PATHS
    return method == "POST" and _KNOWLEDGE_QUERY_PATH.fullmatch(path) is not None


def read_grant_allowed(user, method: str, path: str, declared_keys=()) -> bool:
    """Whether a declared read domain unlocks this exact endpoint."""
    for key in declared_keys:
        for allowed_method, pattern in READ_GRANT_ENDPOINTS.get(key, ()):
            if allowed_method == method and re.fullmatch(pattern, path):
                if has_grant(user, key):
                    return True
    return False


def feature_access_allowed(user, method: str, path: str) -> bool:
    """Whether a feature-entry grant unlocks this exact endpoint.

    Observers keep their global read-only identity: a feature grant never
    overrides the observer write ban.
    """
    if getattr(user, "role", None) == "observer":
        return False
    return any(
        has_grant(user, key) and (method, path) in endpoints
        for key, endpoints in FEATURE_GRANTS.items()
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _active_window():
    now = _now()
    return (
        or_(UserGrant.effective_from.is_(None), UserGrant.effective_from <= now),
        or_(UserGrant.effective_to.is_(None), UserGrant.effective_to >= now),
    )


async def load_grants(db: AsyncSession, user) -> None:
    """Attach active grants to a user object for the current request."""
    rows = (await db.execute(
        select(UserGrant).where(UserGrant.user_id == user.id)
    )).scalars().all()
    user._has_grant_history = bool(rows)
    now = _now()
    user._effective_grants = {
        row.grant_key for row in rows
        if (row.effective_from is None or row.effective_from <= now)
        and (row.effective_to is None or row.effective_to >= now)
    }


async def grants_for_users(db: AsyncSession, user_ids: list[int]) -> dict[int, list[str]]:
    """Batch lookup for the user management list (avoids N+1).

    Legacy bundle rows are expanded so the admin form shows the individual
    domains that are actually in effect.
    """
    grants: dict[int, set[str]] = {uid: set() for uid in user_ids}
    if user_ids:
        history_ids = set((await db.execute(
            select(UserGrant.user_id).where(UserGrant.user_id.in_(user_ids)).distinct()
        )).scalars().all())
        for uid in user_ids:
            if uid not in history_ids:
                grants[uid] |= env_grant_keys(uid)
        from_window, to_window = _active_window()
        rows = await db.execute(
            select(UserGrant.user_id, UserGrant.grant_key).where(
                UserGrant.user_id.in_(user_ids), from_window, to_window
            )
        )
        for uid, key in rows.all():
            grants.setdefault(uid, set()).add(key)
    return {
        uid: sorted((keys - {LEGACY_GLOBAL_READ}) | set(READ_GRANT_KEYS)
                    if LEGACY_GLOBAL_READ in keys else keys)
        for uid, keys in grants.items()
    }


async def sync_user_grants(
    db: AsyncSession, user_id: int, desired: set[str], granted_by: int | None = None
) -> None:
    """Make the active grants equal ``desired`` while preserving history."""
    unknown = desired - GRANT_KEYS
    if unknown:
        raise ValueError("未知的额外权限：" + ", ".join(sorted(unknown)))

    from_window, to_window = _active_window()
    rows = await db.execute(
        select(UserGrant.grant_key).where(
            UserGrant.user_id == user_id, from_window, to_window
        )
    )
    current = set(rows.scalars().all())

    revoked = current - desired
    if revoked:
        await db.execute(
            update(UserGrant)
            .where(UserGrant.user_id == user_id, UserGrant.grant_key.in_(revoked), from_window, to_window)
            .values(effective_to=_now())
        )
    for key in sorted(desired - current):
        db.add(UserGrant(
            user_id=user_id, grant_key=key, granted_by=granted_by,
            effective_from=_now(),
        ))
    await db.flush()
