from __future__ import annotations

import os
from datetime import UTC
from datetime import datetime

import httpx

from src.fetchers.base import BaseFetcher, FetchWindow
from src.fetchers.http import get_with_retries


class CrossrefFetcher(BaseFetcher):
    source_name = "crossref"
    sample_size = 1000

    def fetch(self, window: FetchWindow) -> list[dict[str, object]]:
        mailto = os.environ.get("CROSSREF_MAILTO")
        if not mailto:
            raise RuntimeError("CROSSREF_MAILTO is required for Crossref requests")

        start = _format_crossref_timestamp(window.start)
        end = _format_crossref_timestamp(window.end)
        params = {
            "filter": f"from-index-date:{start},until-index-date:{end}",
            "rows": str(self.sample_size),
            "sort": "indexed",
            "order": "desc",
            "mailto": mailto,
        }

        with httpx.Client(
            base_url="https://api.crossref.org",
            headers={"User-Agent": f"zotwatch-public-harvester/0.1 (+mailto:{mailto})"},
            timeout=30.0,
        ) as client:
            response = get_with_retries(client, "/works", params=params)
            payload = response.json()
        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, dict) or not isinstance(message.get("items"), list):
            raise ValueError("Crossref response is missing message.items")
        items = message["items"]
        if any(not isinstance(item, dict) for item in items):
            raise ValueError("Crossref response contains an invalid work item")
        if len(items) > self.sample_size:
            raise ValueError("Crossref response exceeds requested sample size")
        return items


def _format_crossref_timestamp(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(UTC)
    return value.astimezone(UTC).replace(microsecond=0, tzinfo=None).isoformat()
