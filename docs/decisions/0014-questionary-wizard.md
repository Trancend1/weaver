# 0014: Questionary for weaver new Wizard

Date: 2026-05-23
Status: accepted

## Context

`weaver init <epub>` creates a project but requires the user to know the provider name, edit `project.toml` manually, and understand template names. First-time users have no guidance. An interactive wizard that asks each question in sequence lowers the barrier to a first successful run. The wizard requires a TTY and an interactive-prompt library; forcing it on users who script Weaver would be wrong.

## Decision

Add `weaver new` backed by `questionary`, shipped as an optional extra `[wizard]`. The wizard steps: path to EPUB → provider → template → working directory. It returns a `WizardAnswers` dataclass; the CLI calls `initialize_project()` with those answers and prints the same output as `weaver init`.

`questionary` is declared under `[project.optional-dependencies] wizard = ["questionary>=2.0"]`. The CLI defers `from weaver.services.wizard import run_new_wizard` to inside the command function body. A `_require_questionary()` guard raises `ConfigError` with an install hint when the package is absent.

`run_new_wizard()` is a pure function: it asks questions and returns `WizardAnswers`. The CLI owns the `initialize_project()` call. This separation lets tests inject answers without a TTY by monkeypatching `run_new_wizard`.

## Consequences

Easier: first-time users can create a project without knowing provider names or template slugs. The wizard is optional — power users continue using `weaver init` directly.

Harder: `questionary` prompts hang when stdin is not a TTY (e.g., piped input in CI). Integration tests must mock `run_new_wizard` rather than drive the interactive prompts through `CliRunner`. Users must install the `[wizard]` extra explicitly.
