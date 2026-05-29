"""Weaver local web cockpit (Phase 12).

A thin Flask layer over the existing ``services/`` core. The web package holds
no translation/glossary/export logic — it routes HTTP, manages job lifecycle,
and renders HTML. Binds ``127.0.0.1`` only (ADR ``0017``). Installed via the
optional ``weaver[web]`` extra.
"""
