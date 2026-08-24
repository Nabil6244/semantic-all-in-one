"""Build-time Supabase credentials (public anon key + project URL).

CI overwrites these via scripts/embed_supabase.py before PyInstaller.
Local/dev: leave empty and set SUPABASE_URL / SUPABASE_ANON_KEY in the environment.
"""

SUPABASE_URL = ""
SUPABASE_ANON_KEY = ""
