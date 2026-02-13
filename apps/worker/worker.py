import logging
import os
import time

from tasks import sync_trials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("invalid int env %s=%s; using %s", name, raw, default)
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    raw_conditions = os.getenv("SYNC_CONDITION", "cancer")
    conditions = _split_csv(raw_conditions) or ["cancer"]
    status = os.getenv("SYNC_STATUS")
    page_limit = _env_int("SYNC_PAGE_LIMIT", 1)
    page_size = _env_int("SYNC_PAGE_SIZE", 100)
    interval_seconds = _env_int("SYNC_INTERVAL_SECONDS", 3600)
    failure_retry_seconds = _env_int("SYNC_FAILURE_RETRY_SECONDS", 30)
    run_once = _env_bool("SYNC_RUN_ONCE", False)

    logger.info(
        (
            "worker started conditions=%s status=%s page_limit=%s page_size=%s "
            "run_once=%s"
        ),
        ",".join(conditions),
        status,
        page_limit,
        page_size,
        run_once,
    )

    condition_index = 0
    while True:
        condition = conditions[condition_index % len(conditions)]
        condition_index += 1
        try:
            stats = sync_trials(
                condition=condition,
                status=status,
                page_limit=page_limit,
                page_size=page_size,
            )
            logger.info(
                (
                    "sync run completed run_id=%s processed=%s inserted=%s updated=%s "
                    "pruned_trials=%s pruned_criteria=%s "
                    "parse_success=%s parse_failed=%s parse_success_rate=%s "
                    "parser_version=%s parser_source_breakdown=%s "
                    "fallback_reason_breakdown=%s llm_budget_exceeded_count=%s "
                    "backfill_selected=%s selective_llm_triggered=%s selective_llm_skipped=%s"
                ),
                stats.run_id,
                stats.processed,
                stats.inserted,
                stats.updated,
                stats.pruned_trials,
                stats.pruned_criteria,
                stats.parse_success,
                stats.parse_failed,
                stats.parse_success_rate,
                stats.parser_version,
                stats.parser_source_breakdown,
                stats.fallback_reason_breakdown,
                stats.llm_budget_exceeded_count,
                stats.backfill_selected,
                stats.selective_llm_triggered,
                stats.selective_llm_skipped_breakdown,
            )
        except Exception:
            logger.exception("sync run failed")
            if run_once:
                break
            time.sleep(failure_retry_seconds)
            continue

        if run_once:
            break

        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
