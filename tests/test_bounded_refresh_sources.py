from __future__ import annotations

from collections import Counter
from dataclasses import replace
import threading
from types import SimpleNamespace
import zipfile

import polars as pl
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from src.financials.scraper import CVMScraper
from src.platform.db import build_engine
from src.platform.contracts import RefreshRequest
from src.platform.settings import build_settings
from src.refresh.jobs import RefreshJobRepository
from src.refresh.job_worker import RefreshJobWorker


def _write_sources(settings, *, year=2024, value=100, patterns=("DRE",)):
    raw = settings.paths.input_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for doc, end in (("dfp", f"{year}-12-31"), ("itr", f"{year}-03-31")):
        content = (
            "CD_CVM;CD_CONTA;DS_CONTA;VL_CONTA;DT_REFER;DT_INI_EXERC;"
            "DT_FIM_EXERC;ORDEM_EXERC;ESCALA_MOEDA;VERSAO;MOEDA;GRUPO_DFP\n"
        )
        for code, amount in ((9512, value), (4170, value * 2), (9999, value * 3)):
            content += (
                f"{code};3.01;Revenue;{amount};{end};{year}-01-01;{end};"
                "ÚLTIMO;MIL;1;REAL;DF Consolidado\n"
            )
        with zipfile.ZipFile(raw / f"{doc}_cia_aberta_{year}.zip", "w") as archive:
            for pattern in patterns:
                archive.writestr(f"{doc}_cia_aberta_{pattern}_con_{year}.csv", content.encode("latin1"))


def _queue(repository, code, *, start_year=2024, end_year=2024, scope="on_demand"):
    return repository.enqueue_job(
        cd_cvm=code, company_name=f"Company {code}", source_scope=scope,
        start_year=start_year, end_year=end_year,
    )


def _job(repository, job_id):
    with repository.engine.connect() as conn:
        return dict(conn.execute(text("SELECT * FROM refresh_jobs WHERE id = :id"),
                                 {"id": job_id}).mappings().one())


def _worker(tmp_path, monkeypatch):
    settings = build_settings(project_root=tmp_path)
    settings.paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    repository = RefreshJobRepository(build_engine(settings))
    repository.ensure_schema()
    _write_sources(settings)
    counts = Counter()
    scrapers = []
    read_csv = pl.read_csv
    extract = zipfile.ZipFile.extract

    def read(*args, **kwargs):
        counts["parse"] += 1
        return read_csv(*args, **kwargs)

    def unpack(*args, **kwargs):
        counts["extract"] += 1
        return extract(*args, **kwargs)

    def catalog(scraper):
        scrapers.append(scraper)
        scraper.companies_map = {f"Company {code}": code for code in (9512, 4170, 9999)}

    def persist(scraper, name, cvm, reports, qas=None):
        return scraper.db.insert_company_data(name, cvm, "comercial", reports, qas)

    monkeypatch.setattr(pl, "read_csv", read)
    monkeypatch.setattr(zipfile.ZipFile, "extract", unpack)
    monkeypatch.setattr(CVMScraper, "fetch_company_list", catalog)
    monkeypatch.setattr(CVMScraper, "_fetch_remote_zip_metadata", lambda *_: {})
    monkeypatch.setattr(CVMScraper, "persist_reports", persist)
    return RefreshJobWorker(settings=settings, repository=repository), counts, scrapers


def _observe_persistence(monkeypatch):
    snapshots = []
    persist = CVMScraper.persist_reports

    def write(scraper, name, cvm, reports, qas=None):
        cache = scraper.source_cache
        frames = [entry[1] for entry in cache._frames.values()] if cache else scraper._csv_cache.values()
        snapshots.append({
            "cache": cache,
            "companies": [set(frame["CD_CVM"].to_list()) for frame in frames],
            "local_cache": bool(scraper._csv_cache),
        })
        return persist(scraper, name, cvm, reports, qas)

    monkeypatch.setattr(CVMScraper, "persist_reports", write)
    return snapshots


