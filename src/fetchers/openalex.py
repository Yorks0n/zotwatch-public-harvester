from __future__ import annotations

import os
from datetime import UTC
from datetime import datetime

import httpx

from src.fetchers.base import BaseFetcher, FetchWindow
from src.fetchers.http import get_with_retries


class OpenAlexFetcher(BaseFetcher):
    source_name = "openalex"

    def fetch(self, window: FetchWindow) -> list[dict[str, object]]:
        mailto = os.environ.get("OPENALEX_MAILTO") or os.environ.get("CROSSREF_MAILTO")
        if not mailto:
            raise RuntimeError("OPENALEX_MAILTO or CROSSREF_MAILTO is required for OpenAlex requests")

        start = _format_openalex_date(window.start)
        end = _format_openalex_date(window.end)
        results: list[dict[str, object]] = []
        cursor = "*"

        with httpx.Client(
            base_url="https://api.openalex.org",
            headers={"User-Agent": f"zotwatch-public-harvester/0.1 (mailto:{mailto})"},
            timeout=30.0,
        ) as client:
            while cursor:
                response = get_with_retries(
                    client,
                    "/works",
                    params={
                        "filter": f"from_publication_date:{start},to_publication_date:{end}",
                        "per-page": "200",
                        "cursor": cursor,
                        "mailto": mailto,
                        "sort": "publication_date:desc",
                    },
                )
                payload = response.json()
                page_results = payload.get("results", [])
                if not isinstance(page_results, list):
                    break
                results.extend(item for item in page_results if isinstance(item, dict))

                meta = payload.get("meta", {})
                if not isinstance(meta, dict):
                    break
                next_cursor = meta.get("next_cursor")
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = str(next_cursor)

        return results


def _format_openalex_date(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(UTC)
    return value.astimezone(UTC).date().isoformat()
