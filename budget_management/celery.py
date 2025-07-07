"""
Celery configuration for budget_management project.
"""
import os
from celery import Celery
from celery.schedules import crontab
from celery.app.task import Task
from typing import Dict, Any

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'budget_management.settings')

app = Celery('budget_management')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Beat Schedule
app.conf.beat_schedule = {
    'check-budgets-and-dayparting': {
        'task': 'campaigns.tasks.check_budgets_and_dayparting',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
        'options': {'expires': 60}  # Task expires after 1 minute
    },
    'daily-reset': {
        'task': 'campaigns.tasks.daily_reset_task',
        'schedule': crontab(hour=0, minute=0),  # Daily at midnight
        'options': {'expires': 60}
    },
    'monthly-reset': {
        'task': 'campaigns.tasks.monthly_reset_task',
        'schedule': crontab(hour=0, minute=0, day_of_month=1),  # Monthly on 1st day
        'options': {'expires': 60}
    },
    'cleanup-old-spends': {
        'task': 'campaigns.tasks.cleanup_old_spends',
        'schedule': crontab(hour=2, minute=0, day_of_week=1),  # Weekly on Monday at 2 AM
        'options': {'expires': 300}  # 5 minutes
    },
}

# Celery Configuration
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_routes={
        'campaigns.tasks.*': {'queue': 'campaigns'},
    },
)

@app.task(bind=True)
def debug_task(self: Task) -> str:
    """Debug task for testing Celery configuration."""
    return f'Request: {self.request!r}' 