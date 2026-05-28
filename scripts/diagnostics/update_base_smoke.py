"""Smoke repetivel para o fluxo de atualizacao em lote da pagina `/atualizar-base`.

Modos:
  web     — chama a API FastAPI (`POST /refresh/batch`, polling em `/refresh/jobs/...`).
  desktop — usa o bridge Python (`CVMBridge`) como no app pywebview.

Seguranca:
  - Por padrao so imprime o que seria enviado (`--dry-run` implicito quando nao ha
    `--confirm-live`).
  - Execucao real exige `--confirm-live`.
  - `limit` acima de 50 exige `--allow-large-batch`.

Exemplos:
  python scripts/diagnostics/update_base_smoke.py --dry-run
  python scripts/diagnostics/update_base_smoke.py --profile web --confirm-live --limit 1 --cd-cvm 9512
  python scripts/diagnostics/update_base_smoke.py --profile desktop --confirm-live --limit 1 --cd-cvm 9512 --cancel
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable
from urllib.parse import urljoin

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DEFAULT_API_BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
MAX_SAFE_LIMIT = 50
TERMINAL_JOB_STATES = frozenset({"success", "error", "cancelled", "interrupted"})


@dataclass
class SmokeEvidence:
    profile: str
    api_base: str
    dry_run: bool
    batch_body: dict[str, Any]
    dispatch: dict[str, Any] | None = None
    job_snapshots: list[dict[str, Any]] | None = None
    cancel_result: dict[str, Any] | None = None
    terminal_state: str | None = None
    error: str | None = None


def default_api_base() -> str:
    return DEFAULT_API_BASE


def build_batch_body(
    *,
    mode: str,
    limit: int | None,
    cd_cvm: int | None,
    sector_slug: str | None,
    cvm_from: int | None,
    cvm_to: int | None,
    start_year: int | None,
    end_year: int | None,
    status_filter: str | None,
    search: str | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"mode": mode}
    if limit is not None:
        body["limit"] = int(limit)
    if cd_cvm is not None:
        body["cd_cvm"] = int(cd_cvm)
    if sector_slug:
        body["sector_slug"] = sector_slug
    if cvm_from is not None or cvm_to is not None:
        cvm_range: dict[str, int] = {}
        if cvm_from is not None:
            cvm_range["start"] = int(cvm_from)
        if cvm_to is not None:
            cvm_range["end"] = int(cvm_to)
        body["cvm_range"] = cvm_range
    if start_year is not None:
        body["start_year"] = int(start_year)
    if end_year is not None:
        body["end_year"] = int(end_year)
    if status_filter:
        body["status_filter"] = status_filter
    if search:
        body["search"] = search
    return body


def validate_live_guardrails(
    *,
    dry_run: bool,
    confirm_live: bool,
    limit: int | None,
    allow_large_batch: bool,
) -> None:
    if dry_run:
        return
    if not confirm_live:
        print(
            "[FAIL] Execucao real bloqueada: passe --confirm-live ou use --dry-run.\n"
            "        Exemplo seguro: python scripts/diagnostics/update_base_smoke.py --dry-run\n"
            "        Exemplo live:    python scripts/diagnostics/update_base_smoke.py --confirm-live --limit 1 --cd-cvm 9512",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if limit is not None and int(limit) > MAX_SAFE_LIMIT and not allow_large_batch:
        print(
            f"[FAIL] limit={limit} excede {MAX_SAFE_LIMIT} sem --allow-large-batch.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _merge_dispatch(dispatch: dict[str, Any]) -> dict[str, Any]:
    out = dict(dispatch)
    if "status" not in out and "state" in out:
        out["status"] = out.get("state")
    return out


def run_web_smoke(
    *,
    api_base: str,
    body: dict[str, Any],
    dry_run: bool,
    poll_interval: float,
    poll_timeout: float,
    cancel_after_running: bool,
    post_fn: Callable[..., Any] | None = None,
    get_fn: Callable[..., Any] | None = None,
) -> SmokeEvidence:
    evidence = SmokeEvidence(
        profile="web",
        api_base=api_base,
        dry_run=dry_run,
        batch_body=body,
        job_snapshots=[],
    )
    if dry_run:
        evidence.dispatch = {"status": "dry_run", "message": "Nenhuma chamada HTTP realizada."}
        return evidence

    session = requests.Session()
    post = post_fn or session.post
    get = get_fn or session.get

    batch_url = urljoin(api_base + "/", "refresh/batch")
    response = post(
        batch_url,
        json=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=60,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        evidence.error = f"Resposta invalida ({response.status_code}): {response.text[:500]}"
        raise RuntimeError(evidence.error) from exc

    if response.status_code >= 400:
        evidence.error = json.dumps(payload, ensure_ascii=False)
        raise RuntimeError(f"HTTP {response.status_code}: {evidence.error}")

    evidence.dispatch = _merge_dispatch(payload)
    status = str(payload.get("status") or "")
    job_id = payload.get("job_id")

    if status in {"already_current", "error"} or not job_id:
        evidence.terminal_state = status or "no_job"
        return evidence

    job_url = urljoin(api_base + "/", f"refresh/jobs/{job_id}")
    deadline = time.monotonic() + float(poll_timeout)
    cancel_requested = False

    while time.monotonic() < deadline:
        snap_resp = get(job_url, headers={"Accept": "application/json"}, timeout=30)
        if snap_resp.status_code == 404:
            evidence.error = f"Job {job_id} desapareceu do processo da API (404)."
            raise RuntimeError(evidence.error)
        snap = snap_resp.json()
        evidence.job_snapshots = evidence.job_snapshots or []
        evidence.job_snapshots.append(snap)

        state = str(snap.get("state") or snap.get("status") or "")
        if cancel_after_running and not cancel_requested and state == "running":
            cancel_url = urljoin(api_base + "/", f"refresh/jobs/{job_id}/cancel")
            cancel_resp = post(
                cancel_url,
                headers={"Accept": "application/json"},
                timeout=30,
            )
            try:
                evidence.cancel_result = cancel_resp.json()
            except ValueError:
                evidence.cancel_result = {"raw": cancel_resp.text[:500]}
            cancel_requested = True

        if state in TERMINAL_JOB_STATES:
            evidence.terminal_state = state
            return evidence

        time.sleep(float(poll_interval))

    evidence.error = f"Timeout apos {poll_timeout}s aguardando estado terminal do job {job_id}."
    raise RuntimeError(evidence.error)


def run_desktop_smoke(
    *,
    body: dict[str, Any],
    dry_run: bool,
    poll_interval: float,
    poll_timeout: float,
    cancel_after_running: bool,
    bridge_factory: Callable[[], Any] | None = None,
) -> SmokeEvidence:
    evidence = SmokeEvidence(
        profile="desktop",
        api_base="pywebview.bridge",
        dry_run=dry_run,
        batch_body=body,
        job_snapshots=[],
    )
    if dry_run:
        evidence.dispatch = {"status": "dry_run", "message": "Nenhuma chamada ao bridge realizada."}
        return evidence

    if bridge_factory is None:
        from desktop.bridge import CVMBridge  # noqa: PLC0415

        bridge_factory = CVMBridge

    bridge = bridge_factory()
    dispatch = bridge.request_refresh(dict(body))
    evidence.dispatch = _merge_dispatch(dispatch if isinstance(dispatch, dict) else dict(dispatch))

    status = str(evidence.dispatch.get("status") or "")
    job_id = evidence.dispatch.get("job_id")

    if status in {"already_current", "error"} or not job_id:
        evidence.terminal_state = status or "no_job"
        return evidence

    deadline = time.monotonic() + float(poll_timeout)
    cancel_requested = False

    while time.monotonic() < deadline:
        snap = bridge.get_refresh_status({"job_id": str(job_id)})
        if not isinstance(snap, dict):
            evidence.error = "get_refresh_status retornou tipo inesperado."
            raise RuntimeError(evidence.error)

        evidence.job_snapshots = evidence.job_snapshots or []
        evidence.job_snapshots.append(snap)

        state = str(snap.get("state") or snap.get("status") or "")
        if cancel_after_running and not cancel_requested and state == "running":
            evidence.cancel_result = bridge.cancel_refresh({"job_id": str(job_id)})
            cancel_requested = True

        if state == "not_found":
            evidence.terminal_state = state
            evidence.error = f"Job {job_id} nao encontrado no desktop manager."
            raise RuntimeError(evidence.error)

        if state in TERMINAL_JOB_STATES:
            evidence.terminal_state = state
            return evidence

        time.sleep(float(poll_interval))

    evidence.error = f"Timeout apos {poll_timeout}s aguardando estado terminal do job {job_id}."
    raise RuntimeError(evidence.error)


def evidence_to_dict(evidence: SmokeEvidence) -> dict[str, Any]:
    return asdict(evidence)


def format_evidence_text(evidence: SmokeEvidence) -> str:
    lines = [
        "== update_base_smoke ==",
        f"profile={evidence.profile}",
        f"api_base={evidence.api_base}",
        f"dry_run={evidence.dry_run}",
        f"batch_body={json.dumps(evidence.batch_body, ensure_ascii=False)}",
    ]
    if evidence.dispatch:
        lines.append(f"dispatch={json.dumps(evidence.dispatch, ensure_ascii=False)}")
    if evidence.job_snapshots:
        last = evidence.job_snapshots[-1]
        lines.append(f"last_snapshot={json.dumps(last, ensure_ascii=False)}")
    if evidence.cancel_result is not None:
        lines.append(f"cancel={json.dumps(evidence.cancel_result, ensure_ascii=False)}")
    if evidence.terminal_state:
        lines.append(f"terminal_state={evidence.terminal_state}")
    if evidence.error:
        lines.append(f"error={evidence.error}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke do fluxo Atualizar base (web/API + desktop bridge).")
    parser.add_argument(
        "--profile",
        choices=("web", "desktop"),
        default="web",
        help="web = FastAPI direto; desktop = CVMBridge local.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Nao chama API nem bridge; so monta o body.")
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Obrigatorio para execucao real (sem --dry-run).",
    )
    parser.add_argument(
        "--allow-large-batch",
        action="store_true",
        help=f"Permite limit acima de {MAX_SAFE_LIMIT}.",
    )
    parser.add_argument(
        "--api-base",
        default=default_api_base(),
        help=f"Base URL da API (default: env API_BASE_URL ou {DEFAULT_API_BASE}).",
    )
    parser.add_argument("--mode", default="missing", choices=("full", "missing", "outdated", "failed"))
    parser.add_argument("--limit", type=int, default=1, help="Limite final apos filtros (default: 1).")
    parser.add_argument("--cd-cvm", type=int, default=None)
    parser.add_argument("--sector-slug", default=None)
    parser.add_argument("--cvm-from", type=int, default=None)
    parser.add_argument("--cvm-to", type=int, default=None)
    parser.add_argument("--start-year", type=int, default=None)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--status-filter", default=None)
    parser.add_argument("--search", default=None)
    parser.add_argument("--poll-interval", type=float, default=2.5)
    parser.add_argument("--poll-timeout", type=float, default=180.0)
    parser.add_argument(
        "--cancel",
        action="store_true",
        help="Apos ver o job em running, solicita cancelamento (API ou bridge).",
    )
    parser.add_argument("--json", dest="json_out", action="store_true", help="Saida somente JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    api_base = str(args.api_base).rstrip("/")

    validate_live_guardrails(
        dry_run=bool(args.dry_run),
        confirm_live=bool(args.confirm_live),
        limit=int(args.limit) if args.limit is not None else None,
        allow_large_batch=bool(args.allow_large_batch),
    )

    body = build_batch_body(
        mode=str(args.mode),
        limit=int(args.limit),
        cd_cvm=args.cd_cvm,
        sector_slug=args.sector_slug,
        cvm_from=args.cvm_from,
        cvm_to=args.cvm_to,
        start_year=args.start_year,
        end_year=args.end_year,
        status_filter=args.status_filter,
        search=args.search,
    )

    try:
        if args.profile == "web":
            evidence = run_web_smoke(
                api_base=api_base,
                body=body,
                dry_run=bool(args.dry_run),
                poll_interval=float(args.poll_interval),
                poll_timeout=float(args.poll_timeout),
                cancel_after_running=bool(args.cancel),
            )
        else:
            evidence = run_desktop_smoke(
                body=body,
                dry_run=bool(args.dry_run),
                poll_interval=float(args.poll_interval),
                poll_timeout=float(args.poll_timeout),
                cancel_after_running=bool(args.cancel),
            )
    except RuntimeError as exc:
        if args.json_out:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    payload_out = evidence_to_dict(evidence)
    if args.json_out:
        print(json.dumps(payload_out, ensure_ascii=False, default=str))
    else:
        print(format_evidence_text(evidence))

    return 0 if not evidence.error else 1


if __name__ == "__main__":
    raise SystemExit(main())
