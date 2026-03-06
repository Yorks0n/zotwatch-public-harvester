from __future__ import annotations

from datetime import UTC
from datetime import datetime
from itertools import islice

from supabase import Client

from src.db.client import get_supabase_client
from src.normalize.candidates import assess_candidate_visibility


BATCH_SIZE = 200
SEEDED_EXAMPLE_SOURCE = "crossref"
SEEDED_EXAMPLE_IDENTIFIER = "10.1234/example"
SOURCE_LAST_SEEN_REFRESH = {"arxiv", "biorxiv", "medrxiv"}


def run_reindex_candidates(*, client: Client | None = None) -> None:
    client = client or get_supabase_client()
    _log("reindex", "start")
    removed_examples = _remove_seeded_example_rows(client)
    _log("reindex", f"removed_seed_examples={removed_examples}")

    rows = _fetch_all_works(client)
    _log("reindex", f"loaded_works={len(rows)}")
    now_iso = _iso(datetime.now(UTC))

    updates: list[dict[str, object]] = []
    for row in rows:
        update = _reindex_row(row, now_iso=now_iso)
        if update is not None:
            updates.append(update)

    _log("reindex", f"recomputed_rows={len(updates)}")
    updated_rows = 0
    for batch in _batched(updates, BATCH_SIZE):
        for row in batch:
            work_id = row["id"]
            payload = {
                "is_candidate_public": row["is_candidate_public"],
                "quality_flags_json": row["quality_flags_json"],
                "last_seen_at": row["last_seen_at"],
            }
            client.table("works").update(payload).eq("id", work_id).execute()
            updated_rows += 1
        _log("reindex", f"updated_batch size={len(batch)} total_updated={updated_rows}")

    _log("reindex", "completed")


def _remove_seeded_example_rows(client: Client) -> int:
    response = (
        client.table("works")
        .delete()
        .eq("source", SEEDED_EXAMPLE_SOURCE)
        .eq("source_identifier", SEEDED_EXAMPLE_IDENTIFIER)
        .execute()
    )
    return len(response.data or [])


def _fetch_all_works(client: Client) -> list[dict[str, object]]:
    all_rows: list[dict[str, object]] = []
    offset = 0
    while True:
        response = (
            client.table("works")
            .select(
                "id,source,title,abstract,venue,url,canonical_doi,authors_json,is_candidate_public,quality_flags_json,last_seen_at,updated_at"
            )
            .order("updated_at", desc=True)
            .range(offset, offset + BATCH_SIZE - 1)
            .execute()
        )
        batch = response.data or []
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < BATCH_SIZE:
            break
        offset += BATCH_SIZE
    return all_rows


def _reindex_row(row: dict[str, object], *, now_iso: str) -> dict[str, object] | None:
    source = str(row.get("source") or "")
    title = str(row.get("title") or "").strip()
    if not source or not title:
        return None

    authors_raw = row.get("authors_json")
    authors = [str(author) for author in authors_raw] if isinstance(authors_raw, list) else []
    is_candidate_public, quality_flags = assess_candidate_visibility(
        source=source,
        title=title,
        abstract=_optional_str(row.get("abstract")),
        venue=_optional_str(row.get("venue")),
        url=_optional_str(row.get("url")),
        doi=_optional_str(row.get("canonical_doi")),
        authors=authors,
    )

    last_seen_at = _optional_str(row.get("last_seen_at"))
    if source in SOURCE_LAST_SEEN_REFRESH:
        last_seen_at = now_iso
    elif not last_seen_at:
        last_seen_at = _optional_str(row.get("updated_at")) or now_iso

    return {
        "id": row["id"],
        "is_candidate_public": is_candidate_public,
        "quality_flags_json": quality_flags,
        "last_seen_at": last_seen_at,
    }


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _batched(values: list[dict[str, object]], size: int) -> list[list[dict[str, object]]]:
    iterator = iter(values)
    return [batch for batch in iter(lambda: list(islice(iterator, size)), [])]


def _log(source: str, message: str) -> None:
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    print(f"[{timestamp}] [{source}] {message}")