def test_standalone_jobs_retain_only_current_company_until_persistence_and_release_immediately(tmp_path, monkeypatch):
    worker, counts, _ = _worker(tmp_path, monkeypatch)
    snapshots = _observe_persistence(monkeypatch)
    for code in (9512, 4170):
        job = _queue(worker.repository, code)
        assert worker.run_once()
        assert _job(worker.repository, job.id)["state"] == "success"
        snapshot = snapshots[-1]
        assert snapshot["companies"] == [{code}, {code}]
        assert not snapshot["local_cache"]
        assert snapshot["cache"] is not None
        assert not snapshot["cache"].active
        assert snapshot["cache"].retained_bytes == 0
        assert worker._source_cache is None
        assert not worker._source_job_ids
        assert not worker.run_once()

    assert snapshots[0]["cache"] is not snapshots[1]["cache"]
    assert counts == {"parse": 4, "extract": 4}
    with worker.engine.connect() as conn:
        actual = conn.execute(text('SELECT "CD_CVM", "VL_CONTA" FROM financial_reports '
                                   'WHERE "PERIOD_LABEL" = \'2024\' ORDER BY "CD_CVM"')).all()
    assert actual == [(4170, 200.0), (9512, 100.0)]


@pytest.mark.parametrize("boundary", ["source_scope", "years", "attempted"])
def test_excluded_next_job_remains_unclaimed_while_current_job_uses_a_singleton_context(tmp_path, monkeypatch, boundary):
    worker, _, _ = _worker(tmp_path, monkeypatch)
    snapshots = _observe_persistence(monkeypatch)
    first = _queue(worker.repository, 9512)
    second = _queue(worker.repository, 4170,
                    scope="other" if boundary == "source_scope" else "on_demand",
                    start_year=2023 if boundary == "years" else 2024)
    if boundary == "attempted":
        with worker.engine.begin() as conn:
            conn.execute(text("UPDATE refresh_jobs SET attempt_count = 1 WHERE id = :id"), {"id": second.id})
    elif boundary == "years":
        _write_sources(worker.settings, year=2023)

    assert worker.run_once()
    assert _job(worker.repository, first.id)["state"] == "success"
    queued = _job(worker.repository, second.id)
    assert (queued["state"], queued["attempt_count"], queued["started_at"]) == (
        "queued", int(boundary == "attempted"), None,
    )
    assert snapshots[0]["companies"] == [{9512}, {9512}]
    assert not snapshots[0]["local_cache"]
    first_cache = snapshots[0]["cache"]
    assert first_cache is not None and not first_cache.active
    assert first_cache.retained_bytes == 0
    assert worker._source_cache is None
    if boundary != "attempted":
        assert worker.run_once()
        assert _job(worker.repository, second.id)["state"] == "success"
        assert snapshots[1]["cache"] is not first_cache
        assert all(codes == {4170} for codes in snapshots[1]["companies"])
        assert not snapshots[1]["local_cache"]
        assert worker._source_cache is None


@pytest.mark.parametrize("boundary", ["retry", "request_force", "environment_force"])
def test_current_retry_and_forced_jobs_keep_the_existing_source_fallback(tmp_path, monkeypatch, boundary):
    worker, _, _ = _worker(tmp_path, monkeypatch)
    snapshots = _observe_persistence(monkeypatch)
    job = _queue(worker.repository, 9512)
    downloads = []
    if boundary == "retry":
        with worker.engine.begin() as conn:
            conn.execute(text("UPDATE refresh_jobs SET attempt_count = 1 WHERE id = :id"), {"id": job.id})
    elif boundary == "request_force":
        build = worker._build_request
        monkeypatch.setattr(worker, "_build_request", lambda item: replace(
            build(item), policy=replace(build(item).policy, force_refresh=True)
        ))
    else:
        monkeypatch.setenv("CVM_FORCE_REFRESH", "1")

        def download(_scraper, url, **_kwargs):
            downloads.append(url)
            payload = (worker.settings.paths.input_dir / "raw" / url.rsplit("/", 1)[-1]).read_bytes()
            return SimpleNamespace(status_code=200, iter_content=lambda **_: [payload])

        monkeypatch.setattr(CVMScraper, "_http_get", download)

    assert worker.run_once()
    assert _job(worker.repository, job.id)["state"] == "success"
    assert snapshots[0]["cache"] is None
    assert snapshots[0]["companies"] == [{9512, 4170, 9999}, {9512, 4170, 9999}]
    assert snapshots[0]["local_cache"]
    assert worker._source_cache is None
    if boundary == "environment_force":
        assert len(downloads) == 2
    with worker.engine.connect() as conn:
        actual = conn.execute(text('SELECT "CD_CVM", "VL_CONTA" FROM financial_reports '
                                   'WHERE "PERIOD_LABEL" = \'2024\'')).all()
    assert actual == [(9512, 100.0)]


