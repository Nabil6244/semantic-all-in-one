-- Video generation tracking.
--
-- One row per generation attempt, keyed by a client-generated generation_id
-- (the idempotency key). The row is the source of truth for analytics:
-- a "generated video" is exactly one row with status = 'completed', which the
-- app only writes after the final render passed its output validation.
-- Daily/weekly/monthly numbers are queries over this table (views below);
-- there is no separately maintained counter.
--
-- user_id is the Supabase auth user. It defaults to auth.uid() and RLS
-- rejects any row whose user_id is not the caller's, so a client cannot
-- record (or read) generations for another account.

create table if not exists public.video_generation_events (
    id                     uuid primary key default gen_random_uuid(),
    generation_id          uuid not null,
    user_id                uuid not null default auth.uid()
                               references auth.users (id) on delete cascade,
    project_id             text,
    status                 text not null,
    started_at             timestamptz not null default now(),
    completed_at           timestamptz,
    video_duration_seconds numeric,
    render_time_seconds    numeric,
    render_engine          text,
    app_version            text,
    platform               text,
    error_category         text,
    error_message          text,
    created_at             timestamptz not null default now(),
    updated_at             timestamptz not null default now(),
    constraint video_generation_events_generation_id_key unique (generation_id),
    constraint video_generation_events_status_check
        check (status in ('running', 'completed', 'failed', 'cancelled')),
    constraint video_generation_events_error_message_len
        check (error_message is null or char_length(error_message) <= 2000)
);

create index if not exists video_generation_events_user_completed_idx
    on public.video_generation_events (user_id, completed_at)
    where status = 'completed';

-- Server-side lifecycle rules:
--  * completed_at is stamped when a row becomes completed/failed/cancelled
--    without one (an offline-queued upload keeps the time it really ended).
--  * A finished row is final: a duplicate completion callback, a network
--    retry, or a late 'running' upsert for the same generation_id is ignored
--    (returning NULL skips the UPDATE), so a completed video can never be
--    counted twice, un-completed, or downgraded to failed.
create or replace function public.video_generation_events_lifecycle()
returns trigger
language plpgsql
as $$
begin
    if tg_op = 'UPDATE' then
        if old.status <> 'running' then
            return null;
        end if;
        new.user_id = old.user_id;
        new.generation_id = old.generation_id;
        new.started_at = old.started_at;
        new.created_at = old.created_at;
    end if;
    if new.status <> 'running' and new.completed_at is null then
        new.completed_at = now();
    end if;
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists video_generation_events_lifecycle on public.video_generation_events;
create trigger video_generation_events_lifecycle
    before insert or update on public.video_generation_events
    for each row execute function public.video_generation_events_lifecycle();

alter table public.video_generation_events enable row level security;

drop policy if exists video_generation_events_select_own on public.video_generation_events;
create policy video_generation_events_select_own
    on public.video_generation_events
    for select
    to authenticated
    using (user_id = auth.uid());

drop policy if exists video_generation_events_insert_own on public.video_generation_events;
create policy video_generation_events_insert_own
    on public.video_generation_events
    for insert
    to authenticated
    with check (user_id = auth.uid());

drop policy if exists video_generation_events_update_own on public.video_generation_events;
create policy video_generation_events_update_own
    on public.video_generation_events
    for update
    to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- Deliberately NO delete policy: generation history is an audit record.

grant select, insert, update on public.video_generation_events to authenticated;

-- ---------------------------------------------------------------------------
-- Analytics. Days are UTC. security_invoker makes the views run under the
-- caller's RLS: an app user sees only their own numbers. All-user numbers
-- are read from the Supabase dashboard / SQL editor (service role), e.g.
--
--   select user_id, day, videos from public.video_generation_daily
--   order by day desc;
-- ---------------------------------------------------------------------------

drop view if exists public.video_generation_totals;
drop view if exists public.video_generation_daily;

create view public.video_generation_daily
with (security_invoker = true) as
select
    user_id,
    (completed_at at time zone 'utc')::date as day,
    count(*)::bigint as videos
from public.video_generation_events
where status = 'completed'
group by user_id, (completed_at at time zone 'utc')::date;

-- No join to public.profiles here, so this migration never depends on a
-- table it does not create. For names, join at query time, e.g.
--   select t.*, p.display_name from public.video_generation_totals t
--   left join public.profiles p on p.id = t.user_id;
create view public.video_generation_totals
with (security_invoker = true) as
select
    user_id,
    count(*) filter (where (completed_at at time zone 'utc')::date
                           = (now() at time zone 'utc')::date)                    as today,
    count(*) filter (where (completed_at at time zone 'utc')::date
                           = (now() at time zone 'utc')::date - 1)                as yesterday,
    count(*) filter (where completed_at >= date_trunc('week', now() at time zone 'utc')
                                           at time zone 'utc')                    as this_week,
    count(*) filter (where completed_at >= date_trunc('month', now() at time zone 'utc')
                                           at time zone 'utc')                    as this_month,
    count(*)                                                                      as all_time
from public.video_generation_events
where status = 'completed'
group by user_id;

grant select on public.video_generation_daily, public.video_generation_totals to authenticated;
