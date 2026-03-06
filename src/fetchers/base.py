from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class FetchWindow:
    start: datetime | None
    end: datetime | None
    cursor: str | None = None


class BaseFetcher:
    source_name: str = ""

    def fetch(self, window: FetchWindow) -> list[dict[str, Any]]:
        raise NotImplementedError
