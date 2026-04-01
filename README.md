# zotwatch-public-harvester

Central public literature harvester for ZotWatch. It collects public metadata from scholarly sources, normalizes and deduplicates records, stores them in Supabase, and exposes stable read APIs for downstream GitHub Actions and personal ZotWatch forks.

## Scope

This repository does:

- fetch public scholarly sources
- normalize fields into a stable work model
- deduplicate public records across providers
- run incremental syncs and backfills
- write canonical data into Supabase
- expose read-only APIs for downstream consumers

This repository does not:

- sync any user's Zotero library
- store personal recommendation scores
- store per-user read, save, or library state
- build user-specific ranking or profiles

## Architecture

```text
GitHub Actions
  -> Fetchers
  -> Normalize + Deduplicate
  -> Supabase Postgres
  -> Edge Functions / Views
  -> Personal ZotWatch forks
```

See the detailed docs:

- [docs/architecture.md](/Users/yorkson/opt/zotwatch-public-harvester/docs/architecture.md)
- [docs/api.md](/Users/yorkson/opt/zotwatch-public-harvester/docs/api.md)
- [docs/schema.md](/Users/yorkson/opt/zotwatch-public-harvester/docs/schema.md)
- [docs/operations.md](/Users/yorkson/opt/zotwatch-public-harvester/docs/operations.md)

## Project Layout

```text
.
├─ README.md
├─ docs/
├─ src/
│  ├─ main.py
│  ├─ fetchers/
│  ├─ normalize/
│  ├─ db/
│  └─ jobs/
├─ supabase/
│  ├─ migrations/
│  ├─ seed.sql
│  └─ functions/
└─ .github/workflows/
```

## Stable Downstream Contract

Downstream repos should depend only on the stable candidate payload fields:

- `source`
- `source_identifier`
- `doi`
- `title`
- `abstract`
- `authors`
- `published_at`
- `venue`
- `url`
- `is_preprint`
- `metrics`
- `updated_at`

The contract is versioned at the API layer. Consumers should not depend on internal table shapes.

## Environment Variables

Harvester workflows:

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`
- `CROSSREF_MAILTO`
- `OPENALEX_MAILTO`
- `WORK_RETENTION_DAYS` optional, defaults to `90`
- `FETCH_RUN_RETENTION_DAYS` optional, defaults to `30`
- `RAW_PAYLOAD_RETENTION_DAYS` optional, defaults to `7`

Read-only consumers:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`

## Local Development

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/python -m pip install -r requirements.txt
```

Create a local `.env` file in the repository root:

```bash
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SECRET_KEY=<your_secret_key>
CROSSREF_MAILTO=<your_email>
OPENALEX_MAILTO=<your_email>
```

Load the environment variables into your shell:

```bash
export $(grep -v '^#' .env | xargs)
```

Verify the CLI entrypoint:

```bash
python -m src.main --help
```

Run the harvester:

```bash
python -m src.main harvest-all
```

Run retention cleanup only:

```bash
python -m src.main cleanup
```

The current implementation runs:

- `crossref`: incremental fetch by `from-index-date`
- `arxiv`: incremental fetch by `submittedDate` window
- `biorxiv`: incremental fetch by date-window details API
- `medrxiv`: incremental fetch by date-window details API

`openalex` harvesting is currently paused and new OpenAlex records are not fetched or written during `harvest-all`.

## GitHub Actions Setup

This repository includes two GitHub Actions workflows:

- `.github/workflows/harvest.yml`: runs incremental harvesting every 6 hours and supports manual dispatch
- `.github/workflows/deploy-functions.yml`: deploys Supabase Edge Functions on pushes to `main` or `master`, and supports manual dispatch

Recommended setup:

1. Push the repository to GitHub.
2. In `Settings -> Secrets and variables -> Actions`, add the required secrets:
   - `SUPABASE_URL`
   - `SUPABASE_SECRET_KEY`
   - `CROSSREF_MAILTO`
   - `OPENALEX_MAILTO`
   - `SUPABASE_ACCESS_TOKEN`
   - `SUPABASE_PROJECT_REF`
3. Optionally add repository variables if you want custom retention windows:
   - `WORK_RETENTION_DAYS`
   - `FETCH_RUN_RETENTION_DAYS`
   - `RAW_PAYLOAD_RETENTION_DAYS`
4. Open the GitHub `Actions` tab and enable workflows if GitHub requires first-run approval.

## Supported Sources

The repository currently harvests these public sources:

- `crossref`
- `arxiv`
- `biorxiv`
- `medrxiv`

`openalex` remains configured in `public.sources` for future re-enable, but it is currently paused.

Each source writes to the same canonical `works` table and records operational metadata in `fetch_runs` and `source_cursors`.

## Runtime Logging

Local runs and GitHub Actions runs print per-source progress logs with:

- source start and window boundaries
- stale running-run cleanup
- raw fetched counts
- normalized and filtered counts
- deduplicated counts
- upsert inserted and updated counts
- cursor updates
- final success or failure status

Example:

```text
[2026-04-01T02:30:00Z] [openalex] skipped paused_source=true
```

## Required Secrets

### Local shell

- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_SECRET_KEY`: write-capable key for this harvester repo
- `CROSSREF_MAILTO`: contact email sent with Crossref requests
- `OPENALEX_MAILTO`: optional only if OpenAlex harvesting is re-enabled later
- `WORK_RETENTION_DAYS`: optional retention window for `works`, based on `last_seen_at`
- `FETCH_RUN_RETENTION_DAYS`: optional retention window for old completed `fetch_runs`
- `RAW_PAYLOAD_RETENTION_DAYS`: optional retention window for `raw_payloads`

