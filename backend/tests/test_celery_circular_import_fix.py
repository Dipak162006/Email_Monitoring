import os
import subprocess
import sys
from pathlib import Path
import pytest

from app.workers.celery_app import celery_app
from app.workers.campaign_tasks import (
    dispatch_campaign_task,
    retry_campaign_delivery_task,
    scheduled_campaign_dispatch_task,
)
from app.modules.campaigns.dispatch_service import CampaignDispatchService
from app.modules.campaigns.delivery_service import CampaignDeliveryService


BACKEND_DIR = Path(__file__).resolve().parent.parent


def _run_fresh_python(code: str) -> subprocess.CompletedProcess:
    """Run Python code in a fresh, independent process without an existing sys.modules cache."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND_DIR)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


class TestCeleryCircularImportFix:
    """Regression tests verifying resolution of the circular import across Celery, worker tasks, and campaign services."""

    def test_fresh_process_import_workers_package(self):
        """app.workers package must import in a fresh Python process without circular import error."""
        proc = _run_fresh_python("import app.workers")
        assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    def test_fresh_process_import_celery_app(self):
        """app.workers.celery_app must import in a fresh Python process without circular import error."""
        proc = _run_fresh_python("from app.workers.celery_app import celery_app")
        assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    def test_fresh_process_import_campaign_tasks(self):
        """app.workers.campaign_tasks must import in a fresh Python process without circular import error."""
        proc = _run_fresh_python("import app.workers.campaign_tasks")
        assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    def test_fresh_process_import_delivery_service(self):
        """app.modules.campaigns.delivery_service must import in a fresh Python process without importing worker tasks."""
        proc = _run_fresh_python(
            "import sys\n"
            "from app.modules.campaigns.delivery_service import CampaignDeliveryService\n"
            "assert 'app.workers.campaign_tasks' not in sys.modules, 'campaign_tasks should not be eagerly imported'\n"
        )
        assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    def test_fresh_process_import_dispatch_service(self):
        """app.modules.campaigns.dispatch_service must import in a fresh Python process without circular import error."""
        proc = _run_fresh_python("from app.modules.campaigns.dispatch_service import CampaignDispatchService")
        assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    def test_fresh_process_import_campaigns_package_getattr(self):
        """Lazy __getattr__ in app.modules.campaigns correctly resolves CampaignDispatchService on demand."""
        proc = _run_fresh_python(
            "from app.modules.campaigns import CampaignDispatchService, CampaignDeliveryService\n"
            "assert CampaignDispatchService is not None\n"
            "assert CampaignDeliveryService is not None\n"
        )
        assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    def test_fresh_process_import_workers_package_getattr(self):
        """Lazy __getattr__ in app.workers correctly resolves dispatch_campaign_task on demand."""
        proc = _run_fresh_python(
            "from app.workers import dispatch_campaign_task, celery_app\n"
            "assert dispatch_campaign_task is not None\n"
            "assert celery_app is not None\n"
        )
        assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    def test_celery_application_registers_campaign_tasks(self):
        """Celery application loaders register dispatch_campaign_task and related campaign tasks."""
        celery_app.loader.import_default_modules()
        assert "app.workers.campaign_tasks.dispatch_campaign_task" in celery_app.tasks
        assert "app.workers.campaign_tasks.retry_campaign_delivery_task" in celery_app.tasks
        assert "app.workers.campaign_tasks.scheduled_campaign_dispatch_task" in celery_app.tasks

    def test_celery_task_names_and_signatures(self):
        """Preserve existing Celery task names and configuration."""
        assert dispatch_campaign_task.name == "app.workers.campaign_tasks.dispatch_campaign_task"
        assert retry_campaign_delivery_task.name == "app.workers.campaign_tasks.retry_campaign_delivery_task"
        assert scheduled_campaign_dispatch_task.name == "app.workers.campaign_tasks.scheduled_campaign_dispatch_task"

    def test_celery_beat_schedule_preserves_campaign_scheduler(self):
        """Celery Beat schedule contains scheduled campaign dispatch periodic task."""
        assert "scheduled-campaign-dispatch-periodic" in celery_app.conf.beat_schedule
        entry = celery_app.conf.beat_schedule["scheduled-campaign-dispatch-periodic"]
        assert entry["task"] == "app.workers.campaign_tasks.scheduled_campaign_dispatch_task"
