create extension if not exists pgcrypto;

create table if not exists public.sources (
    id text primary key,
    name text not null unique,
    enabled boolean not null default true,
    config_json jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.fetch_runs (
    id uuid primary key default gen_random_uuid(),
    source text not null,
    triggered_by text not null,
    started_at timestamptz not null default timezone('utc', now()),
    finished_at timestamptz,
    status text not null check (status in ('running', 'success', 'partial_failed', 'failed')),
    window_start timestamptz,
    window_end timestamptz,
    fetched_count integer not null default 0,
    normalized_count integer not null default 0,
    inserted_count integer not null default 0,
    updated_count integer not null default 0,
    error_summary text
);

create table if not exists public.source_cursors (
    source text not null,
    cursor_key text not null,
    cursor_value text not null,
    updated_at timestamptz not null default timezone('utc', now()),
    primary key (source, cursor_key)
);

create table if not exists public.works (
    id uuid primary key default gen_random_uuid(),
    source text not null,
    source_identifier text not null,
    canonical_doi text,
    title text not null,
    abstract text,
    authors_json jsonb not null default '[]'::jsonb,
    published_at timestamptz,
    venue text,
    url text,
    is_preprint boolean not null default false,
    language text,
    metrics_json jsonb not null default '{}'::jsonb,
    extra_json jsonb not null default '{}'::jsonb,
    content_hash text,
    first_seen_at timestamptz not null default timezone('utc', now()),
    last_seen_at timestamptz not null default timezone('utc', now()),
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    unique (source, source_identifier)
);

create index if not exists works_canonical_doi_idx on public.works (canonical_doi);
create index if not exists works_published_at_desc_idx on public.works (published_at desc);
create index if not exists works_last_seen_at_desc_idx on public.works (last_seen_at desc);
create index if not exists works_preprint_published_at_idx on public.works (is_preprint, published_at desc);

create table if not exists public.work_aliases (
    id uuid primary key default gen_random_uuid(),
    work_id uuid not null references public.works(id) on delete cascade,
    alias_type text not null,
    alias_value text not null,
    created_at timestamptz not null default timezone('utc', now()),
    unique (alias_type, alias_value)
);

create table if not exists public.raw_payloads (
    id uuid primary key default gen_random_uuid(),
    fetch_run_id uuid references public.fetch_runs(id) on delete cascade,
    source text not null,
    source_identifier text not null,
    payload_json jsonb not null,
    fetched_at timestamptz not null default timezone('utc', now())
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = timezone('utc', now());
    return new;
end;
$$;

drop trigger if exists works_set_updated_at on public.works;
create trigger works_set_updated_at
before update on public.works
for each row execute procedure public.set_updated_at();

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
from public.works w;

alter table public.sources enable row level security;
alter table public.fetch_runs enable row level security;
alter table public.source_cursors enable row level security;
alter table public.works enable row level security;
alter table public.work_aliases enable row level security;
alter table public.raw_payloads enable row level security;

drop policy if exists read_api_candidates_v1 on public.works;
create policy read_api_candidates_v1
on public.works
for select
to anon, authenticated
using (true);

grant usage on schema public to anon, authenticated;
grant select on public.api_candidates_v1 to anon, authenticated;
