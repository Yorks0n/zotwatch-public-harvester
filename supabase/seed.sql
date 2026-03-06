insert into public.sources (id, name, enabled, config_json)
values
    ('crossref', 'crossref', true, '{"cursor_key":"updated_from"}'::jsonb),
    ('arxiv', 'arxiv', true, '{"cursor_key":"updated_from"}'::jsonb),
    ('biorxiv', 'biorxiv', true, '{"cursor_key":"updated_from"}'::jsonb),
    ('medrxiv', 'medrxiv', true, '{"cursor_key":"updated_from"}'::jsonb),
    ('openalex', 'openalex', true, '{"cursor_key":"cursor"}'::jsonb)
on conflict (id) do update
set
    name = excluded.name,
    enabled = excluded.enabled,
    config_json = excluded.config_json,
    updated_at = timezone('utc', now());
