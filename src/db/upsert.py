from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC
from datetime import datetime
from itertools import islice

from supabase import Client

from src.normalize.models import NormalizedWork


BATCH_SIZE = 200


def prepare_work_rows(works: Iterable[NormalizedWork]) -> list[dict[str, object]]:
    seen_at = _iso(datetime.now(UTC))
    rows: list[dict[str, object]] = []
    for work in works:
        rows.append(
            {
                "source": work.source,
                "source_identifier": work.source_identifier,
                "canonical_doi": work.canonical_doi,
                "title": work.title,
                "abstract": work.abstract,
                "authors_json": work.authors,
                "published_at": work.published_at.isoformat() if work.published_at else None,
                "venue": work.venue,
                "url": work.url,
                "is_preprint": work.is_preprint,
                "language": work.language,
                "metrics_json": work.metrics,
                "extra_json": work.extra,
                "content_hash": work.content_hash,
                "is_candidate_public": work.is_candidate_public,
                "quality_flags_json": work.quality_flags,
                "last_seen_at": seen_at,
            }
        )
    return rows


def count_existing_rows(client: Client, source: str, identifiers: list[str]) -> int:
    if not identifiers:
        return 0

    total = 0
    for batch in _batched(identifiers, BATCH_SIZE):
        response = (
            client.table("works")
            .select("source_identifier")
            .eq("source", source)
            .in_("source_identifier", batch)
            .execute()
        )
        total += len(response.data or [])
    return total


def upsert_works(client: Client, works: Iterable[NormalizedWork]) -> dict[str, int]:
    rows = prepare_work_rows(works)
    if not rows:
        return {"total": 0, "inserted": 0, "updated": 0}

    source = str(rows[0]["source"])
    identifiers = [str(row["source_identifier"]) for row in rows]
    existing_count = count_existing_rows(client, source=source, identifiers=identifiers)

    for batch in _batched(rows, BATCH_SIZE):
        client.table("works").upsert(batch, on_conflict="source,source_identifier").execute()

    total = len(rows)
    updated = min(existing_count, total)
    inserted = total - updated
    return {"total": total, "inserted": inserted, "updated": updated}


def create_fetch_run(
    client: Client,
    source: str,
    triggered_by: str,
    window_start: datetime,
    window_end: datetime,
) -> str:
    response = (
        client.table("fetch_runs")
        .insert(
            {
                "source": source,
                "triggered_by": triggered_by,
                "status": "running",
                "started_at": _iso(datetime.now(UTC)),
                "window_start": _iso(window_start),
                "window_end": _iso(window_end),
            }
        )
        .execute()
    )
    return response.data[0]["id"]


def finish_fetch_run(
    client: Client,
    run_id: str,
    *,
    status: str,
    fetched_count: int,
    normalized_count: int,
    inserted_count: int,
    updated_count: int,
    error_summary: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "status": status,
        "finished_at": _iso(datetime.now(UTC)),
        "fetched_count": fetched_count,
        "normalized_count": normalized_count,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "error_summary": error_summary,
    }
    client.table("fetch_runs").update(payload).eq("id", run_id).execute()


def fail_fetch_run(client: Client, run_id: str, error_summary: str) -> None:
    finish_fetch_run(
        client,
        run_id,
        status="failed",
        fetched_count=0,
        normalized_count=0,
        inserted_count=0,
        updated_count=0,
        error_summary=error_summary,
    )


def fail_stale_running_runs(
    client: Client,
    run_ids: list[str],
    *,
    error_summary: str,
) -> None:
    if not run_ids:
        return
    client.table("fetch_runs").update(
        {
            "status": "failed",
            "finished_at": _iso(datetime.now(UTC)),
            "error_summary": error_summary,
        }
    ).in_("id", run_ids).execute()


def upsert_source_cursor(client: Client, source: str, cursor_key: str, cursor_value: str) -> None:
    client.table("source_cursors").upsert(
        {
            "source": source,
            "cursor_key": cursor_key,
            "cursor_value": cursor_value,
            "updated_at": _iso(datetime.now(UTC)),
        },
        on_conflict="source,cursor_key",
    ).execute()


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _batched(values: list[object], size: int) -> Iterable[list[object]]:
    iterator = iter(values)
    while batch := list(islice(iterator, size)):
        yield batch
