"""Celery application.

With REDIS_URL set, run real workers:
    celery -A app.automation.celery_app worker --loglevel=info
    celery -A app.automation.celery_app beat --loglevel=info

Without Redis (local dev), tasks execute inline (eager mode) so the app still works.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "weta_crm",
    broker=settings.redis_url or "memory://",
    include=["app.automation.tasks"],
)

celery_app.conf.update(
    task_always_eager=not settings.redis_url,
    task_eager_propagates=False,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
)

celery_app.conf.beat_schedule = {
    "meeting-reminders-every-5-min": {
        "task": "app.automation.tasks.send_meeting_reminders",
        "schedule": 300.0,
    },
    "mark-overdue-invoices-daily": {
        "task": "app.automation.tasks.mark_overdue_invoices",
        "schedule": crontab(hour=1, minute=0),
    },
    "daily-summary-report": {
        "task": "app.automation.tasks.send_daily_summary",
        "schedule": crontab(hour=3, minute=0),
    },
    "weekly-summary-report": {
        "task": "app.automation.tasks.send_weekly_summary",
        "schedule": crontab(hour=3, minute=30, day_of_week=1),
    },
    # Statuses first, so the reminder job sees the freshly-derived ones.
    "refresh-policy-statuses-daily": {
        "task": "app.automation.tasks.refresh_policy_statuses",
        "schedule": crontab(hour=0, minute=30),
    },
    "create-renewal-tasks-daily": {
        "task": "app.automation.tasks.create_renewal_tasks",
        "schedule": crontab(hour=0, minute=45),
    },
    "reindex-search-nightly": {
        "task": "app.automation.tasks.reindex_search",
        "schedule": crontab(hour=2, minute=0),
    },
}
