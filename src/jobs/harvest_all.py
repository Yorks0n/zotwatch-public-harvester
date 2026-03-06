from __future__ import annotations

import os
from datetime import UTC
from datetime import datetime
from datetime import timedelta

from src.db.client import get_supabase_client
from src.db.queries import default_window_start
from src.db.queries import fetch_enabled_sources
from src.db.queries import fetch_running_runs
from src.db.queries import get_source_cursor
from src.db.upsert import create_fetch_run
from src.db.upsert import fail_fetch_run
from src.db.upsert import fail_stale_running_runs
from src.db.upsert import finish_fetch_run
from src.db.upsert import upsert_source_cursor
from src.db.upsert import upsert_works
from src.fetchers.arxiv import ArxivFetcher
from src.fetchers.base import BaseFetcher
from src.fetchers.base import FetchWindow
from src.fetchers.biorxiv import BioRxivFetcher
from src.fetchers.crossref import CrossrefFetcher
from src.fetchers.medrxiv import MedRxivFetcher
from src.fetchers.openalex import OpenAlexFetcher
from src.jobs.cleanup import run_cleanup
from src.normalize.canonicalize import build_content_hash
from src.normalize.canonicalize import canonicalize_doi
from src.normalize.candidates import assess_candidate_visibility
from src.normalize.dedupe import dedupe_works
from src.normalize.models import NormalizedWork


STALE_RUNNING_THRESHOLD = timedelta(hours=2)


def run_harvest_all() -> None:
    client = get_supabase_client()
    enabled_sources = {row["id"]: row for row in fetch_enabled_sources(client)}
    _log("harvest", f"enabled_sources={','.join(enabled_sources.keys())}")
    fetchers = [
        CrossrefFetcher(),
        ArxivFetcher(),
        BioRxivFetcher(),
        MedRxivFetcher(),
        OpenAlexFetcher(),
    ]
    for fetcher in fetchers:
        source_config = enabled_sources.get(fetcher.source_name)
        if not source_config:
            continue

        try:
            if fetcher.source_name == "crossref":
                _run_crossref_harvest(
                    client=client,
                    fetcher=fetcher,
                    cursor_key=str(source_config.get("config_json", {}).get("cursor_key", "updated_from")),
                )
                continue

            if fetcher.source_name == "arxiv":
                _run_arxiv_harvest(
                    client=client,
                    fetcher=fetcher,
                    cursor_key=str(source_config.get("config_json", {}).get("cursor_key", "updated_from")),
                )
                continue

            if fetcher.source_name == "biorxiv":
                _run_biorxiv_family_harvest(
                    client=client,
                    fetcher=fetcher,
                    cursor_key=str(source_config.get("config_json", {}).get("cursor_key", "updated_from")),
                )
                continue

            if fetcher.source_name == "medrxiv":
                _run_biorxiv_family_harvest(
                    client=client,
                    fetcher=fetcher,
                    cursor_key=str(source_config.get("config_json", {}).get("cursor_key", "updated_from")),
                )
                continue

            if fetcher.source_name == "openalex":
                _run_openalex_harvest(
                    client=client,
                    fetcher=fetcher,
                    cursor_key=str(source_config.get("config_json", {}).get("cursor_key", "cursor")),
                )
                continue

            if fetcher.source_name not in {"crossref", "arxiv", "biorxiv", "medrxiv", "openalex"}:
                print(f"skipping unimplemented source {fetcher.source_name}")
                continue
        except Exception as exc:
            _log(fetcher.source_name, f"failed error={exc}")
    run_cleanup(client=client)


