# H3 final result: public harvester production contract

Final classification: **H3 overall = FINAL PASS** for the current
recent-candidate product contract. The production code baseline for this seal is
`H3_SAMPLE_MAIN=5ed7319c276124a880d54d80d470095cc4d9bb68`. This document
supersedes the earlier local H3B draft in this file; it does not erase the
historical audit or failed performance evidence.

The previously observed large-scale candidate API timeout remains a **known
capacity limitation**. It is **DEFERRED / OUT OF CURRENT PRODUCT SCOPE**, because
the current production contract uses bounded recent-candidate sampling and
does not require large-scale historical candidate traversal. Neither that
timeout nor the large-scale facet performance issue has been fixed by the
clean-data rollout.

## Accepted production contract

| Area | Current contract |
| --- | --- |
| Crossref | Recent sampled feed; at most 1,000 records per harvest; one request/page, sorted by Crossref `indexed` timestamp descending; lookback limited to the later of the previous sample time and 24 hours ago. `freshness.state=sampled` means the last successful sample time, **not** complete coverage of the filtered window. |
| arXiv | Normal recent incremental source. |
| bioRxiv / medRxiv | Temporarily, explicitly `enabled=false` in production after persistent upstream HTTP 200 responses with empty or non-JSON bodies. Disabled sources are skipped; an enabled source that fails is failed. Existing failed runs and works remain; neither source had a cursor at the disable check, and no cursor was created. They are not permanently in `PAUSED_SOURCES` and may be re-enabled after upstream recovery. |
| OpenAlex | Paused under the existing policy; skipped during harvest. |
| Retention | `works=90`, `fetch_runs=30`, `raw_payloads=7` days. |
| Candidate APIs | Current recent-candidate workload and clean-scale production health are supported. There is no acceptance guarantee for arbitrary >100k full-dataset traversal or large-scale analytics. The existing candidate API code, filters, exact-count behavior, and visibility semantics were not changed during the sampling rollout. |
| Facets | Correctness **PASS** through exact database-side aggregation and fail-closed Edge behavior; large-scale performance is a **DEFERRED KNOWN ISSUE**. |

The product supplies a limited pool of recent candidate papers to ZotWatch.
It does not mirror all of Crossref and does not need to scan hundreds of
thousands of historical candidates. ZotWatch consumes recent candidates,
not a large historical analytics database. **H1 full-pagination completeness
is historical, superseded behavior; it is not the current production
Crossref contract.** The H1 result document remains a record of that earlier
implementation and its tests.

## Chronology and evidence

### H3A: production audit

The [H3A read-only audit](H3A_AUDIT.md) found inconsistent retention
authorities: Python defaults were 3/3/1 days while the scheduled workflow
effectively used 90/30/7. It confirmed OpenAlex disabled with no fetch runs,
and identified a correctness defect in facets: the Edge implementation
aggregated only the first 1,000 returned rows while the candidate view held
15,521. The production facet response reported 1,000, undercounting by
14,521. The audit made no production changes.

### H3B: retention and facet correctness

H3B made Python's canonical retention defaults 90/30/7 days and made the
workflow pass optional overrides to those defaults. The
`20260923000000_candidate_facets_rpc.sql` migration added
`public.api_candidate_facets_v1()`: an exact aggregation over
`public.api_candidates_v1`, with `SECURITY INVOKER`, a fixed search path,
and execution restricted to `service_role`. The facet Edge Function calls
that RPC, validates the response, and fails closed on missing, malformed, or
failed results; it does not fall back to fetching 1,000 candidate rows.
Candidate visibility and the core candidate APIs were unchanged.

Before production migration, the local/remote migration lists disagreed
on `20260401023000_pause_openalex_source.sql`: its effect was already
present in production but its remote history entry was absent. The official
`supabase migration repair 20260401023000 --status applied --linked`
reconciled **history only**; it did not rerun the source update. A following
dry run listed only the facet RPC migration. The facet migration was then
applied to production and the versioned facet Edge Function deployed.
Production exact facet correctness was confirmed against independent
database-side candidate counts and group totals, including a 176,042-candidate
measurement. The stale H1 guard test was corrected to protect the unchanged
candidate APIs rather than require the superseded Crossref pagination.
H3B correctness and its final code gates passed.

### Facet performance: retained failure evidence

The deployed exact RPC had a separate large-scale performance problem.
At 176,042 candidates, the original RPC produced two `57014` failures in
five sequential service-role calls; successful calls reached 8.884 seconds.
An `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)` execution took 7,994.059 ms and
spilled temporary pages. These are genuine failures, not a correctness PASS
for large-scale latency.

The read-only PERF2 `GROUPING SETS` candidate matched the exact result and
reduced one plan's execution to 2,231.689 ms without observed spill. Yet
five sequential management-path SELECTs still took 4.764–9.985 seconds.
PERF3 simulated the 8-second PostgreSQL statement timeout under
`service_role`; its first SELECT failed with SQLSTATE `57014` and the
remaining attempts were stopped. **The optimization was not deployed.**
The original diagnostic, PERF2 benchmark, and PERF3 failure reports remain
preserved; facet large-scale performance is deferred.

### Crossref incident and contract change

The exhaustive H1 Crossref implementation proved operationally unsuitable.
A cancelled run had already processed **506 pages / 50,600 records**, while
Crossref reported a much larger matching population. The high write volume
also expanded the candidate data set and refreshed many `updated_at`
values. This led to an explicit contract change from full-window completeness
to a bounded recent sample, rather than describing a partial exhaustive run
as covered.

