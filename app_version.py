"""Single source of the app version.

Read by the macOS bundle (VideoGenerator.spec), recorded with each Supabase
generation event (licensing/generation_tracking.py). Keep
scripts/windows_setup.iss MyAppVersion equal to this (test_app_version.py
checks it).
"""

APP_VERSION = "1.1.0"
