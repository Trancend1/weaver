"""FastAPI cockpit for Weaver (the web cockpit; ADR 004).

This package is the Cockpit backend. It must stay a thin adapter layer: domain
logic lives in ``weaver.services`` / ``weaver.storage`` / ``weaver.core`` and is
consumed here, never reimplemented.
"""
