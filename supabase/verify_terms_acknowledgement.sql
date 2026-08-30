-- Live verification for user_terms_acknowledgements.
--
-- Run in the Supabase SQL editor AFTER applying
-- 20260830000001_user_terms_acknowledgements.sql.
--
-- Sections 1-5 are READ-ONLY catalog queries.
-- Section 6 exercises RLS as two real users and is wrapped in an explicit
-- ROLLBACK, so it writes nothing permanent.

-- 1. table + columns -------------------------------------------------------
select column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public' and table_name = 'user_terms_acknowledgements'
order by ordinal_position;
-- EXPECT: id, user_id, display_name, terms_version, acknowledged,
--         acknowledged_at, created_at, updated_at

-- 2. unique constraint on (user_id, terms_version) -------------------------
select con.conname, pg_get_constraintdef(con.oid) as definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
where rel.relname = 'user_terms_acknowledgements' and con.contype = 'u';
-- EXPECT: UNIQUE (user_id, terms_version)

-- 3. trigger stamps acknowledged_at ---------------------------------------
select tgname,
       case when tgtype & 4 = 4 then 'INSERT ' else '' end ||
       case when tgtype & 16 = 16 then 'UPDATE' else '' end as fires_on
from pg_trigger
where tgrelid = 'public.user_terms_acknowledgements'::regclass and not tgisinternal;
-- EXPECT: fires on INSERT and UPDATE (insert matters: first ack is an insert)

-- 4. RLS enabled -----------------------------------------------------------
select relname, relrowsecurity, relforcerowsecurity
from pg_class where relname = 'user_terms_acknowledgements';
-- EXPECT: relrowsecurity = true

-- 5. policies --------------------------------------------------------------
select polname,
       case polcmd when 'r' then 'SELECT' when 'a' then 'INSERT'
                   when 'w' then 'UPDATE' when 'd' then 'DELETE'
                   else polcmd::text end as command,
       pg_get_expr(polqual, polrelid)      as using_expr,
       pg_get_expr(polwithcheck, polrelid) as with_check_expr
from pg_policy where polrelid = 'public.user_terms_acknowledgements'::regclass;
-- EXPECT exactly three rows: SELECT / INSERT / UPDATE, each = auth.uid()
-- EXPECT NO row with command = DELETE

-- 6. RLS behaviour as two real users (rolls back, nothing persisted) -------
--
-- Replace the two UUIDs with real auth.users ids, then run this whole block.
-- Negative cases are wrapped in exception handlers so a denial is REPORTED as
-- a pass instead of aborting the transaction.
do $$
declare
    a uuid := '00000000-0000-0000-0000-00000000000a';  -- <-- real user A
    b uuid := '00000000-0000-0000-0000-00000000000b';  -- <-- real user B
    stamped timestamptz;
    seen int;
    touched int;
    denied boolean;
begin
    -- ---------- act as User A ----------
    perform set_config('role', 'authenticated', true);
    perform set_config('request.jwt.claims',
        json_build_object('sub', a, 'role', 'authenticated')::text, true);

    -- A inserts their own acknowledgement, WITHOUT supplying acknowledged_at.
    insert into public.user_terms_acknowledgements
        (user_id, display_name, terms_version, acknowledged)
    values (a, 'User A', '2026-08-30-v1', true);

    select acknowledged_at into stamped
    from public.user_terms_acknowledgements
    where user_id = a and terms_version = '2026-08-30-v1';
    raise notice 'CHECK insert own row .................. %',
        case when stamped is not null then 'PASS (server stamped acknowledged_at)'
             else 'FAIL (acknowledged_at is null)' end;

    -- Upsert the SAME (user, version) again: must not create a second row.
    insert into public.user_terms_acknowledgements
        (user_id, display_name, terms_version, acknowledged)
    values (a, 'User A', '2026-08-30-v1', true)
    on conflict (user_id, terms_version)
        do update set acknowledged = excluded.acknowledged;
    select count(*) into seen from public.user_terms_acknowledgements
    where user_id = a and terms_version = '2026-08-30-v1';
    raise notice 'CHECK upsert is idempotent ............ %',
        case when seen = 1 then 'PASS (1 row)' else 'FAIL (' || seen || ' rows)' end;

    -- A acknowledges a NEWER version: must coexist with the old row.
    insert into public.user_terms_acknowledgements
        (user_id, display_name, terms_version, acknowledged)
    values (a, 'User A', '2099-01-01-v2', true);
    select count(*) into seen from public.user_terms_acknowledgements where user_id = a;
    raise notice 'CHECK old version row preserved ....... %',
        case when seen = 2 then 'PASS (v1 and v2 both present)'
             else 'FAIL (' || seen || ' rows)' end;

    -- A tries to insert AS B: must be denied by the INSERT with-check.
    denied := false;
    begin
        insert into public.user_terms_acknowledgements
            (user_id, terms_version, acknowledged)
        values (b, '2026-08-30-v1', true);
    exception when insufficient_privilege or check_violation then
        denied := true;
    end;
    raise notice 'CHECK A cannot insert as B ............ %',
        case when denied then 'PASS (denied)' else 'FAIL (INSERT ALLOWED)' end;

    -- ---------- act as User B ----------
    perform set_config('request.jwt.claims',
        json_build_object('sub', b, 'role', 'authenticated')::text, true);

    select count(*) into seen from public.user_terms_acknowledgements where user_id = a;
    raise notice 'CHECK B cannot read A''s row ........... %',
        case when seen = 0 then 'PASS (invisible)' else 'FAIL (B saw ' || seen || ')' end;

    update public.user_terms_acknowledgements set acknowledged = false where user_id = a;
    get diagnostics touched = row_count;
    raise notice 'CHECK B cannot update A''s row ......... %',
        case when touched = 0 then 'PASS (0 rows)' else 'FAIL (' || touched || ' updated)' end;

    -- No DELETE policy exists, so a delete must affect nothing.
    delete from public.user_terms_acknowledgements where user_id = a;
    get diagnostics touched = row_count;
    raise notice 'CHECK delete is not permitted ......... %',
        case when touched = 0 then 'PASS (0 rows)' else 'FAIL (' || touched || ' deleted)' end;

    raise exception 'VERIFICATION COMPLETE - rolling back (this is expected)';
end $$;
-- The final raise rolls the whole block back: nothing above is persisted.
