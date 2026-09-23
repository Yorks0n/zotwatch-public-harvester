-- Aggregate the complete visible candidate view in PostgreSQL. The Edge
-- Function is the only public entry point; it calls this RPC as service_role.
create or replace function public.api_candidate_facets_v1()
returns jsonb
language sql
stable
security invoker
set search_path = pg_catalog, public
as $$
    with candidates as materialized (
        select source, candidate_type, candidate_group, is_preprint
        from public.api_candidates_v1
    ),
    totals as (
        select
            count(*) as all_count,
            count(*) filter (where is_preprint is true) as preprint_count,
            count(*) filter (where is_preprint is not true) as published_count
        from candidates
    ),
    source_counts as (
        select coalesce(jsonb_object_agg(source, n), '{}'::jsonb) as result
        from (
            select coalesce(source, '') as source, count(*) as n
            from candidates
            group by coalesce(source, '')
        ) grouped
    ),
    type_counts as (
        select coalesce(jsonb_object_agg(candidate_type, n), '{}'::jsonb) as result
        from (
            select coalesce(candidate_type, '') as candidate_type, count(*) as n
            from candidates
            group by coalesce(candidate_type, '')
        ) grouped
    ),
    group_counts as (
        select coalesce(jsonb_object_agg(candidate_group, n), '{}'::jsonb) as result
        from (
            select coalesce(candidate_group, '') as candidate_group, count(*) as n
            from candidates
            group by coalesce(candidate_group, '')
        ) grouped
    )
    select jsonb_build_object(
        'totals', jsonb_build_object(
            'all', totals.all_count,
            'preprint', totals.preprint_count,
            'published', totals.published_count
        ),
        'sources', source_counts.result,
        'candidate_types', type_counts.result,
        'candidate_groups', group_counts.result
    )
    from totals, source_counts, type_counts, group_counts;
$$;

revoke all on function public.api_candidate_facets_v1() from public;
revoke all on function public.api_candidate_facets_v1() from anon, authenticated;
grant execute on function public.api_candidate_facets_v1() to service_role;
