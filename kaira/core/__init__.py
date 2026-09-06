"""Core package for Kaira.

Phase 5 & 7.5 modules:
- theme    — design system (Theme, Symbols, is_interactive, sym, banner art & tiers)
- ui       — Rich output helpers (panel, kv_table, data_table, success_footer,
           with_summary, render_large_banner, render_small_banner)
- prompts  — unified InquirerPy prompt wrappers (select, confirm, text, secret, fuzzy_select)
- progress — shared multi-step progress renderer (State, ProgressItem, ProgressPhase, ProgressRenderer)
- motion   — bounded, optional terminal animation (reveal, play, motion_enabled)
- ports    — dev-server port resolution and discovery (resolve_port, resolve_base_url)
- fallback_engine — renders core/fallback.py into the user's project
"""
