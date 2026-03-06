from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class NormalizedWork(BaseModel):
    id: UUID | None = None
    source: str
    source_identifier: str
    canonical_doi: str | None = None
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    venue: str | None = None
    url: str | None = None
    is_preprint: bool = False
    language: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None
    is_candidate_public: bool = True
    quality_flags: list[str] = Field(default_factory=list)
