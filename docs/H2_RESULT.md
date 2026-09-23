# H2 result: aggregate harvest status and source freshness

## Checkpoint and scope

- H1 was merged independently into `main` at `7dd7790c8afde63bfe0471df6ff5ca7d93938810`, recorded by the local `H1_MAIN` tag. H1 gates passed on the clean `main` tree before creating `h2/source-failure-freshness`.
- H2 uses the existing `fetch_runs` and `source_cursors` tables. No migration or second run-history authority was added.
- H3 was not started.

## Aggregate-status contract

`run_harvest_all()` returns a `HarvestResult` with `status`, `succeeded`, `failed`, `skipped`, `orchestration_error`, and `cleanup_error`. Every enabled, non-paused known source is attempted independently. Its `fetch_runs` row remains the per-source authority; the aggregate result is not stored in that table.

- `success`: one or more sources were attempted and every attempt completed successfully, with successful cleanup.
- `partial_failed`: at least one source succeeded and at least one failed, with successful cleanup.
- `failed`: no source succeeded, setup failed, or cleanup failed. Cleanup failure is reported separately and does not alter source run rows.

Disabled and paused sources are skipped. Cleanup runs after source attempts even when a source fails. An incomplete Crossref window stays failed with its partial counts and unchanged cursor. Source error summaries record the exception class only to avoid persisting upstream response details or credentials.

## CLI exit-code contract

`python -m src.main harvest-all` exits `0` only for aggregate `success`; it exits `1` for `partial_failed` and `failed`. The existing GitHub Actions step invokes that command directly, so either failure status makes the job red without workflow changes.

## Freshness semantics

`public-status-v1` keeps existing top-level and source fields. It adds `last_successful_run` and `freshness` per source. `latest_run` reports the latest attempt by `started_at`, including failed or running attempts. `last_successful_run` selects the successful run with the greatest `window_end`; `freshness.fresh_through` is that window end, and `lag_seconds` is the nonnegative elapsed time from it. With no known successful run, `state` is `no_success` and coverage and lag are `null`. `covered` means factual successful coverage exists, not that an arbitrary freshness threshold has been met. Cleanup retains each source's latest successful run beyond ordinary run-history retention, so later failures do not erase known coverage.

The candidate API v1 functions and candidate field shapes are unchanged. `public-status-v1` additions are backward-compatible.

## Test and gate evidence

| Gate | Result |
| --- | --- |
| H1 on merged `main`: `python -m unittest discover -s tests -q` | PASS, 8 tests |
| H1 on merged `main`: `python -m compileall -q src tests`; `git diff --check`; clean tree | PASS |
| H2: `/private/tmp/zotwatch-h2-venv/bin/python -m unittest discover -s tests -q` | PASS, 18 tests including all H1 pagination/replay tests |
| H2: `node --test tests/test_h2_freshness.mjs` | PASS, 3 tests |
| H2: compile, diff check, candidate API and migration comparison with H1 | PASS |

The tests use mocked sources and a fake database. No live source, Supabase, or deployed Edge Function integration run was performed.
