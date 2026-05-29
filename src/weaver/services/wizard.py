"""Interactive project-creation wizard powered by questionary (optional dep)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from weaver.errors import ConfigError


def _require_questionary() -> None:
    try:
        import questionary  # type: ignore[import-not-found]  # noqa: F401
    except ImportError as exc:
        raise ConfigError(
            "weaver new requires questionary. "
            "Likely cause: optional dependency not installed. "
            "Next command: pip install 'weaver[wizard]'"
        ) from exc


def _scaffoldable_providers() -> list[str]:
    """Built-in providers `weaver init` can scaffold (custom is set post-init)."""

    from weaver.services.project import DEFAULT_MODELS

    return sorted(DEFAULT_MODELS)


@dataclass(frozen=True)
class WizardAnswers:
    """Answers collected by the interactive new-project wizard."""

    epub_path: Path
    provider: str
    template: str | None
    working_dir: Path | None


def run_new_wizard() -> WizardAnswers:
    """Run the interactive wizard and return structured answers.

    Raises:
        ConfigError: When questionary is not installed.
    """
    _require_questionary()

    import questionary  # type: ignore[import-not-found]

    from weaver.core.templates import list_template_names

    epub_str: str = questionary.path(
        "Path to EPUB file:",
        only_directories=False,
    ).ask()
    if epub_str is None:
        raise ConfigError(
            "Wizard cancelled. "
            "Likely cause: user pressed Ctrl-C or input was interrupted. "
            "Next command: run `weaver new` again."
        )

    provider: str = questionary.select(
        "Translation provider:",
        choices=_scaffoldable_providers(),
    ).ask()
    if provider is None:
        raise ConfigError(
            "Wizard cancelled. "
            "Likely cause: user pressed Ctrl-C or input was interrupted. "
            "Next command: run `weaver new` again."
        )

    template_choices = ["none"] + list_template_names()
    template_raw: str = questionary.select(
        "Project template:",
        choices=template_choices,
    ).ask()
    if template_raw is None:
        raise ConfigError(
            "Wizard cancelled. "
            "Likely cause: user pressed Ctrl-C or input was interrupted. "
            "Next command: run `weaver new` again."
        )

    working_dir_str: str = questionary.path(
        "Working directory (leave blank to use current directory):",
        only_directories=True,
        default="",
    ).ask()

    return WizardAnswers(
        epub_path=Path(epub_str),
        provider=provider,
        template=None if template_raw == "none" else template_raw,
        working_dir=Path(working_dir_str) if working_dir_str else None,
    )
