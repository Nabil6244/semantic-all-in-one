# Shared learning system

Local SQLite ledger (`<store_dir>/learning.sqlite`: `~/.videogen` when packaged) -> optional upload of sanitized events -> reviewed,
style-scoped knowledge packages -> advisory text for the user's external CSV workflow. Nothing here changes a CSV, a protected
template, a render setting or code.

## Event types and where they come from
`csv_import` (user import actions only, never project reopen), `render_outcome` (full renders; id = tracker generation_id, or a local
operation id when signed out), `render_validation` (the tracker's later verdict incl. output validation), `scene_failure` (from the
project's production event log), `pre_render_failure`, `assets_outcome` (assets-only runs, never a render), `video_rating` (append-only revisions).

## Style scope (`mode/style`)
normal: `video_style.style_id` (+`editing_system`); overscaled: preset (`overscaled`, `exp_solar`); weather: its editing style;
pakmap/hybrid: `doc` when the Doc Style switch is on else `default`; starmap: `cinema` when Cinema is on else `default`;
whatif: `default` (no verified sub-style field exists). The scope is frozen when a render starts / an import happens.

## What leaves the device (only when signed in and `settings["learning_sync"]` is not false)
Per event: event_id, device_id (random install id), event_type, schema_version, occurred_at, style_scope, project_id, generation_id,
csv_sha256, and an allow-listed payload (see `learning/sync.py::REMOTE_PAYLOAD_KEYS`): counts, column names, asset-type counts, hashes,
outcome/category codes, scene id + provider key + error class, ratings, category scores, tags. Never: narration, prompts, CSV text,
paths, hostnames, tokens, error messages, **rating comments** (local only; the server also rejects a payload with `comment`).

## Server (migration `supabase/migrations/20261018000001_learning_events.sql`, NOT deployed by this change)
`learning_events`: own rows only (RLS), insert/select only, unique (user_id,event_id), payload <= 8 KB, rate limit.
`knowledge_packages`: authenticated users read `status='published'`; no client write policy. Packages are produced off-device:
`learning.analysis.build_candidates` (needs >= 3 projects, >= 8 observations, >= 20% of renders; one vote per project) ->
human `approved_rules` -> `learning.packages.build_package` -> a trusted admin inserts the row with the service role and flips
`status` to `published`. Clients only validate, hash-check and cache (keep 3 versions; `rollback`, `pin`). No publisher service exists yet.

## Using packages
`_copy_csv_prompt` shows the active package's short advisory block for the exact scope and asks whether to append it. With no valid
package the copied prompt is byte-for-byte the old one. Import-time advisories appear as `[LEARNING]` log lines, only for approved
asset-type rules with enough evidence, and never block or edit anything.

## Account model
Events upload under whichever Supabase account is signed in on that computer; the device id is not an authorization.
