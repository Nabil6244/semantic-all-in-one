-- Shared learning system: sanitized per-user event log + published, style-scoped knowledge packages.
-- NOT DEPLOYED by the desktop app. Review, then apply with the Supabase CLI / SQL editor.
--
-- learning_events: private to the uploading user (RLS own-rows only; no update/delete policies, so rows are an append-only
--   audit trail). Idempotent on (user_id, event_id). Shared learning never reads other users' rows from the client:
--   aggregation runs with the service role OFF-DEVICE and publishes sanitized packages into knowledge_packages.
-- knowledge_packages: readable by any authenticated user, but ONLY status='published' rows; no insert/update/delete
--   policy exists, so only the service role (an administrative publisher) can write.

create table if not exists public.learning_events (
    id             uuid primary key default gen_random_uuid(),
    event_id       text not null,
    user_id        uuid not null default auth.uid() references auth.users (id) on delete cascade,
    device_id      text,
    event_type     text not null,
    schema_version integer not null default 1,
    occurred_at    timestamptz not null,
    style_scope    text not null,
    project_id     text,
    generation_id  text,
    csv_sha256     text,
    payload        jsonb not null default '{}'::jsonb,
    received_at    timestamptz not null default now(),
    constraint learning_events_user_event_key unique (user_id, event_id),
    constraint learning_events_type_check check (event_type in
        ('csv_import','render_outcome','render_validation','scene_failure','pre_render_failure','csv_import_failed','assets_outcome','video_rating')),
    constraint learning_events_scope_check check (style_scope ~ '^[a-z0-9_.+\-]{1,60}/[a-z0-9_.+\-]{1,60}(\+[a-z0-9_.+\-]{1,60})?$'),
    constraint learning_events_event_id_len check (char_length(event_id) between 1 and 128),
    constraint learning_events_payload_size check (pg_column_size(payload) <= 8192),
    constraint learning_events_no_comment check (not (payload ? 'comment'))
);

create index if not exists learning_events_scope_type_idx on public.learning_events (style_scope, event_type);
create index if not exists learning_events_user_idx on public.learning_events (user_id, received_at);

-- Rate limit: at most 3000 rows per user per rolling minute (a day of 60 videos is a few thousand rows in total).
create or replace function public.learning_events_rate_limit() returns trigger language plpgsql as $$
begin
    if (select count(*) from public.learning_events
        where user_id = new.user_id and received_at > now() - interval '1 minute') >= 3000 then
        raise exception 'learning_events rate limit' using errcode = '54000';
    end if;
    return new;
end;
$$;
drop trigger if exists learning_events_rate_limit on public.learning_events;
create trigger learning_events_rate_limit before insert on public.learning_events
    for each row execute function public.learning_events_rate_limit();

alter table public.learning_events enable row level security;
drop policy if exists learning_events_select_own on public.learning_events;
create policy learning_events_select_own on public.learning_events for select to authenticated using (user_id = auth.uid());
drop policy if exists learning_events_insert_own on public.learning_events;
create policy learning_events_insert_own on public.learning_events for insert to authenticated with check (user_id = auth.uid());
grant select, insert on public.learning_events to authenticated;

create table if not exists public.knowledge_packages (
    id           uuid primary key default gen_random_uuid(),
    style_scope  text not null,
    version      integer not null check (version > 0),
    status       text not null default 'candidate' check (status in ('candidate','published','withdrawn')),
    package      jsonb not null,
    created_at   timestamptz not null default now(),
    constraint knowledge_packages_scope_version_key unique (style_scope, version),
    constraint knowledge_packages_size check (pg_column_size(package) <= 20000)
);
alter table public.knowledge_packages enable row level security;
drop policy if exists knowledge_packages_read_published on public.knowledge_packages;
create policy knowledge_packages_read_published on public.knowledge_packages for select to authenticated using (status = 'published');
grant select on public.knowledge_packages to authenticated;
