> 历史归档：本文保留对应阶段的计划或验收事实，不代表当前部署状态或待办事项。

# H3C core candidate API timeout diagnosis

Date: 2026-09-24 UTC. Branch base: `main` at
`5067a70abf2a8adaa75f26517383c2fb0290c4e9`. This was a read-only
production investigation. No index, migration, Edge deployment, harvest, cleanup,
cursor reset, or data deletion was performed.

## Postgres evidence

Supabase Postgres logs record two `postgrest`/`authenticator` `SELECT` failures
with SQLSTATE `57014` and `canceling statement due to statement timeout`:

| Endpoint inferred from logged SQL and current Edge code | UTC | Actual predicate and order | Query ID |
| --- | --- | --- | --- |
| `public-candidates-v1` | `2026-09-24T02:13:29.821000` | No predicate; `updated_at DESC`; `LIMIT $1 OFFSET $2` | `-2478479821724382326` |
| `public-candidates-incremental-v1` | `2026-09-24T02:13:42.185000` | `updated_at >= $1`; `updated_at ASC`; `LIMIT $2 OFFSET $3` | `816870290896341025` |

Both logged queries use `WITH pgrst_source AS (...)`, a separate
`pgrst_source_count AS (SELECT 1 FROM public.api_candidates_v1 ...)`, and
`(SELECT count(*) FROM pgrst_source_count) AS total_result_set`. This matches
both Edge functions' `.select("*", { count: "exact" })` requests. The Postgres
logs do not include bound parameter values. No other regular-endpoint filters
were present in this timeout. The incremental timeout used only `updated_at`.

## Server-side plans

The Supabase SQL editor ran `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)` equivalents
against production. Plans ran through the management SQL path as `postgres`,
not the PostgREST `authenticator` connection, so these are database execution
measurements, not API latency measurements. Page size was 200, offset 0.
For incremental plans, the log's `$1` value was unavailable: the explicit
representative cutoff was `2026-09-23 00:00:00+00`. These incremental timings
cannot be attributed to the exact failed request.

| Endpoint | Query shape | Measured top-node time | Shared buffers (hit/read) | Observation |
| --- | --- | ---: | ---: | --- |
| regular | Logged PostgREST row-plus-exact-count wrapper | 5,293.823 ms | 41,002 / 45,262 | Two scans; count InitPlan about 1,784 ms |
| regular | `SELECT count(*) FROM public.api_candidates_v1` | 3,352.887 ms execution | 20,295 / 22,775 | Parallel aggregate |
| regular | `SELECT * FROM public.api_candidates_v1 ORDER BY updated_at DESC LIMIT 200 OFFSET 0` | 7,580.918 ms top node | 20,273 / 22,871 | `Gather Merge` and sort on `w.updated_at DESC` |
| incremental | Logged wrapper with representative `updated_at >=` cutoff | 4,972.935 ms | 41,693 / 44,559 | Two scans; count InitPlan about 2,114 ms |
| incremental | `count(*)` with representative cutoff | 3,566.182 ms top node | 20,647 / 22,423 | Parallel aggregate |
| incremental | Rows without count, representative cutoff | 4,981.725 ms top node | 20,625 / 22,519 | `Gather Merge`; no index-backed order |

The ordinary row-only query was already near the effective 8-second API
statement timeout on one server-side run. The log records actual timeouts for
the combined queries, despite some faster management-path runs; timing is
variable. Removing exact count alone is therefore **not demonstrated stable or
materially below 8 seconds**. Do not deploy the proposed Edge-only change on
these results. No index has been created. A separate review of indexing or
query strategy is needed before production mutation.

## Indexes and consumers

`pg_indexes` reported seven indexes on `public.works`:

- `works_candidate_visibility_idx` on `(is_candidate_public, last_seen_at DESC)`
- `works_canonical_doi_idx` on `(canonical_doi)`
- `works_last_seen_at_desc_idx` on `(last_seen_at DESC)`
- `works_pkey` on `(id)`
- `works_preprint_published_at_idx` on `(is_preprint, published_at DESC)`
- `works_published_at_desc_idx` on `(published_at DESC)`
- `works_source_source_identifier_key` on `(source, source_identifier)`

There is no `updated_at` index usable for the endpoint's filter/order. The
currently supported ZotWatch `main` and `codex/v2` versions of
`src/fetch_new.py` both advance with `paging.get("next_offset")` and never read
`paging.total`. The v1 consumer contract allows `total` to be null and defines
`next_offset=null` as the end of pagination.

## Hold

No Edge-only fix, contract tests, production deploy, index, or Crossref merge
was prepared because the no-count performance gate failed. The scheduled
harvester on `main` still needs to be disabled before its next trigger; this
diagnostic did not change GitHub Actions configuration.
