# API

## Versioning

Read APIs are versioned. Downstream repos should target versioned endpoints and should not assume stability of internal tables or unversioned helper views.

Initial version label: `v1`

## `GET /functions/v1/public-candidates-v1`

Returns public candidate works.

### Query parameters

- `since`: inclusive ISO date or timestamp filter on `published_at`
- `until`: inclusive ISO date or timestamp filter on `published_at`
- `sources`: comma-separated source list
- `candidate_types`: comma-separated low-level types such as `preprint`, `article`, `dataset`, `review`, `book`
- `candidate_groups`: comma-separated normalized groups such as `preprint`, `article`, `dataset`, `review`, `bookish`
- `limit`: default `200`, max `1000`
- `offset`: default `0`
- `include_preprints`: `true` or `false`
- `updated_since`: inclusive timestamp filter on `updated_at`

### Response shape

```json
{
  "data": [
    {
      "id": "uuid",
      "source": "crossref",
      "source_identifier": "10.1234/example",
      "doi": "10.1234/example",
      "title": "Example Paper",
      "abstract": "Abstract text",
      "authors": ["A. Author", "B. Author"],
      "published_at": "2026-03-03T00:00:00Z",
      "venue": "Nature",
      "url": "https://doi.org/10.1234/example",
      "is_preprint": false,
      "candidate_type": "journal-article",
      "candidate_group": "article",
      "metrics": {
        "cited_by": 4
      },
      "updated_at": "2026-03-06T00:10:00Z"
    }
  ],
  "paging": {
    "limit": 200,
    "offset": 0,
    "next_offset": 200
  }
}
```

## `GET /functions/v1/public-candidates-incremental-v1`

Returns candidates updated since a given cursor.

### Query parameters

- `updated_since`: required ISO timestamp
- `limit`: default `200`, max `1000`
- `offset`: default `0`

## `GET /functions/v1/public-status-v1`

Returns source freshness and recent run status.

### Response fields

- per-source last successful fetch timestamp
- most recent run status
- current covered freshness window
- current work counts

## `GET /functions/v1/public-work-v1`

Returns a single work by canonical identifier.

### Query parameters

- `id`
- `doi`

Exactly one identifier should be provided.

## `GET /functions/v1/public-candidate-facets-v1`

Returns the currently available candidate dimensions for downstream filtering.

### Response fields

- `totals.all`
- `totals.preprint`
- `totals.published`
- `sources`
- `candidate_types`
- `candidate_groups`

This endpoint is intended for downstream discovery and dashboarding before calling `public-candidates-v1`.

## Consumer Guidance

- treat the API as a candidate pool, not a personalized recommendation stream
- implement fallback behavior when freshness is stale or APIs fail
- use `updated_since` for efficient incremental syncs
- do not depend on source-specific extras beyond the documented stable fields
- use your Supabase `Publishable key` when calling the public function endpoints
- direct PostgREST access to internal tables or helper views is not part of the public contract and should be treated as unsupported
- the public functions are deployed with `--no-verify-jwt` and validate the publishable key from either `apikey` or `Authorization: Bearer ...`
