from __future__ import annotations

from datetime import UTC
from datetime import datetime

import httpx

from src.fetchers.base import BaseFetcher, FetchWindow
from src.fetchers.http import get_json_with_retries
from src.fetchers.http import InvalidJsonResponseError
from src.fetchers.http import UpstreamUnavailableError


class BioRxivFetcher(BaseFetcher):
    source_name = "biorxiv"

    def fetch(self, window: FetchWindow) -> list[dict[str, object]]:
        return _fetch_biorxiv_family(server="biorxiv", window=window)


def _fetch_biorxiv_family(*, server: str, window: FetchWindow) -> list[dict[str, object]]:
    start_date = _format_biorxiv_date(window.start)
    end_date = _format_biorxiv_date(window.end)
    cursor = 0
    # The details endpoint returns 30 records per page.
    page_size = 30
    items: list[dict[str, object]] = []

    with httpx.Client(base_url="https://api.biorxiv.org", timeout=30.0) as client:
        while True:
            try:
                payload = get_json_with_retries(
                    client,
                    f"/details/{server}/{start_date}/{end_date}/{cursor}/json",
                    params={},
                    context=f"{server} details cursor={cursor}",
                )
            except (InvalidJsonResponseError, UpstreamUnavailableError, ValueError, httpx.HTTPStatusError,
                    httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                raise UpstreamUnavailableError(
                    f"{server} details fetch failed cursor={cursor}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise UpstreamUnavailableError(
                    f"{server} details returned a non-object JSON payload cursor={cursor}"
                )
            collection = payload.get("collection", [])
            if not isinstance(collection, list) or not collection:
                break
            items.extend(item for item in collection if isinstance(item, dict))

            messages = payload.get("messages", [])
            if not isinstance(messages, list) or not messages:
                break
            first_message = messages[0]
            if not isinstance(first_message, dict):
                break
            total = _safe_int(first_message.get("total"))
            if total is None:
                break
            cursor += page_size
            if cursor >= total:
                break

    return items


def _format_biorxiv_date(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(UTC)
    return value.astimezone(UTC).date().isoformat()


def _safe_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
