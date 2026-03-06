from __future__ import annotations

from src.fetchers.biorxiv import _fetch_biorxiv_family
from src.fetchers.base import BaseFetcher, FetchWindow


class MedRxivFetcher(BaseFetcher):
    source_name = "medrxiv"

    def fetch(self, window: FetchWindow) -> list[dict[str, object]]:
        return _fetch_biorxiv_family(server="medrxiv", window=window)
