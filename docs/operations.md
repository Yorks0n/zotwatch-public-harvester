# Operations

## Workflows

### `harvest.yml`

Runs on:

- schedule
- manual dispatch

Responsibilities:

- install dependencies
- run incremental harvests
- persist normalized works and aliases
- update fetch runs and source cursors
- fail loudly on source or persistence errors

### `deploy-functions.yml`

Runs when Edge Function code changes on the default branch.

Responsibilities:

- install Supabase CLI
- authenticate
- deploy versioned read-only functions

## Operational Constraints

- all harvest jobs must be idempotent
- repeated windows must not create duplicates
- writes should use upserts, not insert-only behavior
- every run must record fetch metadata
- Crossref is intentionally bounded to one recent, indexed-descending sample of at most 1,000 records; its cursor is the last sample time, not a completeness watermark
- backfill jobs must be separate from routine harvest jobs
- raw payload retention must be bounded

## Failure Policy

- each attempted source records its own `success` or `failed` fetch run
- `harvest-all` reports `partial_failed` when some sources succeed and others fail; it reports `failed` when none succeed or cleanup fails
- the CLI exits non-zero for both aggregate failure states
- keep the previous cursor when a run fails before persistence completes
- report successful Crossref freshness as `sampled`; do not interpret its time range as exhaustive coverage
- surface failure summaries in `fetch_runs.error_summary`

## Downstream Contract

Downstream repos should know:

- this is a shared public candidate pool
- update cadence is workflow-driven
- records may be corrected, merged, or removed as upstream metadata changes
- version upgrades happen at the API layer
- consumers should fall back to their own direct fetch path or local cache when needed
