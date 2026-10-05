"""Marken-Domain-Health: Celery (lange RDAP-Läufe)."""

from __future__ import annotations

import logging

from src.celery_app import celery_app
from src.helpers.database import get_db_session
from src.services.brand_domain_health import apply_brand_health_rdap_followup
from src.services.brand_health_check_lock import release_brand_health_check_lock
from src.services.brand_health_check_service import run_brand_health_check_for_user
from src.services.domain_reputation import (
    brand_health_rdap_auto_followup,
    brand_health_rdap_followup_chunk_size,
    brand_health_rdap_followup_cooldown_seconds,
)

logger = logging.getLogger(__name__)

_HEALTH_CHECK_SOFT = 1200
_HEALTH_CHECK_HARD = 1500


@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=_HEALTH_CHECK_SOFT,
    time_limit=_HEALTH_CHECK_HARD,
)
def run_brand_health_check_task(self, user_id: int, brand_map: dict, check_options: dict | None = None):
    if not brand_map:
        brand_map = {}
    opts = check_options if isinstance(check_options, dict) else {}
    try:
        self.update_state(
            state="PROGRESS",
            meta={"status": "running", "message": "Domain-Prüfung läuft…"},
        )
        result = run_brand_health_check_for_user(
            user_id,
            brand_map,
            force_recheck=bool(opts.get("force_recheck")),
            recheck_domains=opts.get("recheck_domains"),
            include_rdap=bool(opts.get("brand_health_rdap", False)),
        )
        if not result.get("ok"):
            return result
        pending = list(result.pop("rdap_pending", None) or [])
        checks = result.get("checks_performed") or {}
        rdap_on = bool(checks.get("rdap_brand_health"))
        if (
            pending
            and rdap_on
            and brand_health_rdap_auto_followup()
            and not (result.get("settings") or {}).get("health", {}).get("aborted")
        ):
            try:
                from src.helpers.task_ownership import track_celery_task

                chunk = brand_health_rdap_followup_chunk_size()
                first = pending[:chunk]
                rest = pending[chunk:]
                async_result = retry_brand_health_rdap_task.delay(user_id, first)
                track_celery_task(async_result, user_id)
                if rest:
                    cooldown = brand_health_rdap_followup_cooldown_seconds()
                    chained = retry_brand_health_rdap_task.apply_async(
                        args=[user_id, rest],
                        countdown=cooldown,
                    )
                    track_celery_task(chained, user_id)
                settings = result.get("settings") or {}
                health = settings.get("health")
                if isinstance(health, dict):
                    health["rdap_followup_enqueued"] = True
                    if rest:
                        health["rdap_followup_queued"] = len(rest)
            except Exception as exc:
                logger.exception("RDAP followup enqueue failed: %s", exc)
                warnings = list(result.get("warnings") or [])
                warnings.append(
                    "RDAP-Nachzug konnte nicht gestartet werden (Celery/Redis)."
                )
                result["warnings"] = warnings
                settings = result.get("settings") or {}
                health = settings.get("health")
                if isinstance(health, dict):
                    health["rdap_followup_enqueued"] = False
        return result
    except Exception as exc:
        logger.exception("brand health check task failed user=%s: %s", user_id, exc)
        return {"ok": False, "error": "Domain-Prüfung fehlgeschlagen (Serverfehler)."}
    finally:
        release_brand_health_check_lock(user_id)


@celery_app.task(bind=True, max_retries=0)
def retry_brand_health_rdap_task(self, user_id: int, domains: list):
    if not domains:
        return {"ok": True, "updated": 0}
    from src.helpers.database import _get_models

    models = _get_models()
    chunk_size = brand_health_rdap_followup_chunk_size()
    batch = list(domains[:chunk_size])
    rest = list(domains[chunk_size:])
    with get_db_session() as db:
        result = apply_brand_health_rdap_followup(
            user_id,
            batch,
            db_session=db,
            models=models,
        )
    if rest and bool((result or {}).get("checks_performed", {}).get("rdap_brand_health")):
        from src.helpers.task_ownership import track_celery_task

        cooldown = brand_health_rdap_followup_cooldown_seconds()
        chained = retry_brand_health_rdap_task.apply_async(
            args=[user_id, rest],
            countdown=cooldown,
        )
        track_celery_task(chained, user_id)
        result["remaining_queued"] = len(rest)
    logger.info("brand health RDAP followup user=%s: %s", user_id, result)
    return result
