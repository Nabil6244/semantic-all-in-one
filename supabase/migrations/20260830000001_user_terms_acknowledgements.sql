-- About & Ownership acknowledgement.
--
-- One row per (user, terms_version). Bumping CURRENT_TERMS_VERSION in
-- licensing/terms.py makes an existing user acknowledge again WITHOUT
-- deleting their historical rows.
--
-- Stores no credentials: display_name is only a snapshot of the name shown
-- at the moment of acknowledgement; user_id remains the authoritative identity.

create table if not exists public.user_terms_acknowledgements (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users (id) on delete cascade,
    display_name    text,
    terms_version   text not null,
    acknowledged    boolean not null default false,
    acknowledged_at timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    constraint user_terms_acknowledgements_user_version_key
        unique (user_id, terms_version)
);

-- The app's only read is "has THIS user acknowledged THIS version".
create index if not exists user_terms_acknowledgements_user_version_idx
    on public.user_terms_acknowledgements (user_id, terms_version);

-- updated_at, and acknowledged_at, are both set SERVER-SIDE.
--
-- acknowledged_at is deliberately not accepted from the client: a client
-- cannot be trusted to supply an accurate time, and PostgREST would have to
-- send it as a JSON string (the literal "now()" is not a valid timestamptz
-- input — only the bare word 'now' is — so a client-supplied value is also
-- easy to get wrong). Stamping it here makes the audit time authoritative.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    if new.acknowledged and new.acknowledged_at is null then
        new.acknowledged_at = now();
    end if;
    return new;
end;
$$;

drop trigger if exists user_terms_acknowledgements_set_updated_at
    on public.user_terms_acknowledgements;
create trigger user_terms_acknowledgements_set_updated_at
    before insert or update on public.user_terms_acknowledgements
    for each row execute function public.set_updated_at();

alter table public.user_terms_acknowledgements enable row level security;

-- A user may only ever see, create or amend their OWN acknowledgement.
-- with check on insert/update is what stops the client submitting another
-- account's user_id, so one employee cannot acknowledge for another.
drop policy if exists user_terms_ack_select_own on public.user_terms_acknowledgements;
create policy user_terms_ack_select_own
    on public.user_terms_acknowledgements
    for select
    to authenticated
    using (user_id = auth.uid());

drop policy if exists user_terms_ack_insert_own on public.user_terms_acknowledgements;
create policy user_terms_ack_insert_own
    on public.user_terms_acknowledgements
    for insert
    to authenticated
    with check (user_id = auth.uid());

drop policy if exists user_terms_ack_update_own on public.user_terms_acknowledgements;
create policy user_terms_ack_update_own
    on public.user_terms_acknowledgements
    for update
    to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- Deliberately NO delete policy: acknowledgements are an audit record.

grant select, insert, update on public.user_terms_acknowledgements to authenticated;
