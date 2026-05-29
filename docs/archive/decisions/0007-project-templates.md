# 0007: Project Templates

Date: 2026-05-23
Status: accepted

## Context

Different novel genres benefit from different glossary extraction and QA thresholds. Light novels use many katakana loanwords and honorifics; web novels are shorter with informal prose; Aozora Bunko texts are classical with dense kanji. Requiring users to hand-tune `[glossary]` and `[qa]` knobs for each genre adds friction to `weaver init`.

## Decision

Add `weaver init --from-template <name>` with three built-in presets:

| Template         | `max_terms_per_segment` | `require_review` | `minimum_length_ratio` | Notes                              |
|------------------|-------------------------|-------------------|------------------------|------------------------------------|
| `light-novel`    | 30                      | true              | 0.25                   | Generous glossary, relaxed ratio   |
| `web-novel`      | 15                      | false             | 0.2                    | Smaller glossary, auto-approve     |
| `aozora-classic` | 40                      | true              | 0.4                    | Dense kanji, strict QA             |

Templates are frozen dicts in `src/weaver/core/templates.py`. They override the `[glossary]` and `[qa]` sections of the generated `project.toml` while leaving `[provider]`, `[translation]`, `[output]`, and `[logging]` at defaults. When `--from-template` is omitted, the current default TOML is generated unchanged (wire-compatible).

Template names are validated at init time. Unknown names raise `ConfigError`.

## Consequences

**Easier:** Genre-appropriate defaults out of the box. New presets are one dict addition — no new modules.

**Harder:** Template knobs are frozen at init time; changing a template does not retroactively update existing projects. Users must re-init or hand-edit. This is intentional — projects own their config after creation.
