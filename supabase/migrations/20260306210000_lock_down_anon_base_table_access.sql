revoke all on public.sources from anon, authenticated;
revoke all on public.fetch_runs from anon, authenticated;
revoke all on public.source_cursors from anon, authenticated;
revoke all on public.works from anon, authenticated;
revoke all on public.work_aliases from anon, authenticated;
revoke all on public.raw_payloads from anon, authenticated;
revoke all on public.api_candidates_v1 from anon, authenticated;

drop policy if exists read_api_candidates_v1 on public.works;

grant usage on schema public to anon, authenticated;
