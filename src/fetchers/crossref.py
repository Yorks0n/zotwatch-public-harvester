from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC
from datetime import datetime

import httpx

from src.fetchers.base import BaseFetcher, FetchWindow
from src.fetchers.http import get_with_retries


class CrossrefFetcher(BaseFetcher):
    source_name = "crossref"
    page_size = 100

    def fetch(self, window: FetchWindow) -> list[dict[str, object]]:
        return [item for page in self.iter_pages(window) for item in page]

    def iter_pages(self, window: FetchWindow) -> Iterator[list[dict[str, object]]]:
        mailto = os.environ.get("CROSSREF_MAILTO")
        if not mailto:
            raise RuntimeError("CROSSREF_MAILTO is required for Crossref requests")

        start = _format_crossref_timestamp(window.start)
        end = _format_crossref_timestamp(window.end)
        params = {
            "filter": f"from-index-date:{start},until-index-date:{end}",
            "rows": str(self.page_size),
            "mailto": mailto,
            "cursor": "*",
        }

        with httpx.Client(
            base_url="https://api.crossref.org",
            headers={"User-Agent": f"zotwatch-public-harvester/0.1 (+mailto:{mailto})"},
            timeout=30.0,
        ) as client:
            seen_cursors = {"*"}
            while True:
                response = get_with_retries(client, "/works", params=params)
                payload = response.json()
                message = payload.get("message") if isinstance(payload, dict) else None
                if not isinstance(message, dict) or not isinstance(message.get("items"), list):
                    raise ValueError("Crossref response is missing message.items")
                items = message["items"]
                if any(not isinstance(item, dict) for item in items):
                    raise ValueError("Crossref response contains an invalid work item")
                if len(items) > self.page_size:
                    raise ValueError("Crossref response exceeds requested page size")
                yield items
                if len(items) < self.page_size:
                    return
                next_cursor = message.get("next-cursor")
                if next_cursor is None:
                    return
                if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
                    raise ValueError("Crossref response has an invalid or repeated next-cursor")
                seen_cursors.add(next_cursor)
                params["cursor"] = next_cursor


def _format_crossref_timestamp(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(UTC)
    return value.astimezone(UTC).replace(microsecond=0, tzinfo=None).isoformat()
