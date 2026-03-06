from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta

from supabase import Client


def fetch_enabled_sources(client: Client) -> list[dict[str, object]]:
    response = client.table("sources").select("*").eq("enabled", True).execute()
    return list(response.data or [])


def get_source_cursor(
    client: Client,
    source: str,
    cursor_key: str = "updated_from",
) -> str | None:
    response = (
        client.table("source_cursors")
        .select("cursor_value")
        .eq("source", source)
        .eq("cursor_key", cursor_key)
        .limit(1)
        .execute()
    )
    data = response.data or []
    if not data:
        return None
    return data[0]["cursor_value"]


def default_window_start(hours: int = 24) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


def fetch_running_runs(client: Client, source: str) -> list[dict[str, object]]:
    response = (
        client.table("fetch_runs")
        .select("id,source,status,started_at,finished_at")
        .eq("source", source)
        .eq("status", "running")
        .order("started_at", desc=True)
        .execute()
    )
    return list(response.data or [])
