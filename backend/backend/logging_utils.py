"""
Logging utilities: request-id context, filters, formatters, middleware,
and a custom rotating file handler.

Log line format (no spaces around separators):
    <ISO-8601 time>::<LEVEL>::<request_id>::<app>::<module.func>::<message>

File layout (all rotated, kept up to N=10 files; index 0 = latest):
    logs/app/app0.txt      ... app9.txt
    logs/error/error0.txt  ... error9.txt
    logs/access/access0.txt... access9.txt
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from contextvars import ContextVar
from logging.handlers import BaseRotatingHandler
from typing import Optional

# URL-safe alphabet (nanoid default minus look-alikes kept simple)
_NANOID_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_NANOID_LEN = 6


def new_request_id() -> str:
    """Generate a short (6 chars) nanoid-style request id."""
    return "".join(secrets.choice(_NANOID_ALPHABET) for _ in range(_NANOID_LEN))


# ---------------------------------------------------------------------------
# Custom rotating handler: app0.txt (latest) ... appN.txt
# Rotates either when the current day rolls over (UTC) or when maxBytes
# is exceeded (set maxBytes=0 to disable size-based rotation).
# ---------------------------------------------------------------------------
class IndexedRotatingFileHandler(BaseRotatingHandler):
    """
    Files are named ``<stem><index><suffix>`` inside ``directory``.
    Index 0 is always the active/latest file; on rollover, file ``i`` is
    renamed to ``i+1`` and a fresh ``stem0suffix`` is opened. Files past
    ``backupCount-1`` are deleted.
    """

    def __init__(
        self,
        directory: str,
        stem: str,
        suffix: str = ".txt",
        backupCount: int = 10,
        maxBytes: int = 0,
        when_daily: bool = True,
        encoding: str = "utf-8",
        delay: bool = True,
    ):
        os.makedirs(directory, exist_ok=True)
        self.directory = directory
        self.stem = stem
        self.suffix = suffix
        self.backupCount = max(1, int(backupCount))
        self.maxBytes = int(maxBytes)
        self.when_daily = when_daily
        self._current_day = self._utc_day()
        active = os.path.join(directory, f"{stem}0{suffix}")
        super().__init__(active, mode="a", encoding=encoding, delay=delay)

    @staticmethod
    def _utc_day() -> int:
        return int(time.time() // 86400)

    def _path_for(self, index: int) -> str:
        return os.path.join(self.directory, f"{self.stem}{index}{self.suffix}")

    def shouldRollover(self, record: logging.LogRecord) -> bool:  # noqa: N802
        if self.when_daily and self._utc_day() != self._current_day:
            return True
        if self.maxBytes > 0:
            if self.stream is None:
                self.stream = self._open()
            try:
                self.stream.seek(0, 2)  # end
                if self.stream.tell() + len(self.format(record)) + 1 >= self.maxBytes:
                    return True
            except Exception:
                return False
        return False

    def doRollover(self) -> None:  # noqa: N802
        if self.stream:
            self.stream.close()
            self.stream = None

        # Drop the oldest if it exists.
        oldest = self._path_for(self.backupCount - 1)
        if os.path.exists(oldest):
            try:
                os.remove(oldest)
            except OSError:
                pass

        # Shift others up: i -> i+1, from highest down to 0.
        for i in range(self.backupCount - 2, -1, -1):
            src = self._path_for(i)
            dst = self._path_for(i + 1)
            if os.path.exists(src):
                if os.path.exists(dst):
                    try:
                        os.remove(dst)
                    except OSError:
                        pass
                try:
                    os.rename(src, dst)
                except OSError:
                    pass

        self._current_day = self._utc_day()
        if not self.delay:
            self.stream = self._open()


# ---------------------------------------------------------------------------
# Request-scoped context (safe for sync + async views, threads & ASGI tasks)
# ---------------------------------------------------------------------------
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the request id bound to the current context (or '-')."""
    return _request_id_ctx.get()


def set_request_id(request_id: Optional[str]) -> None:
    _request_id_ctx.set(request_id or "-")


# ---------------------------------------------------------------------------
# Logging filters
# ---------------------------------------------------------------------------
class RequestIDFilter(logging.Filter):
    """Inject the current request id into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        record.request_id = getattr(record, "request_id", None) or get_request_id()
        return True


class AppNameFilter(logging.Filter):
    """Inject a short app/component name derived from the logger name."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        # logger name like "core.views" -> app = "core"
        name = record.name or "root"
        record.app = name.split(".", 1)[0] if name != "root" else "root"
        # method name = "<module>.<funcName>" for fast traceability
        record.method = f"{record.module}.{record.funcName}"
        # Defaults so formatters that reference these never crash.
        if not hasattr(record, "client_ip"):
            record.client_ip = "-"
        if not hasattr(record, "user_agent"):
            record.user_agent = "-"
        return True


# ---------------------------------------------------------------------------
# Request / access log middleware
# ---------------------------------------------------------------------------
_access_logger = logging.getLogger("access")


class RequestLoggingMiddleware:
    """
    * Generates / propagates an X-Request-ID header.
    * Binds the request id to the logging context for the whole request.
    * Writes one structured access log line per request.
    """

    HEADER = "HTTP_X_REQUEST_ID"
    RESPONSE_HEADER = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get(self.HEADER, "").strip()
        rid = incoming or new_request_id()
        set_request_id(rid)
        request.request_id = rid

        start = time.perf_counter()
        try:
            response = self.get_response(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            _access_logger.exception(
                "%s %s -> 500 in %.2fms",
                request.method,
                request.get_full_path(),
                duration_ms,
                extra={
                    "client_ip": _client_ip(request),
                    "user_agent": request.META.get("HTTP_USER_AGENT", "-"),
                },
            )
            set_request_id("-")
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response[self.RESPONSE_HEADER] = rid

        level = logging.WARNING if response.status_code >= 500 else (
            logging.INFO if response.status_code < 400 else logging.WARNING
        )
        _access_logger.log(
            level,
            "%s %s -> %d in %.2fms",
            request.method,
            request.get_full_path(),
            response.status_code,
            duration_ms,
            extra={
                "client_ip": _client_ip(request),
                "user_agent": request.META.get("HTTP_USER_AGENT", "-"),
            },
        )
        set_request_id("-")
        return response


def _client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "-")
