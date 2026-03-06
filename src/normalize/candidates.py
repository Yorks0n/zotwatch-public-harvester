from __future__ import annotations

import re


OPENALEX_BLOCKLIST_RE = re.compile(
    r"\b(xnxx|xvideos|sex videos?|viral video|mms clips?|braindumps?|exam dumps?)\b",
    re.IGNORECASE,
)
OPENALEX_GENERIC_TITLES = {
    "introduction",
    "worlds",
    "editorial",
    "foreword",
    "preface",
    "lunch and poster session",
    "poster preview session",
    "symposium wrap-up and awards",
    "main symposium podium presentations",
    "specialty interest group focused session",
}


def assess_candidate_visibility(
    *,
    source: str,
    title: str,
    abstract: str | None,
    venue: str | None,
    url: str | None,
    doi: str | None,
    authors: list[str],
) -> tuple[bool, list[str]]:
    if source != "openalex":
        return True, []

    flags: list[str] = []
    title_lower = title.strip().lower()
    combined_text = " ".join(part for part in [title, abstract or "", url or "", venue or ""]).lower()
    if title_lower in OPENALEX_GENERIC_TITLES:
        flags.append("generic_title")
    if OPENALEX_BLOCKLIST_RE.search(combined_text):
        flags.append("blocked_keyword")
    if len(title_lower) < 8:
        flags.append("short_title")
    if not doi and not venue and not authors:
        flags.append("low_metadata")
    return (len(flags) == 0, flags)
