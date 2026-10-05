"""Celery-Tasks unter src/tasks/ müssen im Worker registriert sein.

Worker-Start lädt src.tasks (__init__.py-Exports), nicht jedes Modul per Autodiscover.
Neue *\_tasks.py mit @celery_app.task → Import in src/tasks/__init__.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.celery_app import celery_app


def _tasks_package_dir() -> Path:
    import src.tasks as tasks_pkg

    return Path(tasks_pkg.__path__[0])


def test_task_modules_with_celery_decorator_imported_from_tasks_init():
    import src.tasks  # noqa: F401 — wie Celery-Worker nach import_default_modules

    tasks_dir = _tasks_package_dir()
    missing = []
    for path in sorted(tasks_dir.glob("*_tasks.py")):
        text = path.read_text(encoding="utf-8")
        if "celery_app.task" not in text:
            continue
        mod_name = f"src.tasks.{path.stem}"
        if mod_name not in sys.modules:
            missing.append(mod_name)
    assert not missing, (
        "Diese Task-Module sind nicht über src.tasks.__init__ geladen "
        "(Worker: unregistered task):\n" + "\n".join(missing)
    )


def test_exported_tasks_registered_on_celery_app():
    import src.tasks  # noqa: F401

    celery_app.loader.import_default_modules()

    from src.tasks import (
        retry_brand_health_rdap_task,
        run_brand_health_check_task,
        update_tranco_popularity_list,
    )

    for task in (
        update_tranco_popularity_list,
        retry_brand_health_rdap_task,
        run_brand_health_check_task,
    ):
        assert task.name in celery_app.tasks, task.name
