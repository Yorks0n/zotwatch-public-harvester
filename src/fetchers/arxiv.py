from __future__ import annotations

from datetime import UTC
from datetime import datetime
from xml.etree import ElementTree

import httpx

from src.fetchers.base import BaseFetcher, FetchWindow
from src.fetchers.http import get_with_retries


class ArxivFetcher(BaseFetcher):
    source_name = "arxiv"

    def fetch(self, window: FetchWindow) -> list[dict[str, object]]:
        start = 0
        max_results = 100
        entries: list[dict[str, object]] = []
        query = (
            "submittedDate:["
            f"{_format_arxiv_datetime(window.start)} TO {_format_arxiv_datetime(window.end)}"
            "]"
        )

        with httpx.Client(base_url="https://export.arxiv.org", timeout=30.0) as client:
            while True:
                response = get_with_retries(
                    client,
                    "/api/query",
                    params={
                        "search_query": query,
                        "start": str(start),
                        "max_results": str(max_results),
                        "sortBy": "submittedDate",
                        "sortOrder": "descending",
                    },
                )
                batch = _parse_arxiv_feed(response.text)
                if not batch:
                    break
                entries.extend(batch)
                if len(batch) < max_results:
                    break
                start += max_results

        return entries


def _parse_arxiv_feed(xml_text: str) -> list[dict[str, object]]:
    root = ElementTree.fromstring(xml_text)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    entries: list[dict[str, object]] = []
    for entry in root.findall("atom:entry", ns):
        authors = [
            author.findtext("atom:name", default="", namespaces=ns).strip()
            for author in entry.findall("atom:author", ns)
            if author.findtext("atom:name", default="", namespaces=ns).strip()
        ]
        primary_category = entry.find("arxiv:primary_category", ns)
        alternate_link = None
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("rel") == "alternate":
                alternate_link = link.attrib.get("href")
                break

        entries.append(
            {
                "id": entry.findtext("atom:id", default="", namespaces=ns).strip(),
                "title": _clean_text(entry.findtext("atom:title", default="", namespaces=ns)),
                "summary": _clean_text(entry.findtext("atom:summary", default="", namespaces=ns)),
                "authors": authors,
                "published": entry.findtext("atom:published", default="", namespaces=ns).strip(),
                "updated": entry.findtext("atom:updated", default="", namespaces=ns).strip(),
                "primary_category": primary_category.attrib.get("term") if primary_category is not None else None,
                "url": alternate_link or entry.findtext("atom:id", default="", namespaces=ns).strip(),
            }
        )
    return entries


def _clean_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _format_arxiv_datetime(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(UTC)
    return value.astimezone(UTC).strftime("%Y%m%d%H%M")