def test_two_queued_companies_reuse_sources_without_claiming_or_mixing_them(tmp_path, monkeypatch):
    worker, counts, scrapers = _worker(tmp_path, monkeypatch)
    first = _queue(worker.repository, 9512)
    second = _queue(worker.repository, 4170)
    stages = []
    update_progress = worker.repository.update_progress

    def progress(**kwargs):
        stages.append((kwargs["job_id"], kwargs["stage"]))
        return update_progress(**kwargs)

    monkeypatch.setattr(worker.repository, "update_progress", progress)

    assert worker.run_once()
    assert _job(worker.repository, first.id)["state"] == "success"
    queued = _job(worker.repository, second.id)
    assert (queued["state"], queued["attempt_count"], queued["started_at"]) == ("queued", 0, None)
    assert worker.run_once()

    assert counts == {"parse": 2, "extract": 2}
    assert _job(worker.repository, second.id)["state"] == "success"
    with worker.engine.connect() as conn:
        actual = conn.execute(text('SELECT "CD_CVM", "VL_CONTA" FROM financial_reports '
                                   'WHERE "PERIOD_LABEL" = \'2024\' ORDER BY "CD_CVM"')).all()
    assert actual == [(4170, 200.0), (9512, 100.0)]
    assert all(not scraper._csv_cache for scraper in scrapers)
    assert Counter(job_id for job_id, _ in stages) == {first.id: 9, second.id: 9}
    assert worker._source_cache is None


def test_cohort_never_admits_a_third_company(tmp_path, monkeypatch):
    worker, counts, _ = _worker(tmp_path, monkeypatch)
    for code in (9512, 4170, 9999):
        _queue(worker.repository, code)
    for _ in range(3):
        assert worker.run_once()
    assert counts == {"parse": 4, "extract": 4}


@pytest.mark.parametrize("change", ["zip", "extracted", "missing_extracted", "missing_zip", "corrupt_zip"])
def test_changed_or_missing_source_is_not_reused(tmp_path, monkeypatch, change):
    worker, counts, _ = _worker(tmp_path, monkeypatch)
    _queue(worker.repository, 9512)
    _queue(worker.repository, 4170)
    worker.run_once()
    source = worker.settings.paths.input_dir / "raw" / "dfp_cia_aberta_2024.zip"
    csv = worker.settings.paths.input_dir / "processed" / "dfp_cia_aberta_DRE_con_2024.csv"
    if change == "zip":
        _write_sources(worker.settings, value=150)
    elif change == "extracted":
        csv.write_bytes(csv.read_bytes() + b"\n")
    elif change == "missing_extracted":
        csv.unlink()
    elif change == "missing_zip":
        source.unlink()
        monkeypatch.setattr(CVMScraper, "_http_get", lambda *_a, **_k: type("Missing", (), {"status_code": 404})())
    else:
        source.write_bytes(b"invalid zip")
    worker.run_once()
    if change == "corrupt_zip":
        # An unreadable source is a visible failure, never a reuse of old frames.
        assert counts["parse"] == 2
        with worker.engine.connect() as conn:
            errors = conn.execute(text("SELECT last_error FROM company_refresh_status WHERE cd_cvm IN (9512, 4170)")).scalars().all()
        assert any("could not be downloaded" in str(error) for error in errors)
        return
    assert counts["parse"] > 2
    if change not in {"missing_zip", "corrupt_zip"}:
        assert counts["extract"] > 2
    if change == "zip":
        with worker.engine.connect() as conn:
            value = conn.execute(text('SELECT "VL_CONTA" FROM financial_reports '
                                      'WHERE "CD_CVM" = 4170 AND "PERIOD_LABEL" = \'2024\'')).scalar_one()
        assert value == 300.0


def test_retained_frames_are_company_subsets_and_cannot_be_mutated_by_consumers(tmp_path, monkeypatch):
    worker, _, scrapers = _worker(tmp_path, monkeypatch)
    _queue(worker.repository, 9512)
    _queue(worker.repository, 4170)
    worker.run_once()
    scraper = scrapers[0]
    path = str(worker.settings.paths.input_dir / "processed" / "dfp_cia_aberta_DRE_con_2024.csv")
    first = scraper._read_csv_cached(path)
    assert set(first["CD_CVM"].tolist()) == {9512, 4170}
    first.loc[:, "VL_CONTA"] = "999999"
    second = scraper._read_csv_cached(path)
    assert second["VL_CONTA"].tolist() == ["100", "200"]
    assert not scraper._csv_cache


