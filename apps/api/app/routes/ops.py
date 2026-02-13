from fastapi import APIRouter

from app.services.observability import get_ops_metrics

router = APIRouter()


@router.get("/api/ops/metrics")
def ops_metrics() -> dict:
    return get_ops_metrics()
