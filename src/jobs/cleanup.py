from __future__ import annotations

import os
from datetime import UTC
from datetime import datetime
from datetime import timedelta

from supabase import Client

from src.db.client import get_supabase_client


DEFAULT_WORK_RETENTION_DAYS = 90
DEFAULT_FETCH_RUN_RETENTION_DAYS = 30
DEFAULT_RAW_PAYLOAD_RETENTION_DAYS = 7
DELETE_BATCH_SIZE = 500


def run_cleanup(
    *,
    client: Client | None = None,
    work_retention_days: int | None = None,
    fetch_run_retention_days: int | None = None,
    raw_payload_retention_days: int | None = None,
) -> None:
    client = client or get_supabase_client()
    work_days = work_retention_days or _env_int("WORK_RETENTION_DAYS", DEFAULT_WORK_RETENTION_DAYS)
    fetch_run_days = fetch_run_retention_days or _env_int(
        "FETCH_RUN_RETENTION_DAYS",
        DEFAULT_FETCH_RUN_RETENTION_DAYS,
    )
    raw_payload_days = raw_payload_retention_days or _env_int(
        "RAW_PAYLOAD_RETENTION_DAYS",
        DEFAULT_RAW_PAYLOAD_RETENTION_DAYS,
    )

    _log(
        "cleanup",
        f"start work_retention_days={work_days} fetch_run_retention_days={fetch_run_days} raw_payload_retention_days={raw_payload_days}",
    )

    deleted_works = _delete_old_works(client, retention_days=work_days)
    deleted_fetch_runs = _delete_old_fetch_runs(client, retention_days=fetch_run_days)
    deleted_raw_payloads = _delete_old_raw_payloads(client, retention_days=raw_payload_days)

    _log(
        "cleanup",
        f"completed deleted_works={deleted_works} deleted_fetch_runs={deleted_fetch_runs} deleted_raw_payloads={deleted_raw_payloads}",
    )


def _delete_old_works(client: Client, *, retention_days: int) -> int:
    cutoff = _iso(datetime.now(UTC) - timedelta(days=retention_days))
    return _delete_in_batches(
        client,
        table="works",
        timestamp_column="last_seen_at",
        cutoff=cutoff,
    )


def _delete_old_fetch_runs(client: Client, *, retention_days: int) -> int:
    cutoff = _iso(datetime.now(UTC) - timedelta(days=retention_days))
    return _delete_in_batches(
        client,
        table="fetch_runs",
        timestamp_column="finished_at",
        cutoff=cutoff,
        extra_filters={"status": ["success", "partial_failed", "failed"]},
    )


def _delete_old_raw_payloads(client: Client, *, retention_days: int) -> int:
    cutoff = _iso(datetime.now(UTC) - timedelta(days=retention_days))
    return _delete_in_batches(
        client,
        table="raw_payloads",
        timestamp_column="fetched_at",
        cutoff=cutoff,
    )


def _delete_in_batches(
    client: Client,
    *,
    table: str,
    timestamp_column: str,
    cutoff: str,
    extra_filters: dict[str, list[str]] | None = None,
) -> int:
    deleted = 0
    while True:
        query = (
            client.table(table)
            .select("id")
            .lt(timestamp_column, cutoff)
            .limit(DELETE_BATCH_SIZE)
        )
        for column, values in (extra_filters or {}).items():
            query = query.in_(column, values)
        response = query.execute()
        rows = response.data or []
        if not rows:
            return deleted

        ids = [row["id"] for row in rows if "id" in row]
        if not ids:
            return deleted

        client.table(table).delete().in_("id", ids).execute()
        deleted += len(ids)
        _log(table, f"deleted_batch size={len(ids)} cutoff={cutoff}")


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _log(source: str, message: str) -> None:
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    print(f"[{timestamp}] [{source}] {message}")