def test_over_budget_frames_are_read_uncached_without_a_local_full_frame_cache(tmp_path, monkeypatch):
    from src.financials.source_cache import AnnualSourceCache

    monkeypatch.setattr(AnnualSourceCache, "MAX_BYTES", 1)
    worker, counts, scrapers = _worker(tmp_path, monkeypatch)
    _queue(worker.repository, 9512)
    _queue(worker.repository, 4170)
    worker.run_once()
    assert worker._source_cache.retained_bytes == 0
    worker.run_once()
    assert counts == {"parse": 4, "extract": 2}
    assert all(not scraper._csv_cache for scraper in scrapers)


@pytest.mark.parametrize("reason", ["stop", "loop_error", "idle"])
def test_worker_releases_retained_sources_at_lifecycle_boundaries(tmp_path, monkeypatch, reason):
    worker, _, _ = _worker(tmp_path, monkeypatch)
    _queue(worker.repository, 9512)
    _queue(worker.repository, 4170)
    worker.run_once()
    cache = worker._source_cache
    assert cache.retained_bytes > 0
    if reason == "stop":
        stop = threading.Event()
        stop.set()
        worker.run_forever(stop_event=stop)
    elif reason == "loop_error":
        def fail():
            raise RuntimeError("worker loop failure")
        monkeypatch.setattr(worker, "run_once", fail)
        with pytest.raises(RuntimeError, match="worker loop failure"):
            worker.run_forever()
    else:
        worker.repository.claim_next_job(worker_id="another-worker")
        assert not worker.run_once()
    assert cache.retained_bytes == 0
    assert not cache.active


@pytest.mark.parametrize("boundary", ["expired", "retry", "source_scope", "late_job", "force", "years"])
def test_ineligible_jobs_do_not_reuse_a_previous_snapshot(tmp_path, monkeypatch, boundary):
    worker, counts, _ = _worker(tmp_path, monkeypatch)
    now = [0.0]
    monkeypatch.setattr("src.refresh.job_worker.time.monotonic", lambda: now[0])
    _queue(worker.repository, 9512)
    if boundary != "late_job":
        second = _queue(worker.repository, 4170, scope="other" if boundary == "source_scope" else "on_demand")
    worker.run_once()
    if boundary == "late_job":
        _queue(worker.repository, 4170)
    elif boundary == "expired":
        now[0] = 60.01
    elif boundary == "retry":
        with worker.engine.begin() as conn:
            conn.execute(text("UPDATE refresh_jobs SET attempt_count = 1 WHERE id = :id"), {"id": second.id})
    elif boundary == "force":
        build = worker._build_request
        monkeypatch.setattr(worker, "_build_request", lambda job: replace(
            build(job), policy=replace(build(job).policy, force_refresh=True)
        ))
    elif boundary == "years":
        with worker.engine.begin() as conn:
            conn.execute(text("UPDATE refresh_jobs SET start_year = 2023 WHERE id = :id"), {"id": second.id})
        monkeypatch.setattr(CVMScraper, "_http_get", lambda *_a, **_k: type("Missing", (), {"status_code": 404})())
    worker.run_once()
    assert counts == {"parse": 4, "extract": 4}


@pytest.mark.parametrize("failure", ["company_error", "transaction_retry"])
def test_company_failure_or_retry_discards_reuse_and_preserves_individual_results(tmp_path, monkeypatch, failure):
    worker, counts, _ = _worker(tmp_path, monkeypatch)
    first = _queue(worker.repository, 9512)
    second = _queue(worker.repository, 4170)
    persist = CVMScraper.persist_reports
    attempts = Counter()

    def write(scraper, name, cvm, reports, qas=None):
        attempts[cvm] += 1
        if cvm == 9512 and attempts[cvm] > 1:
            assert scraper.source_cache.retained_bytes == 0
        if cvm == 9512 and attempts[cvm] == 1:
            if failure == "company_error":
                raise ValueError("controlled company error")
            raise OperationalError("persist", {}, RuntimeError("transient locked database"))
        return persist(scraper, name, cvm, reports, qas)

    monkeypatch.setattr(CVMScraper, "persist_reports", write)
    monkeypatch.setattr("src.financials.scraper.time.sleep", lambda _: None)
    worker.run_once()
    assert worker._source_cache is None
    assert _job(worker.repository, first.id)["state"] == ("error" if failure == "company_error" else "success")
    assert _job(worker.repository, second.id)["state"] == "queued"
    worker.run_once()
    assert _job(worker.repository, second.id)["state"] == "success"
    assert counts == {"parse": 4, "extract": 4}