def _run_crossref_harvest(*, client, fetcher: CrossrefFetcher, cursor_key: str) -> None:
    window_end = datetime.now(UTC)
    cursor_value = get_source_cursor(client, fetcher.source_name, cursor_key=cursor_key)
    window_start = (
        datetime.fromisoformat(cursor_value.replace("Z", "+00:00"))
        if cursor_value
        else default_window_start()
    )
    run_id = _prepare_fetch_run(
        client=client,
        source=fetcher.source_name,
        window_start=window_start,
        window_end=window_end,
    )
    _log(
        fetcher.source_name,
        f"start run_id={run_id} window_start={_format_dt(window_start)} window_end={_format_dt(window_end)}",
    )

    raw_items: list[dict[str, object]] = []
    normalized_count = 0
    inserted_count = 0
    updated_count = 0
    try:
        raw_items = fetcher.fetch(FetchWindow(start=window_start, end=window_end, cursor=cursor_value))
        _log(fetcher.source_name, f"fetched raw_count={len(raw_items)}")
        normalized = [_normalize_crossref_item(item) for item in raw_items]
        valid_normalized = [item for item in normalized if item is not None]
        filtered_count = len(raw_items) - len(valid_normalized)
        _log(
            fetcher.source_name,
            f"normalized valid_count={len(valid_normalized)} filtered_count={filtered_count}",
        )
        normalized = valid_normalized
        deduped = dedupe_works(normalized)
        _log(fetcher.source_name, f"deduped count={len(deduped)} removed_duplicates={len(normalized) - len(deduped)}")
        result = upsert_works(client, deduped)
        normalized_count = len(deduped)
        inserted_count = result["inserted"]
        updated_count = result["updated"]
        _log(
            fetcher.source_name,
            f"upserted inserted={inserted_count} updated={updated_count} total={result['total']}",
        )
        upsert_source_cursor(
            client,
            source=fetcher.source_name,
            cursor_key=cursor_key,
            cursor_value=window_end.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        _log(fetcher.source_name, f"cursor_updated key={cursor_key}")
        finish_fetch_run(
            client,
            run_id,
            status="success",
            fetched_count=len(raw_items),
            normalized_count=normalized_count,
            inserted_count=inserted_count,
            updated_count=updated_count,
        )
        _log(fetcher.source_name, f"completed run_id={run_id} status=success")
    except Exception as exc:
        _fail_run(
            client=client,
            run_id=run_id,
            fetched_count=len(raw_items),
            normalized_count=normalized_count,
            inserted_count=inserted_count,
            updated_count=updated_count,
            error_summary=str(exc),
        )
        _log(fetcher.source_name, f"completed run_id={run_id} status=failed")
        raise


def _run_openalex_harvest(*, client, fetcher: OpenAlexFetcher, cursor_key: str) -> None:
    window_end = datetime.now(UTC)
    cursor_value = get_source_cursor(client, fetcher.source_name, cursor_key=cursor_key)
    window_start = (
        datetime.fromisoformat(f"{cursor_value}T00:00:00+00:00")
        if cursor_value
        else default_window_start(hours=24)
    )
    run_id = _prepare_fetch_run(
        client=client,
        source=fetcher.source_name,
        window_start=window_start,
        window_end=window_end,
    )
    _log(
        fetcher.source_name,
        f"start run_id={run_id} window_start={_format_dt(window_start)} window_end={_format_dt(window_end)}",
    )

    raw_items: list[dict[str, object]] = []
    normalized_count = 0
    inserted_count = 0
    updated_count = 0
    try:
        raw_items = fetcher.fetch(FetchWindow(start=window_start, end=window_end, cursor=cursor_value))
        _log(fetcher.source_name, f"fetched raw_count={len(raw_items)}")
        normalized = [_normalize_openalex_item(item) for item in raw_items]
        valid_normalized = [item for item in normalized if item is not None]
        filtered_count = len(raw_items) - len(valid_normalized)
        _log(
            fetcher.source_name,
            f"normalized valid_count={len(valid_normalized)} filtered_count={filtered_count}",
        )
        normalized = valid_normalized
        deduped = dedupe_works(normalized)
        _log(fetcher.source_name, f"deduped count={len(deduped)} removed_duplicates={len(normalized) - len(deduped)}")
        result = upsert_works(client, deduped)
        normalized_count = len(deduped)
        inserted_count = result["inserted"]
        updated_count = result["updated"]
        _log(
            fetcher.source_name,
            f"upserted inserted={inserted_count} updated={updated_count} total={result['total']}",
        )
        upsert_source_cursor(
            client,
            source=fetcher.source_name,
            cursor_key=cursor_key,
            cursor_value=window_end.date().isoformat(),
        )
        _log(fetcher.source_name, f"cursor_updated key={cursor_key}")
        finish_fetch_run(
            client,
            run_id,
            status="success",
            fetched_count=len(raw_items),
            normalized_count=normalized_count,
            inserted_count=inserted_count,
            updated_count=updated_count,
        )
        _log(fetcher.source_name, f"completed run_id={run_id} status=success")
    except Exception as exc:
        _fail_run(
            client=client,
            run_id=run_id,
            fetched_count=len(raw_items),
            normalized_count=normalized_count,
            inserted_count=inserted_count,
            updated_count=updated_count,
            error_summary=str(exc),
        )
        _log(fetcher.source_name, f"completed run_id={run_id} status=failed")
        raise


def _run_arxiv_harvest(*, client, fetcher: ArxivFetcher, cursor_key: str) -> None:
    window_end = datetime.now(UTC)
    cursor_value = get_source_cursor(client, fetcher.source_name, cursor_key=cursor_key)
    window_start = (
        datetime.fromisoformat(cursor_value.replace("Z", "+00:00"))
        if cursor_value
        else default_window_start(hours=24)
    )
    run_id = _prepare_fetch_run(
        client=client,
        source=fetcher.source_name,
        window_start=window_start,
        window_end=window_end,
    )
    _log(
        fetcher.source_name,
        f"start run_id={run_id} window_start={_format_dt(window_start)} window_end={_format_dt(window_end)}",
    )

    raw_items: list[dict[str, object]] = []
    normalized_count = 0
    inserted_count = 0
    updated_count = 0
    try:
        raw_items = fetcher.fetch(FetchWindow(start=window_start, end=window_end, cursor=cursor_value))
        _log(fetcher.source_name, f"fetched raw_count={len(raw_items)}")
        normalized = [_normalize_arxiv_item(item) for item in raw_items]
        valid_normalized = [item for item in normalized if item is not None]
        filtered_count = len(raw_items) - len(valid_normalized)
        _log(
            fetcher.source_name,
            f"normalized valid_count={len(valid_normalized)} filtered_count={filtered_count}",
        )
        normalized = valid_normalized
        deduped = dedupe_works(normalized)
        _log(fetcher.source_name, f"deduped count={len(deduped)} removed_duplicates={len(normalized) - len(deduped)}")
        result = upsert_works(client, deduped)
        normalized_count = len(deduped)
        inserted_count = result["inserted"]
        updated_count = result["updated"]
        _log(
            fetcher.source_name,
            f"upserted inserted={inserted_count} updated={updated_count} total={result['total']}",
        )
        upsert_source_cursor(
            client,
            source=fetcher.source_name,
            cursor_key=cursor_key,
            cursor_value=window_end.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        _log(fetcher.source_name, f"cursor_updated key={cursor_key}")
        finish_fetch_run(
            client,
            run_id,
            status="success",
            fetched_count=len(raw_items),
            normalized_count=normalized_count,
            inserted_count=inserted_count,
            updated_count=updated_count,
        )
        _log(fetcher.source_name, f"completed run_id={run_id} status=success")
    except Exception as exc:
        _fail_run(
            client=client,
            run_id=run_id,
            fetched_count=len(raw_items),
            normalized_count=normalized_count,
            inserted_count=inserted_count,
            updated_count=updated_count,
            error_summary=str(exc),
        )
        _log(fetcher.source_name, f"completed run_id={run_id} status=failed")
        raise


def _run_biorxiv_family_harvest(*, client, fetcher: BaseFetcher, cursor_key: str) -> None:
    window_end = datetime.now(UTC)
    cursor_value = get_source_cursor(client, fetcher.source_name, cursor_key=cursor_key)
    window_start = (
        datetime.fromisoformat(f"{cursor_value}T00:00:00+00:00")
        if cursor_value
        else default_window_start(hours=24)
    )
    run_id = _prepare_fetch_run(
        client=client,
        source=fetcher.source_name,
        window_start=window_start,
        window_end=window_end,
    )
    _log(
        fetcher.source_name,
        f"start run_id={run_id} window_start={_format_dt(window_start)} window_end={_format_dt(window_end)}",
    )

    raw_items: list[dict[str, object]] = []
    normalized_count = 0
    inserted_count = 0
    updated_count = 0
    try:
        raw_items = fetcher.fetch(FetchWindow(start=window_start, end=window_end, cursor=cursor_value))
        _log(fetcher.source_name, f"fetched raw_count={len(raw_items)}")
        normalized = [_normalize_biorxiv_family_item(item, source=fetcher.source_name) for item in raw_items]
        valid_normalized = [item for item in normalized if item is not None]
        filtered_count = len(raw_items) - len(valid_normalized)
        _log(
            fetcher.source_name,
            f"normalized valid_count={len(valid_normalized)} filtered_count={filtered_count}",
        )
        normalized = valid_normalized
        deduped = dedupe_works(normalized)
        _log(fetcher.source_name, f"deduped count={len(deduped)} removed_duplicates={len(normalized) - len(deduped)}")
        result = upsert_works(client, deduped)
        normalized_count = len(deduped)
        inserted_count = result["inserted"]
        updated_count = result["updated"]
        _log(
            fetcher.source_name,
            f"upserted inserted={inserted_count} updated={updated_count} total={result['total']}",
        )
        upsert_source_cursor(
            client,
            source=fetcher.source_name,
            cursor_key=cursor_key,
            cursor_value=window_end.date().isoformat(),
        )
        _log(fetcher.source_name, f"cursor_updated key={cursor_key}")
        finish_fetch_run(
            client,
            run_id,
            status="success",
            fetched_count=len(raw_items),
            normalized_count=normalized_count,
            inserted_count=inserted_count,
            updated_count=updated_count,
        )
        _log(fetcher.source_name, f"completed run_id={run_id} status=success")
    except Exception as exc:
        _fail_run(
            client=client,
            run_id=run_id,
            fetched_count=len(raw_items),
            normalized_count=normalized_count,
            inserted_count=inserted_count,
            updated_count=updated_count,
            error_summary=str(exc),
        )
        _log(fetcher.source_name, f"completed run_id={run_id} status=failed")
        raise


def _normalize_crossref_item(item: dict[str, object]) -> NormalizedWork | None:
    title_parts = item.get("title") or []
    if not isinstance(title_parts, list) or not title_parts:
        return None
    title = str(title_parts[0]).strip()
    if not title:
        return None

    doi = canonicalize_doi(_optional_str(item.get("DOI")))
    source_identifier = doi or _optional_str(item.get("URL")) or title
    authors = _extract_crossref_authors(item.get("author"))
    published_at = _extract_crossref_published_at(item)
    venue = _first_list_value(item.get("container-title"))
    abstract = _optional_str(item.get("abstract"))
    url = _optional_str(item.get("URL"))
    work_type = _optional_str(item.get("type"))

    return NormalizedWork(
        source="crossref",
        source_identifier=source_identifier,
        canonical_doi=doi,
        title=title,
        abstract=abstract,
        authors=authors,
        published_at=published_at,
        venue=venue,
        url=url,
        is_preprint=work_type == "posted-content",
        language=_optional_str(item.get("language")),
        metrics={},
        extra={"type": work_type} if work_type else {},
        content_hash=build_content_hash(doi, title, authors[0] if authors else None),
        is_candidate_public=True,
        quality_flags=[],
    )


def _extract_crossref_authors(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for author in value:
        if not isinstance(author, dict):
            continue
        given = str(author.get("given", "")).strip()
        family = str(author.get("family", "")).strip()
        full_name = " ".join(part for part in [given, family] if part).strip()
        if full_name:
            authors.append(full_name)
    return authors


def _extract_crossref_published_at(item: dict[str, object]) -> datetime | None:
    for key in ("issued", "published-print", "published-online"):
        candidate = item.get(key)
        if not isinstance(candidate, dict):
            continue
        date_parts = candidate.get("date-parts")
        if not isinstance(date_parts, list) or not date_parts:
            continue
        first = date_parts[0]
        if not isinstance(first, list) or not first:
            continue
        try:
            if first[0] is None:
                continue
            year = int(first[0])
            month = int(first[1]) if len(first) > 1 and first[1] is not None else 1
            day = int(first[2]) if len(first) > 2 and first[2] is not None else 1
            return datetime(year, month, day, tzinfo=UTC)
        except (TypeError, ValueError):
            continue
    return None


def _first_list_value(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    first = str(value[0]).strip()
    return first or None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_openalex_item(item: dict[str, object]) -> NormalizedWork | None:
    title = _optional_str(item.get("display_name"))
    openalex_id = _optional_str(item.get("id"))
    if not title or not openalex_id:
        return None

    doi = canonicalize_doi(_optional_str(item.get("doi")))
    authors = _extract_openalex_authors(item.get("authorships"))
    venue = _extract_openalex_venue(item.get("primary_location"))
    url = _extract_openalex_url(item.get("primary_location")) or _optional_str(item.get("doi"))
    abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))
    published_at = _extract_openalex_published_at(item.get("publication_date"))
    type_crossref = _optional_str(item.get("type_crossref"))
    cited_by_count = item.get("cited_by_count")

    metrics: dict[str, object] = {}
    if isinstance(cited_by_count, int):
        metrics["cited_by"] = cited_by_count

    is_candidate_public, quality_flags = assess_candidate_visibility(
        source="openalex",
        title=title,
        abstract=abstract,
        venue=venue,
        url=url,
        doi=doi,
        authors=authors,
    )

    return NormalizedWork(
        source="openalex",
        source_identifier=openalex_id,
        canonical_doi=doi,
        title=title,
        abstract=abstract,
        authors=authors,
        published_at=published_at,
        venue=venue,
        url=url,
        is_preprint=type_crossref == "posted-content",
        language=_optional_str(item.get("language")),
        metrics=metrics,
        extra={"openalex_id": openalex_id, "type_crossref": type_crossref},
        content_hash=build_content_hash(doi, openalex_id, title, authors[0] if authors else None),
        is_candidate_public=is_candidate_public,
        quality_flags=quality_flags,
    )


def _normalize_arxiv_item(item: dict[str, object]) -> NormalizedWork | None:
    title = _optional_str(item.get("title"))
    source_identifier = _extract_arxiv_identifier(_optional_str(item.get("id")))
    if not title or not source_identifier:
        return None
    authors = item.get("authors") if isinstance(item.get("authors"), list) else []
    published_at = _parse_iso_datetime(_optional_str(item.get("published")))
    updated_at = _optional_str(item.get("updated"))
    primary_category = _optional_str(item.get("primary_category"))
    url = _optional_str(item.get("url")) or _optional_str(item.get("id"))
    abstract = _optional_str(item.get("summary"))

    return NormalizedWork(
        source="arxiv",
        source_identifier=source_identifier,
        canonical_doi=None,
        title=title,
        abstract=abstract,
        authors=[str(author) for author in authors],
        published_at=published_at,
        venue=primary_category,
        url=url,
        is_preprint=True,
        language=None,
        metrics={},
        extra={"updated_at": updated_at, "primary_category": primary_category},
        content_hash=build_content_hash(source_identifier, title, authors[0] if authors else None),
        is_candidate_public=True,
        quality_flags=[],
    )


def _normalize_biorxiv_family_item(item: dict[str, object], *, source: str) -> NormalizedWork | None:
    title = _optional_str(item.get("title"))
    doi = canonicalize_doi(_optional_str(item.get("doi")))
    version = _optional_str(item.get("version")) or "1"
    if not title or not doi:
        return None
    authors = _split_biorxiv_authors(_optional_str(item.get("authors")))
    published_at = _parse_iso_datetime(_optional_str(item.get("date")))
    abstract = _optional_str(item.get("abstract"))
    category = _optional_str(item.get("category"))
    source_identifier = f"{doi}v{version}"

    return NormalizedWork(
        source=source,
        source_identifier=source_identifier,
        canonical_doi=doi,
        title=title,
        abstract=abstract,
        authors=authors,
        published_at=published_at,
        venue=category,
        url=f"https://doi.org/{doi}",
        is_preprint=True,
        language=None,
        metrics={},
        extra={
            "version": version,
            "type": _optional_str(item.get("type")),
            "license": _optional_str(item.get("license")),
            "server": _optional_str(item.get("server")) or source,
            "published": _optional_str(item.get("published")),
        },
        content_hash=build_content_hash(doi, version, title, authors[0] if authors else None),
        is_candidate_public=True,
        quality_flags=[],
    )


def _extract_openalex_authors(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for authorship in value:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author")
        if not isinstance(author, dict):
            continue
        display_name = _optional_str(author.get("display_name"))
        if display_name:
            authors.append(display_name)
    return authors


def _split_biorxiv_authors(value: str | None) -> list[str]:
    if not value:
        return []
    return [author.strip() for author in value.split(";") if author.strip()]


def _extract_openalex_venue(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    source = value.get("source")
    if not isinstance(source, dict):
        return None
    return _optional_str(source.get("display_name"))


def _extract_openalex_url(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("landing_page_url", "pdf_url"):
        url = _optional_str(value.get(key))
        if url:
            return url
    return None


def _extract_openalex_published_at(value: object) -> datetime | None:
    iso_date = _optional_str(value)
    if not iso_date:
        return None
    return datetime.fromisoformat(f"{iso_date}T00:00:00+00:00")


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    if "T" not in normalized:
        normalized = f"{normalized}T00:00:00+00:00"
    return datetime.fromisoformat(normalized)


def _extract_arxiv_identifier(value: str | None) -> str | None:
    if not value:
        return None
    return value.rstrip("/").split("/")[-1] or None


def _reconstruct_abstract(value: object) -> str | None:
    if not isinstance(value, dict) or not value:
        return None
    positions: list[tuple[int, str]] = []
    for token, indexes in value.items():
        if not isinstance(token, str) or not isinstance(indexes, list):
            continue
        for index in indexes:
            if isinstance(index, int):
                positions.append((index, token))
    if not positions:
        return None
    positions.sort(key=lambda item: item[0])
    return " ".join(token for _, token in positions)


def _triggered_by() -> str:
    return "github_actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "manual"


def _prepare_fetch_run(*, client, source: str, window_start: datetime, window_end: datetime) -> str:
    running_runs = fetch_running_runs(client, source)
    _log(source, f"check_running existing={len(running_runs)}")
    stale_run_ids = [
        str(run["id"])
        for run in running_runs
        if _is_stale_running_run(_optional_str(run.get("started_at")))
    ]
    if stale_run_ids:
        _log(source, f"mark_stale_failed count={len(stale_run_ids)}")
        fail_stale_running_runs(
            client,
            stale_run_ids,
            error_summary="Marked failed before new run because previous run exceeded stale threshold",
        )

    active_running_runs = [
        run for run in running_runs if str(run["id"]) not in set(stale_run_ids)
    ]
    if active_running_runs:
        raise RuntimeError(f"source {source} already has an active running fetch_run")

    return create_fetch_run(
        client,
        source=source,
        triggered_by=_triggered_by(),
        window_start=window_start,
        window_end=window_end,
    )


def _fail_run(
    *,
    client,
    run_id: str,
    fetched_count: int,
    normalized_count: int,
    inserted_count: int,
    updated_count: int,
    error_summary: str,
) -> None:
    if fetched_count == 0 and normalized_count == 0 and inserted_count == 0 and updated_count == 0:
        fail_fetch_run(client, run_id, error_summary=error_summary)
        return
    finish_fetch_run(
        client,
        run_id,
        status="failed",
        fetched_count=fetched_count,
        normalized_count=normalized_count,
        inserted_count=inserted_count,
        updated_count=updated_count,
        error_summary=error_summary,
    )


def _is_stale_running_run(started_at: str | None) -> bool:
    if not started_at:
        return True
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    return datetime.now(UTC) - started > STALE_RUNNING_THRESHOLD


def _log(source: str, message: str) -> None:
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    print(f"[{timestamp}] [{source}] {message}")


def _format_dt(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
