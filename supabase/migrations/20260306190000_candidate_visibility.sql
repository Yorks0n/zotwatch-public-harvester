alter table public.works
add column if not exists is_candidate_public boolean not null default true;

alter table public.works
add column if not exists quality_flags_json jsonb not null default '[]'::jsonb;

create index if not exists works_candidate_visibility_idx
on public.works (is_candidate_public, last_seen_at desc);

create or replace view public.api_candidates_v1 as
select
    w.id,
    w.source,
    w.source_identifier,
    w.canonical_doi as doi,
    w.title,
    w.abstract,
    w.authors_json as authors,
    w.published_at,
    w.venue,
    w.url,
    w.is_preprint,
    w.metrics_json as metrics,
    w.updated_at
from public.works w
where
    w.is_candidate_public = true
    and w.last_seen_at >= timezone('utc', now()) - interval '30 days';
