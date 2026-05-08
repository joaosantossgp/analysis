from __future__ import annotations

from fastapi.responses import Response

from apps.api.app.dependencies import apply_cache_headers
from src.contracts import default_incremental_refresh_policy


def test_apply_cache_headers_adds_origin_vary_once() -> None:
    response = Response()
    response.headers["Vary"] = "Accept-Encoding"

    apply_cache_headers(response, "public, max-age=60")
    apply_cache_headers(response, "public, max-age=60")

    assert response.headers["Cache-Control"] == "public, max-age=60"
    vary_values = [value.strip() for value in response.headers["Vary"].split(",")]
    assert vary_values == ["Accept-Encoding", "Origin"]


def test_default_incremental_refresh_policy_matches_existing_defaults() -> None:
    policy = default_incremental_refresh_policy()

    assert policy.skip_complete_company_years is True
    assert policy.enable_fast_lane is False
    assert policy.force_refresh is False
