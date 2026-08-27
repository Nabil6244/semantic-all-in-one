"""Shared dark production-workstation design tokens for Semantic YT Studio."""

from __future__ import annotations

# Canvas / panels
BG = "#0B0D10"
PANEL = "#12151A"
PANEL_ALT = "#0F1218"
CARD = "#181C24"
CARD_HOVER = "#1E2430"
ROW_ALT = "#141820"
BORDER = "#2A3140"

# Text
TEXT = "#E8EAED"
MUTED = "#8B95A8"

# Accent (restrained indigo)
ACCENT = "#4F6BF6"
ACCENT_HOV = "#3D56E8"
ACCENT_DARK = "#FFFFFF"
ACCENT_SEL = "#1A2240"
ACCENT_BORDER = "#3D5080"

# Status
SUCCESS = "#34D399"
PROCESSING = "#60A5FA"
QUEUED = "#64748B"
WARNING = "#FBBF24"
DANGER = "#F87171"
DANGER_BG = "#2A1A1A"
SKIPPED = "#6B7280"
STEPPER_DONE = "#2F8F6E"

# Layout
SIDEBAR_WIDTH = 148
INSPECTOR_WIDTH = 260
TOPBAR_HEIGHT = 44
STATUSBAR_HEIGHT = 32
PAD = 10
PAD_SM = 6
PAD_LG = 14
RADIUS = 4  # restrained, not pill-like

# Project is chosen from the topbar chip / Switch — not a sidebar destination.
NAV_ITEMS = (
    ("script", "Script"),
    ("brand_style", "Brand & Style"),
    ("visual_plan", "Visual Plan"),
    ("assets", "Assets"),
    ("audio", "Audio"),
    ("music", "Music"),
    ("editorial", "Editorial"),
    ("render", "Render"),
    ("qa", "QA"),
)

WORKFLOW_STEPS = ("INPUT", "PLAN", "ASSETS", "AUDIO", "EDITORIAL", "RENDER", "QA")
