"""PyInstaller entrypoint for the Weaver desktop sidecar.

This file is packaging glue only. It imports the existing Typer CLI and keeps the
runtime command surface identical to the installed `weaver` console script.
"""

from __future__ import annotations

from weaver.cli.main import app

if __name__ == "__main__":
    app(prog_name="weaver")
