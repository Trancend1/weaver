"""Textual-based read-only TUI dashboard mirroring `weaver inspect`."""

from __future__ import annotations

from pathlib import Path

from weaver.errors import ConfigError


def _require_textual() -> None:
    try:
        import textual  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as exc:
        raise ConfigError(
            "weaver dashboard requires textual. "
            "Likely cause: optional dependency not installed. "
            "Next command: pip install 'weaver[tui]'"
        ) from exc


def run_dashboard(project_toml: Path, *, no_color: bool = False) -> None:
    """Launch the Textual TUI dashboard for a Weaver project.

    Raises:
        ConfigError: When textual is not installed.
    """
    _require_textual()

    from textual.app import App, ComposeResult  # type: ignore[import-not-found]
    from textual.widgets import DataTable, Footer, Header, Label  # type: ignore[import-not-found]

    from weaver.services.project import inspect_project

    class WeaverDashboardApp(App):  # type: ignore[type-arg]
        BINDINGS = [("r", "refresh", "Refresh"), ("q", "quit", "Quit")]
        CSS = """
        Screen { background: #1e1e1e; }
        DataTable { height: auto; }
        Label { color: #ffffff; margin: 1; }
        """

        def __init__(self, toml_path: Path, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self._toml_path = toml_path

        def compose(self) -> ComposeResult:
            yield Header()
            yield Label("Loading…", id="status")
            yield DataTable()
            yield Footer()

        def on_mount(self) -> None:
            self._load()

        def _load(self) -> None:
            try:
                summary = inspect_project(self._toml_path)
            except Exception as exc:  # noqa: BLE001
                self.query_one("#status", Label).update(f"Error: {exc}")
                return

            table = self.query_one(DataTable)
            table.clear(columns=True)
            table.add_columns("Field", "Value")
            pct = (
                round(100 * summary.translated_count / summary.segment_count)
                if summary.segment_count
                else 0
            )
            table.add_rows(
                [
                    ("Project", summary.project_name),
                    ("Chapters", str(summary.chapter_count)),
                    ("Segments", f"{summary.segment_count} ({pct}% done)"),
                    ("Translated", str(summary.translated_count)),
                    ("Failed", str(summary.failed_count)),
                    ("Glossary terms", str(summary.glossary_term_count)),
                ]
            )
            self.query_one("#status", Label).update(f"Project: {summary.project_name}")

        def action_refresh(self) -> None:
            self._load()

        def action_quit(self) -> None:
            self.exit()

    WeaverDashboardApp(project_toml, no_color=no_color).run()
