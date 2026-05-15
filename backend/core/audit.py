"""Audit logging helpers."""

from __future__ import annotations

from typing import Any

from .models import AuditLog


def _client_info(request):
    if request is None:
        return None, ""
    ip = (
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR")
    )
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:400]
    return ip, ua


def record(request, action: str, *, target: str = "", target_id: int | None = None, metadata: dict[str, Any] | None = None) -> None:
    """Persist an AuditLog entry. Best-effort — never raises into the caller."""
    try:
        ip, ua = _client_info(request)
        user = getattr(request, "user", None)
        AuditLog.objects.create(
            user=user if (user and user.is_authenticated) else None,
            action=action,
            target=target[:200],
            target_id=target_id,
            ip_address=ip,
            user_agent=ua,
            metadata=metadata or {},
        )
    except Exception:
        # Audit logging must never break the request path.
        pass
