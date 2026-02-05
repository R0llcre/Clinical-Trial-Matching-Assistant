import logging
import os
import time

from tasks import sync_trials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    condition = os.getenv("SYNC_CONDITION", "cancer")
    status = os.getenv("SYNC_STATUS")
    page_limit = _env_int("SYNC_PAGE_LIMIT", 1)
    page_size = _env_int("SYNC_PAGE_SIZE", 100)
    interval_seconds = _env_int("SYNC_INTERVAL_SECONDS", 3600)
    failure_retry_seconds = _env_int("SYNC_FAILURE_RETRY_SECONDS", 30)
    run_once = _env_bool("SYNC_RUN_ONCE", False)

    logger.info(
        (
            "worker started condition=%s status=%s page_limit=%s page_size=%s "
            "run_once=%s"
        ),
        condition,
        status,
        page_limit,
        page_size,
        run_once,
    )

    while True:
        try:
            stats = sync_trials(
                condition=condition,
                status=status,
                page_limit=page_limit,
                page_size=page_size,
            )
            logger.info(
                "sync run completed run_id=%s processed=%s inserted=%s updated=%s",
                stats.run_id,
                stats.processed,
                stats.inserted,
                stats.updated,
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