[PR #1](https://github.com/Yorks0n/zotwatch-public-harvester/pull/1)
contains three preserved commits:

1. `10929098209d61fc18e016223c22b531d324cde2` — one-page Crossref
   sampling of at most 1,000 recently indexed works and public
   `freshness.state=sampled`.
2. `22a4ffc361fddd56ced9240a97e04e98bd7e5fcb` — bounded retries for
   bioRxiv/medRxiv empty or non-JSON responses, `UpstreamUnavailableError`,
   and correct 30-record details-endpoint pagination. A malformed response
   is not treated as an empty collection.
3. `5ed7319c276124a880d54d80d470095cc4d9bb68` — restored H2 aggregate
   failure semantics: enabled unavailable sources fail, later sources are
   still attempted, cursors do not advance on failure, and persisted
   `error_summary` contains only the exception class.

### Controlled data reset and rollout

With the old scheduled harvest disabled and no harvest active, one authorized
reset truncated only rebuildable harvester data:
`work_aliases`, `raw_payloads`, `fetch_runs`, `source_cursors`, and
`works`. Schema, migration history, SQL functions, views, permissions,
`sources` configuration, and indexes were retained. Pre-reset aggregate
counts and source/cursor summaries were recorded separately; no paper rows
were saved as a recovery source.

The `sampled` status semantics were deployed before a bounded production
harvest. That first sample fetched 1,000 Crossref records, inserted 1,000,
and reported `coverage=sampled`. bioRxiv and medRxiv continued to return
HTTP 200 with empty or non-JSON bodies. They were explicitly disabled in
`public.sources`, preserving historical failed runs and existing works;
the read-only check found no cursor for either source. The clean-scale
health gate then passed: each candidate endpoint returned HTTP 200 on
five of five sequential calls at 3,896 candidates, with no visible new
`57014` in the checked Postgres log window.

PR #1 was marked Ready, then `main` was fast-forwarded from
`5067a70abf2a8adaa75f26517383c2fb0290c4e9` to the exact approved
`5ed7319c276124a880d54d80d470095cc4d9bb68` without rewriting any
reviewed commit. GitHub reports PR #1 merged at that same SHA. The
[automatic deployment](https://github.com/Yorks0n/zotwatch-public-harvester/actions/runs/35965289377)
was green for all five versioned public functions, including
`public-status-v1`. After three more sequential HTTP 200 calls to each
core candidate endpoint and a clear visible `57014` log check, the
`Harvest Public Sources` workflow was re-enabled.

### Official main harvest and post-harvest health

The single [manual main harvest run
35965579959](https://github.com/Yorks0n/zotwatch-public-harvester/actions/runs/35965579959)
checked out the approved `main` SHA and completed successfully:

| Source | Outcome |
| --- | --- |
| Crossref | Success: fetched 1,000; inserted 999; updated 0; one-page recent indexed sample; `coverage=sampled`. |
| arXiv | Success; 0 new records in that window. |
| bioRxiv | Skipped because explicitly disabled; no new failed fetch run. |
| medRxiv | Skipped because explicitly disabled; no new failed fetch run. |
| OpenAlex | Skipped under existing paused policy. |
| Aggregate | `status=success`; `failed=` empty. |
| Cleanup | Effective `work_retention_days=90`, `fetch_run_retention_days=30`, `raw_payload_retention_days=7`. |

After that run, `public-status-v1` still showed Crossref as `sampled`
and both preprint sources as `enabled=false`. The candidate view held
**4,895** rows: **896 arXiv** and **3,999 Crossref**. The normal and
incremental candidate endpoints both returned HTTP 200 with valid
`data`/`paging` payloads. The checked Postgres log window had no
**visible** new `57014` or statement-timeout message; log ingestion may
lag. These clean-scale observations do not establish large-scale capacity.
The rollout's post-main gates passed: Python **32/32**, Node **11/11**,
Python compile, Node/TypeScript syntax checks, and `git diff --check`.

### H3C: candidate API capacity boundary

The earlier approximately 176,000-candidate data set produced real
Postgres `57014` timeouts in both core candidate APIs. The read-only
diagnosis identified exact-count scans plus row queries ordered or
filtered by `updated_at`, with no usable `updated_at` index. Removing
exact count alone was not demonstrated sufficient: one normal row-only
server-side plan reached approximately **7.58 seconds** against an
8-second API timeout. No index or Edge change was made. The later 3,896
and 4,895-candidate health checks establish the current operating
baseline only; they do **not** repair or disprove the large-scale failure.

H3C large-scale candidate API scalability is formally
**DEFERRED / OUT OF CURRENT PRODUCT SCOPE**. Revisit it if the supported
product changes to require exhaustive Crossref collection, >100k candidate
traversal, or large-scale analytics. Do not interpret this deferral as an
H3C performance PASS.

## Final classification

| Track | Final state |
| --- | --- |
| H1 historical full-pagination behavior | **SUPERSEDED** by bounded sampled Crossref contract |
| H2 aggregate/freshness semantics | **FINAL PASS** |
| H3A retention/facet audit | **FINAL PASS** |
| H3B retention + facet correctness | **FINAL PASS** |
| Crossref bounded sampling rollout | **FINAL PASS** |
| bioRxiv / medRxiv upstream incident | **CONTAINED** by explicit temporary disable |
| Facet large-scale performance | **DEFERRED KNOWN ISSUE** |
| H3C large-scale candidate scalability | **DEFERRED / OUT OF CURRENT PRODUCT SCOPE** |
| H3 overall, under the current product contract | **FINAL PASS** |