### GitHub Actions

Add the same values as repository secrets before enabling scheduled harvests:

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`
- `CROSSREF_MAILTO`
- `OPENALEX_MAILTO`

For function deployment, also add:

- `SUPABASE_ACCESS_TOKEN`
- `SUPABASE_PROJECT_REF`

Optional repository variables:

- `WORK_RETENTION_DAYS`
- `FETCH_RUN_RETENTION_DAYS`
- `RAW_PAYLOAD_RETENTION_DAYS`

### Edge Functions

Supabase Edge Functions cannot reliably use arbitrary custom secrets that start with `SUPABASE_`, so this repository uses a function-specific secret name:

- `HARVESTER_SUPABASE_SECRET_KEY`: set this to your Supabase `sb_secret_...` key
- `HARVESTER_SUPABASE_PUBLISHABLE_KEY`: set this to your Supabase `sb_publishable_...` key

Downstream clients should call the public functions with:

- `SUPABASE_PUBLISHABLE_KEY`

Functions are deployed with `--no-verify-jwt` and validate the publishable key internally. Downstream callers may send the key in either header:

```text
apikey: <SUPABASE_PUBLISHABLE_KEY>
```

or

```text
Authorization: Bearer <SUPABASE_PUBLISHABLE_KEY>
```

## Downstream API Usage

Downstream repos should call the public Edge Functions only. Do not read internal tables directly.
`SUPABASE_PUBLISHABLE_KEY` is safe to distribute to downstream repos because `anon` access is limited to read-only Edge Functions, not base tables or REST access to helper views.

Base URL:

```text
https://rbsfoisrcaxacwodbuzg.supabase.co/functions/v1
```

Recommended auth header:

```text
apikey: <SUPABASE_PUBLISHABLE_KEY>
```

Equivalent bearer header:

```text
Authorization: Bearer <SUPABASE_PUBLISHABLE_KEY>
```

### Available Endpoints

- `GET /public-candidates-v1`: list candidate works with filters and pagination
- `GET /public-candidates-incremental-v1`: incremental sync by `updated_since`
- `GET /public-work-v1`: fetch one work by `id` or `doi`
- `GET /public-candidate-facets-v1`: discover available sources and candidate type distribution
- `GET /public-status-v1`: inspect source freshness and latest harvest state

### `GET /public-candidates-v1`

Use this endpoint for normal downstream reads.

Supported query params:

- `sources`: comma-separated source ids such as `arxiv,biorxiv,medrxiv`
- `since`: publication-time lower bound, inclusive
- `until`: publication-time upper bound, inclusive
- `updated_since`: updated-time lower bound, inclusive
- `include_preprints`: `true` or `false`
- `candidate_types`: comma-separated fine-grained types such as `journal-article,dataset,preprint`
- `candidate_groups`: comma-separated stable groups such as `article,preprint,dataset,review,bookish`
- `limit`: page size
- `offset`: page offset

Examples:

```bash
curl "$SUPABASE_URL/functions/v1/public-candidates-v1?limit=20" \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```

```bash
curl "$SUPABASE_URL/functions/v1/public-candidates-v1?sources=arxiv,biorxiv,medrxiv&candidate_groups=preprint&limit=50" \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```

```bash
curl "$SUPABASE_URL/functions/v1/public-candidates-v1?candidate_groups=article&since=2026-03-01&until=2026-03-06&limit=100" \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```

Response shape:

```json
{
  "data": [
    {
      "id": "uuid",
      "source": "crossref",
      "source_identifier": "10.1234/abc",
      "doi": "10.1234/abc",
      "title": "Example Paper",
      "abstract": "...",
      "authors": ["A", "B"],
      "published_at": "2026-03-03T00:00:00+00:00",
      "venue": "Nature",
      "url": "https://doi.org/10.1234/abc",
      "is_preprint": false,
      "candidate_type": "journal-article",
      "candidate_group": "article",
      "metrics": {"cited_by": 4},
      "updated_at": "2026-03-06T00:10:00+00:00"
    }
  ],
  "paging": {
    "limit": 100,
    "offset": 0,
    "next_offset": 100,
    "total": 1234
  }
}
```

### `GET /public-candidates-incremental-v1`

Use this endpoint for scheduled downstream sync jobs.

Supported query params:

- `updated_since`
- `limit`

Example:

```bash
curl "$SUPABASE_URL/functions/v1/public-candidates-incremental-v1?updated_since=2026-03-06T00:00:00Z&limit=100" \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```

### `GET /public-work-v1`

Use this endpoint to fetch one work by identity.

Supported query params:

- `id`
- `doi`

Examples:

```bash
curl "$SUPABASE_URL/functions/v1/public-work-v1?doi=10.1234/example" \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```

```bash
curl "$SUPABASE_URL/functions/v1/public-work-v1?id=<uuid>" \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```

### `GET /public-candidate-facets-v1`

Use this endpoint before list queries if you want to discover the currently available distribution by source or candidate class.

Example:

```bash
curl "$SUPABASE_URL/functions/v1/public-candidate-facets-v1" \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```

Expected response categories:

- `totals`
- `sources`
- `candidate_types`
- `candidate_groups`

### `GET /public-status-v1`

Use this endpoint to check whether the pool is fresh enough before syncing.

Example:

```bash
curl "$SUPABASE_URL/functions/v1/public-status-v1" \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```

### Recommended Downstream Flow

For a downstream fork, the normal read pattern should be:

1. Call `public-status-v1` and confirm the pool is fresh enough.
2. Call `public-candidate-facets-v1` if you need to inspect available sources or candidate mix.
3. Use `public-candidates-incremental-v1` for normal scheduled syncs.
4. Use `public-candidates-v1` for first-time bootstrap, backfill, or type-specific pulls.
5. Use `public-work-v1` only when you need to re-fetch a single known item.

### Stable Fields for Consumers

Downstream repos should depend only on these response fields:

- `id`
- `source`
- `source_identifier`
- `doi`
- `title`
- `abstract`
- `authors`
- `published_at`
- `venue`
- `url`
- `is_preprint`
- `candidate_type`
- `candidate_group`
- `metrics`
- `updated_at`

### Candidate Type Semantics

Prefer `candidate_groups` for filtering because they are more stable across providers:

- `preprint`
- `article`
- `dataset`
- `review`
- `bookish`

Use `candidate_types` only if your downstream logic needs finer distinctions such as:

- `preprint`
- `journal-article`
- `book-chapter`
- `proceedings-article`
- `book`
- `report`
- `standard`

### Paging and Error Handling

List endpoints use `limit` and `offset`. Downstream clients should follow the returned `paging.next_offset`.

Suggested client behavior:

- retry `5xx` responses with backoff
- fail fast on `401`
- treat `400` as a caller bug and log the full query
- treat the pool as a public candidate feed, not as a personalized recommendation stream

## Initial Verification

After the environment is loaded, run one harvest locally and confirm:

```bash
python -m src.main harvest-all
```

Then verify in Supabase:

```sql
select * from public.fetch_runs order by started_at desc limit 10;
select * from public.source_cursors order by updated_at desc limit 10;
select source, source_identifier, title from public.works order by updated_at desc limit 10;
```

For source-specific checks:

```sql
select source, status, fetched_count, normalized_count, inserted_count, updated_count, error_summary
from public.fetch_runs
order by started_at desc
limit 20;
```

```sql
select source, source_identifier, title, published_at
from public.works
order by updated_at desc
limit 30;
```

## Data Quality Notes

Current quality control is intentionally lightweight:

- OpenAlex has first-pass spam and generic-title filtering
- other sources currently keep most normalized records unless they fail basic parsing
- duplicates inside the same source window are removed before write
- cross-source deduplication is still conservative and centered on DOI or source identifiers

This means the repository is already useful as a shared public candidate pool, but `public-candidates-v1` still needs an explicit quality layer before it should be treated as a fully curated downstream feed.

## Retention Policy

To prevent unbounded database growth, the harvester now runs cleanup after each `harvest-all` run:

- `works` older than `WORK_RETENTION_DAYS` are deleted using `last_seen_at`
- completed `fetch_runs` older than `FETCH_RUN_RETENTION_DAYS` are deleted
- `raw_payloads` older than `RAW_PAYLOAD_RETENTION_DAYS` are deleted

Default values:

- `WORK_RETENTION_DAYS=3`
- `FETCH_RUN_RETENTION_DAYS=3`
- `RAW_PAYLOAD_RETENTION_DAYS=1`

The cleanup command can also be run independently:

```bash
python -m src.main cleanup
```

## Known Limitations

- OpenAlex incremental sync currently uses publication date, not true metadata update time
- arXiv, bioRxiv, and medRxiv do not yet have source-specific quality filters beyond parse validation
- some upstream APIs are noisy and may return spam, event pages, or low-signal records
- base-table deduplication is still minimal; alias and merge enrichment is not fully implemented yet
- if a local process is interrupted mid-run, stale `running` runs are cleaned up only on the next run

## Current Status

This repository currently contains:

- repository contract and operational docs
- Supabase schema and RLS foundations
- versioned Edge Function stubs
- working fetchers for Crossref, arXiv, bioRxiv, medRxiv, and OpenAlex
- incremental cursor persistence and fetch-run bookkeeping
- per-source progress logging for local runs and CI
- GitHub Actions scaffolding for harvesting and function deployment

The next major area of work is downstream candidate quality: stronger filtering, cross-source merge policy, and a tighter public API surface for consumers.
