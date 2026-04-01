update public.sources
set
    enabled = false,
    updated_at = timezone('utc', now())
where id = 'openalex';
