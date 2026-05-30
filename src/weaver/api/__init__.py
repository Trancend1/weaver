"""FastAPI cockpit for Weaver (target direction, runs parallel to Flask baseline).

This package is the new Cockpit backend (ADR 004). It must stay a thin adapter
layer: domain logic lives in ``weaver.services`` / ``weaver.storage`` /
``weaver.core`` and is consumed here, never reimplemented. It must not import
Flask (``weaver.web``).
"""
