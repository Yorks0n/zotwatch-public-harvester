from __future__ import annotations

import hashlib
import re


DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/)", re.IGNORECASE)
NON_WORD_RE = re.compile(r"\W+")


def canonicalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    normalized = DOI_PREFIX_RE.sub("", value.strip()).lower()
    return normalized or None


def normalize_title(value: str) -> str:
    return NON_WORD_RE.sub("", value.strip().lower())


def build_content_hash(*parts: str | None) -> str:
    joined = "||".join(part or "" for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
