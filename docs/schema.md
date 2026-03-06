# Schema

## Core Tables

### `public.sources`

- `id` text primary key
- `name` text unique
- `enabled` boolean
- `config_json` jsonb
- `updated_at` timestamptz

### `public.fetch_runs`

- `id` uuid primary key
- `source` text
- `triggered_by` text
- `started_at` timestamptz
- `finished_at` timestamptz
- `status` text
- `window_start` timestamptz
- `window_end` timestamptz
- `fetched_count` integer
- `normalized_count` integer
- `inserted_count` integer
- `updated_count` integer
- `error_summary` text

### `public.source_cursors`

- `source` text
- `cursor_key` text
- `cursor_value` text
- `updated_at` timestamptz

Primary key: `source, cursor_key`

### `public.works`

- `id` uuid primary key
- `source` text
- `source_identifier` text
- `canonical_doi` text
- `title` text
- `abstract` text
- `authors_json` jsonb
- `published_at` timestamptz
- `venue` text
- `url` text
- `is_preprint` boolean
- `language` text
- `metrics_json` jsonb
- `extra_json` jsonb
- `content_hash` text
- `first_seen_at` timestamptz
- `last_seen_at` timestamptz
- `created_at` timestamptz
- `updated_at` timestamptz

Constraints:

- unique on `source, source_identifier`
- index on `canonical_doi`
- index on `published_at desc`
- index on `last_seen_at desc`
- index on `is_preprint, published_at desc`

### `public.work_aliases`

- `id` uuid primary key
- `work_id` uuid references `public.works(id)`
- `alias_type` text
- `alias_value` text
- `created_at` timestamptz

Useful alias types:

- `doi`
- `url`
- `arxiv_id`
- `openalex_id`
- `title_hash`

### `public.raw_payloads`

- `id` uuid primary key
- `fetch_run_id` uuid references `public.fetch_runs(id)`
- `source` text
- `source_identifier` text
- `payload_json` jsonb
- `fetched_at` timestamptz

This table is optional in production. If retained, apply a retention policy.

## Deduplication Rules

1. Primary match by normalized DOI.
2. Secondary match by source identifier aliases.
3. Tertiary merge-candidate detection by normalized title plus first author plus publication date.
4. Merge precedence:
   - DOI: Crossref > OpenAlex > bioRxiv or medRxiv > arXiv
   - abstract: OpenAlex or preprint source preferred when richer
   - venue: Crossref or OpenAlex preferred
   - citation metrics: OpenAlex preferred

## Access Model

- harvester workflows write using `service_role`
- read-only clients consume public Edge Functions with restricted fields
- `anon` and `authenticated` do not receive direct privileges on base tables
- versioned public contracts are exposed by Edge Functions, not direct REST access to helper views
- RLS stays enabled on base tables
- public-facing contracts stay versioned above the storage layer
