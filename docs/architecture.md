# Architecture

## Goal

`zotwatch-public-harvester` is the shared public-ingestion layer for ZotWatch-compatible consumers. It centralizes fetching, normalization, deduplication, and storage so that downstream repos can read a stable public candidate pool instead of re-implementing source integrations independently.

## Responsibilities

### In scope

- periodic harvesting from public scholarly APIs
- normalization into a canonical work model
- public deduplication across sources
- incremental sync cursor management
- canonical storage in Supabase
- versioned, read-only APIs for downstream clients

### Out of scope

- personal Zotero ingestion
- user-specific dedupe against private libraries
- ranking and recommendations
- per-user reading, saving, or curation state

## Data Flow

1. A GitHub Actions workflow triggers a source harvest.
2. The source fetcher pulls an incremental window using the stored cursor.
3. Raw items are normalized into a common `NormalizedWork` shape.
4. Deduplication resolves source collisions into canonical works and aliases.
5. The database layer upserts canonical works, aliases, cursors, and fetch run metadata.
6. Edge Functions expose versioned read APIs for downstream consumers.

## Component Boundaries

### `src/fetchers`

Provider-specific adapters for Crossref, arXiv, bioRxiv, medRxiv, and OpenAlex.

### `src/normalize`

Shared canonical model, identifier cleanup, content hashing, and merge logic.

### `src/db`

Supabase-facing write and read helpers. All persistence details stay here.

### `src/jobs`

Operational entry points for routine harvests and targeted backfills.

### `supabase/functions`

Stable read APIs. Consumers should depend on these instead of direct table access.

## Design Principles

- idempotent writes
- explicit fetch run bookkeeping
- read contract stability through versioned API surfaces
- strict separation between public candidate data and personal state
- source-specific fetch logic with shared normalization and dedupe rules
