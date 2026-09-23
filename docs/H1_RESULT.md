# H1 result: Crossref window pagination and checkpointing

## Baseline and scope

- Repository: `Yorks0n/zotwatch-public-harvester`
- Baseline: `2a02181d7c87e89bd75cdbb11b4bc9f277bb7c25`
- Branch: `h1/crossref-cursor-pagination`
- Scope: Crossref fetcher, Crossref harvest job, deterministic ingestion tests.
- No engine, Web, API v1 function, or database migration changes.

## Implementation

- Crossref requests begin with `cursor=*`, retain the same date filter, `rows`, and `mailto` on every page, and use each response's `next-cursor` for the following page.
- Pagination ends on a short or empty page, or on a full page with no `next-cursor`. Malformed pages and repeated cursors fail the run rather than reporting partial success.
- Each page is normalized with the existing Crossref normalizer, deduplicated with `dedupe_works`, and written through the existing `(source, source_identifier)` upsert. The source completion cursor is written once, after all pages have been fetched and persisted and the fetch run has been marked successful.
- A failed later page leaves the source cursor unchanged and records a failed fetch run. Previously written works remain in place and are updated on replay. A process interruption leaves a `running` fetch run; the existing two-hour stale-run recovery marks it failed before the next attempt.
- No schema migration is needed: the existing unique constraint and upsert provide replay safety for Crossref's canonical DOI-based source identifiers.

## Test and gate results

| Gate | Result |
| --- | --- |
| `python -m unittest discover -s tests -q` | PASS, 8 deterministic mocked Crossref tests |
| `python -m compileall -q src tests` | PASS |
| `git diff --check` | PASS |
| API v1 functions and migrations compared with baseline | PASS, unchanged |

The tests cover 125 results over two pages, two full pages followed by an empty page, a full final page without a next cursor, page-2 HTTP failure, timeout after two successful pages, unchanged watermark after both failures, replay of partially persisted rows, DOI-based logical deduplication, stale-run replay after interruption, one completion-cursor write on success, and unchanged public API v1 definitions. All Crossref responses are mocked; no live Crossref or Supabase integration gate was run.

## Boundary for review

H1 is complete for review. H2 and H3 have not been started. The existing two-hour stale-run threshold governs when an interrupted run can be automatically replayed.
