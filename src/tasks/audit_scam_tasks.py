"""Celery: Ordner-Audit Identitäts-KI Golden-Set-Benchmark."""
from __future__ import annotations

import importlib
import logging

from src.celery_app import celery_app
from src.helpers.database import get_session_factory
from src.services.audit_scam_llm_config import resolve_audit_scam_llm_config

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.audit_scam.run_golden_benchmark",
    soft_time_limit=3600,
    time_limit=3900,
)
def run_golden_benchmark_task(self, user_id: int) -> dict:
    """Führt Hybrid-Golden-Set mit gespeicherten User-Audit-LLM-Einstellungen aus."""
    models = importlib.import_module(".02_models", "src")
    SessionFactory = get_session_factory()
    with SessionFactory() as db:
        user = db.query(models.User).filter_by(id=user_id).first()
        if not user:
            raise ValueError("User nicht gefunden")
        cfg = resolve_audit_scam_llm_config(user)

    self.update_state(state="PROGRESS", meta={"status": "running", "progress": 0})
    logger.info(
        "Audit golden benchmark user=%s model=%s provider=%s",
        user_id,
        cfg.model,
        cfg.provider,
    )
    from src.services.audit_scam_benchmark import run_golden_hybrid_benchmark

    result = run_golden_hybrid_benchmark(cfg)
    result["status"] = "completed"
    return result
