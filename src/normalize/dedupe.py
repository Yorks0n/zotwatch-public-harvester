from __future__ import annotations

from collections.abc import Iterable

from src.normalize.canonicalize import canonicalize_doi
from src.normalize.models import NormalizedWork


def dedupe_works(works: Iterable[NormalizedWork]) -> list[NormalizedWork]:
    seen: dict[tuple[str, str], NormalizedWork] = {}
    deduped: list[NormalizedWork] = []

    for work in works:
        doi = canonicalize_doi(work.canonical_doi)
        if doi:
            key = ("doi", doi)
        else:
            key = (work.source, work.source_identifier)

        if key in seen:
            continue

        seen[key] = work
        deduped.append(work)

    return deduped