@pytest.mark.parametrize("outcome", ["cancel", "exception"])
def test_service_cancellation_and_exceptions_release_the_supplied_context(tmp_path, monkeypatch, outcome):
    worker, _, _ = _worker(tmp_path, monkeypatch)
    _queue(worker.repository, 9512)
    _queue(worker.repository, 4170)
    worker.run_once()
    cache = worker._source_cache
    request = RefreshRequest(companies=("4170",), start_year=2024, end_year=2024)
    if outcome == "cancel":
        result = worker.refresh_service.execute(request, source_cache=cache, should_cancel=lambda: True)
        assert result.cancelled
        assert not result.companies
    else:
        def fail(*_):
            raise RuntimeError("processing failure")
        monkeypatch.setattr(CVMScraper, "process_all_reports", fail)
        with pytest.raises(RuntimeError, match="processing failure"):
            worker.refresh_service.execute(request, source_cache=cache)
    assert cache.retained_bytes == 0
    assert not cache.active


def test_unexpected_download_failure_cannot_leave_a_successful_reuse_snapshot(tmp_path, monkeypatch):
    worker, _, _ = _worker(tmp_path, monkeypatch)
    _queue(worker.repository, 9512)
    _queue(worker.repository, 4170)
    worker.run_once()
    cache = worker._source_cache
    monkeypatch.setattr(CVMScraper, "_should_refresh_local_zip", lambda *_: (True, "changed remote"))

    def fail(*_args, **_kwargs):
        raise RuntimeError("download failure")

    monkeypatch.setattr(CVMScraper, "_http_get", fail)
    request = RefreshRequest(companies=("4170",), start_year=2024, end_year=2024)
    worker.refresh_service.execute(request, source_cache=cache)
    assert not cache.active
    assert cache.retained_bytes == 0


def test_skipped_company_year_does_not_skip_another_company_year(tmp_path, monkeypatch):
    from test_refresh_jobs import _insert_financial_report_row

    worker, counts, _ = _worker(tmp_path, monkeypatch)
    _write_sources(worker.settings, year=2023)
    for stmt in ("BPA", "BPP", "DRE", "DFC"):
        _insert_financial_report_row(worker.repository, cd_cvm=9512, year=2023,
                                     period_label="2023", line_id_base=stmt, value=50.0)
        with worker.engine.begin() as conn:
            conn.execute(text('UPDATE financial_reports SET "STATEMENT_TYPE" = :stmt '
                              'WHERE "LINE_ID_BASE" = :stmt'), {"stmt": stmt})
    _queue(worker.repository, 9512, start_year=2023)
    _queue(worker.repository, 4170, start_year=2023)
    worker.run_once()
    assert counts == {"parse": 2, "extract": 2}
    worker.run_once()
    assert counts == {"parse": 4, "extract": 4}
    with worker.engine.connect() as conn:
        values = conn.execute(text('SELECT "CD_CVM", "VL_CONTA" FROM financial_reports '
                                   'WHERE "STATEMENT_TYPE" = \'DRE\' AND "PERIOD_LABEL" = \'2023\' '
                                   'ORDER BY "CD_CVM"')).all()
    assert values == [(4170, 200.0), (9512, 50.0)]


def test_reuse_preserves_all_existing_source_families(tmp_path, monkeypatch):
    worker, counts, _ = _worker(tmp_path, monkeypatch)
    _write_sources(worker.settings, patterns=("BPA", "BPP", "DRE", "DFC_MD", "DFC_MI", "DVA", "DMPL"))
    _queue(worker.repository, 9512)
    _queue(worker.repository, 4170)
    worker.run_once()
    worker.run_once()
    assert counts == {"parse": 14, "extract": 14}


