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
- backfill jobs must be separate from routine harvest jobs
- raw payload retention must be bounded

## Failure Policy

- mark run `partial_failed` when at least one source fails but others succeed
- mark run `failed` when no useful results were persisted
- keep the previous cursor when a run fails before persistence completes
- surface failure summaries in `fetch_runs.error_summary`

## Downstream Contract

Downstream repos should know:

- this is a shared public candidate pool
- update cadence is workflow-driven
- records may be corrected, merged, or removed as upstream metadata changes
- version upgrades happen at the API layer
- consumers should fall back to their own direct fetch path or local cache when needed
