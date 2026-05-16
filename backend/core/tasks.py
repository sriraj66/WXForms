"""Lightweight background-task helpers.

We intentionally avoid Celery / django-q for the MVP and run jobs in
short-lived daemon threads. Each job opens its own DB connection and
closes it on exit so we don't leak.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from django.db import close_old_connections

logger = logging.getLogger(__name__)


def run_in_background(target: Callable, *args, **kwargs) -> threading.Thread:
    """Run ``target(*args, **kwargs)`` in a daemon thread.

    The thread closes any DB connection it opened on exit so we don't
    accumulate them. Exceptions are logged, never re-raised.
    """

    def _runner():
        try:
            target(*args, **kwargs)
        except Exception:
            logger.exception("Background task %s failed", getattr(target, "__name__", target))
        finally:
            close_old_connections()

    t = threading.Thread(target=_runner, daemon=True, name=f"bg-{getattr(target, '__name__', 'task')}")
    t.start()
    return t


def deliver_submission_email_async(submission_id: int) -> None:
    """Resolve all dependencies, then dispatch the email send in the background."""

    def _job(sub_id: int):
        from .email_utils import send_submission_email
        from .models import EmailLog, GmailConfig, Submission
        from plans.services import InsufficientCreditsError, charge_email_sent, get_or_create_balance

        try:
            submission = Submission.objects.select_related("form", "form__user", "email_log", "form__email_template").get(pk=sub_id)
        except Submission.DoesNotExist:
            logger.warning("deliver_submission_email_async: submission %s missing", sub_id)
            return

        # Either the row exists from the request handler or we create it now.
        email_log, _ = EmailLog.objects.get_or_create(submission=submission)
        owner = submission.form.user

        from misc.services import get_app_setting
        if not get_app_setting("email_service", True):
            email_log.mark_failed("Email service is globally disabled.")
            return

        try:
            gmail_config = GmailConfig.objects.get(user=owner, is_verified=True, is_enabled=True)
        except GmailConfig.DoesNotExist:
            email_log.mark_failed("Gmail not configured or not verified.")
            return

        # Per-form template wins, otherwise user default.
        from .models import EmailTemplate
        email_template = submission.form.email_template or EmailTemplate.objects.filter(
            user=owner, is_default=True
        ).first()

        # Pre-flight credit check.
        try:
            balance = get_or_create_balance(owner)
            if balance.balance < balance.plan.per_email_cost:
                email_log.mark_failed(
                    f"Insufficient credits (need {balance.plan.per_email_cost}, have {balance.balance})."
                )
                return
        except Exception as e:
            email_log.mark_failed(f"Balance check failed: {e}")
            return

        success, error = send_submission_email(submission, gmail_config, email_template)
        if success:
            email_log.mark_sent()
            try:
                charge_email_sent(owner, submission)
            except InsufficientCreditsError:
                # Email was already sent; record but don't roll back.
                logger.warning("Charge failed after send for submission %s", sub_id)
        else:
            email_log.mark_failed(error)

    run_in_background(_job, submission_id)


def retry_failed_email(submission_id: int) -> tuple[bool, str]:
    """Re-queue a single failed/pending email for delivery.

    Returns ``(queued, reason)``. ``queued`` is False if the submission has no
    email log, the log is already in a terminal "sent" state, or the
    submission was hard-purged. Safe to call from a request handler — the
    actual delivery happens in a background thread.
    """
    from .models import EmailLog, Submission

    try:
        submission = Submission.objects.select_related("email_log").get(pk=submission_id)
    except Submission.DoesNotExist:
        return False, "Submission not found."

    if submission.data_deleted:
        return False, "Submission data was deleted; cannot retry."

    log, _ = EmailLog.objects.get_or_create(submission=submission)
    if log.status == EmailLog.Status.SENT:
        return False, "Email already sent."

    log.mark_retrying()
    deliver_submission_email_async(submission.pk)
    return True, "Queued for retry."


def retry_failed_emails_bulk(submission_ids) -> int:
    """Retry every submission id whose email log is currently failed/pending.

    Returns the number of jobs actually queued. Submissions belonging to a
    different user must be filtered by the caller before invoking this.
    """
    from .models import EmailLog, Submission

    queued = 0
    qs = (
        Submission.objects
        .filter(pk__in=list(submission_ids), data_deleted=False)
        .select_related("email_log")
    )
    for sub in qs:
        log = getattr(sub, "email_log", None) or EmailLog.objects.create(submission=sub)
        if log.status == EmailLog.Status.SENT:
            continue
        log.mark_retrying()
        deliver_submission_email_async(sub.pk)
        queued += 1
    return queued
