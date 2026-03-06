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
    case
        when w.source in ('arxiv', 'biorxiv', 'medrxiv') or w.is_preprint then 'preprint'
        when w.source = 'crossref' then coalesce(nullif(w.extra_json ->> 'type', ''), 'article')
        when w.source = 'openalex' then coalesce(nullif(w.extra_json ->> 'type_crossref', ''), 'article')
        else 'article'
    end as candidate_type,
    case
        when w.source in ('arxiv', 'biorxiv', 'medrxiv') or w.is_preprint then 'preprint'
        when coalesce(w.extra_json ->> 'type', w.extra_json ->> 'type_crossref', '') in ('dataset', 'data-paper') then 'dataset'
        when coalesce(w.extra_json ->> 'type', w.extra_json ->> 'type_crossref', '') in ('review', 'systematic-review') then 'review'
        when coalesce(w.extra_json ->> 'type', w.extra_json ->> 'type_crossref', '') in ('book', 'book-chapter', 'monograph', 'reference-book') then 'bookish'
        else 'article'
    end as candidate_group,
    w.metrics_json as metrics,
    w.updated_at
from public.works w
where
    w.is_candidate_public = true
    and w.last_seen_at >= timezone('utc', now()) - interval '30 days';
