"""Typer entry point for the `weaver` command."""

from __future__ import annotations

import typer

from weaver import __version__

app = typer.Typer(
    name="weaver",
    help="Offline-capable, glossary-aware JP-EN novel translation workbench.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"weaver {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Weaver CLI root."""


if __name__ == "__main__":
    app()
