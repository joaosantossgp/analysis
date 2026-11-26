from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from apps.api.app.dependencies import ensure_api_ready, get_read_service, get_settings
from apps.api.app.presenters import (
    HealthSnapshotPayload,
    RefreshStatusPayload,
    present_health_snapshot,
    present_refresh_status,
)
from src.financials.read_service import CVMReadService

router = APIRouter(tags=["operations"])


@router.get(
    "/refresh-status",
    response_model=list[RefreshStatusPayload],
    summary="Lista o status operacional do refresh por empresa.",
)
def get_refresh_status(
    request: Request,
    cd_cvm: int | None = Query(default=None, description="Filtra por codigo CVM."),
    service: CVMReadService = Depends(get_read_service),
) -> list[RefreshStatusPayload]:
    ensure_api_ready(get_settings(request))
    return present_refresh_status(service.list_refresh_status(cd_cvm=cd_cvm))


@router.get(
    "/base-health",
    response_model=HealthSnapshotPayload,
    summary="Retorna o snapshot de saude e cobertura da base.",
)
def get_base_health(
    request: Request,
    start_year: int = Query(..., description="Ano inicial da janela analisada."),
    end_year: int = Query(..., description="Ano final da janela analisada."),
    force_refresh: bool = Query(default=False, description="Ignora cache local de health."),
    service: CVMReadService = Depends(get_read_service),
) -> HealthSnapshotPayload:
    ensure_api_ready(get_settings(request))
    try:
        snapshot = service.get_health_snapshot(
            start_year=start_year,
            end_year=end_year,
            force_refresh=force_refresh,
        )
    except ValueError as exc:
        from apps.api.app.dependencies import InvalidRequestError

        raise InvalidRequestError(str(exc)) from exc
    return present_health_snapshot(snapshot)


@router.get(
    "/local-database-state",
    summary="Returns the local database state shown by the app shell.",
)
def get_local_database_state(request: Request) -> dict:
    from datetime import datetime, timezone

    from src.platform.db import build_engine
    from src.refresh.local_database_state import (
        derive_local_database_state,
        read_local_database_facts,
    )

    settings = get_settings(request)
    ensure_api_ready(settings)
    engine = build_engine(settings)
    try:
        has_statements, failures = read_local_database_facts(engine)
    finally:
        engine.dispose()
    manager = getattr(request.app.state, "refresh_job_manager", None)
    jobs = manager.list_jobs(active_only=False) if manager is not None else []
    state = derive_local_database_state(
        has_statements=has_statements,
        jobs=jobs,
        now=datetime.now(timezone.utc),
    )
    state["failures"] = failures
    return state