def test_byte_budget_is_shared_across_files_and_falls_back_per_file(tmp_path, monkeypatch):
    from src.financials.source_cache import AnnualSourceCache

    monkeypatch.setattr(AnnualSourceCache, "MAX_BYTES", 1800)
    worker, counts, _ = _worker(tmp_path, monkeypatch)
    _queue(worker.repository, 9512)
    _queue(worker.repository, 4170)
    worker.run_once()
    assert 0 < worker._source_cache.retained_bytes <= 1800
    worker.run_once()
    assert counts == {"parse": 3, "extract": 2}


@pytest.mark.parametrize("setting", ["report_type", "data_dir", "force", "companies"])
def test_service_invalidates_incompatible_context(tmp_path, monkeypatch, setting):
    worker, _, _ = _worker(tmp_path, monkeypatch)
    _queue(worker.repository, 9512)
    _queue(worker.repository, 4170)
    worker.run_once()
    cache = worker._source_cache
    request = RefreshRequest(companies=("4170",), start_year=2024, end_year=2024)
    if setting == "report_type":
        request = replace(request, report_type="individual")
    elif setting == "data_dir":
        request = replace(request, data_dir=str(tmp_path / "other_input"))
        monkeypatch.setattr(CVMScraper, "_http_get", lambda *_a, **_k: type("Missing", (), {"status_code": 404})())
    elif setting == "force":
        request = replace(request, policy=replace(request.policy, force_refresh=True))
    else:
        request = replace(request, companies=("9999",))
    worker.refresh_service.execute(request, source_cache=cache)
    assert not cache.active
    assert cache.retained_bytes == 0


def test_pandas_parser_fallback_reuses_original_source_types_and_values(tmp_path, monkeypatch):
    import pandas as pd
    import src.financials.scraper as module

    worker, counts, scrapers = _worker(tmp_path, monkeypatch)
    read_csv = pd.read_csv

    def read(*args, **kwargs):
        counts["parse"] += 1
        return read_csv(*args, **kwargs)

    def no_polars():
        raise ImportError("Polars unavailable")

    monkeypatch.setattr(module, "_pl", no_polars)
    monkeypatch.setattr(pd, "read_csv", read)
    _queue(worker.repository, 9512)
    _queue(worker.repository, 4170)
    worker.run_once()
    path = str(worker.settings.paths.input_dir / "processed" / "dfp_cia_aberta_DRE_con_2024.csv")
    frame = scrapers[0]._read_csv_cached(path)
    assert str(frame["CD_CVM"].dtype) == "Int64"
    assert frame["VL_CONTA"].tolist() == ["100", "200"]
    worker.run_once()
    assert counts == {"parse": 2, "extract": 2}


def test_empty_cohort_subset_keeps_columns_and_does_not_disable_reuse(tmp_path, monkeypatch):
    worker, counts, scrapers = _worker(tmp_path, monkeypatch)
    for doc in ("dfp", "itr"):
        path = worker.settings.paths.input_dir / "raw" / f"{doc}_cia_aberta_2024.zip"
        with zipfile.ZipFile(path, "a") as archive:
            rows = archive.read(f"{doc}_cia_aberta_DRE_con_2024.csv").splitlines()
            outside_cohort = b"\n".join([rows[0], rows[3]]) + b"\n"
            archive.writestr(f"{doc}_cia_aberta_DFC_MD_con_2024.csv", outside_cohort)

    def no_pyarrow(*_args, **_kwargs):
        raise ImportError("pyarrow unavailable")

    monkeypatch.setattr(pl.DataFrame, "to_pandas", no_pyarrow)
    _queue(worker.repository, 9512)
    _queue(worker.repository, 4170)
    worker.run_once()
    assert worker._source_cache.active
    empty_path = str(worker.settings.paths.input_dir / "processed" / "dfp_cia_aberta_DFC_MD_con_2024.csv")
    empty = scrapers[0]._read_csv_cached(empty_path)
    assert empty.empty
    assert {"CD_CVM", "CD_CONTA", "VL_CONTA", "VERSAO", "MOEDA"}.issubset(empty.columns)
    assert str(empty["CD_CVM"].dtype) == "int64"
    assert str(empty["VL_CONTA"].dtype) == "object"
    worker.run_once()
    assert counts == {"parse": 4, "extract": 4}
    with worker.engine.connect() as conn:
        actual = conn.execute(text('SELECT "CD_CVM", "VL_CONTA" FROM financial_reports '
                                   'WHERE "PERIOD_LABEL" = \'2024\' ORDER BY "CD_CVM"')).all()
    assert actual == [(4170, 200.0), (9512, 100.0)]
