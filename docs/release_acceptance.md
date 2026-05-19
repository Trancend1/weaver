# Weaver v0.1.0 Release Acceptance

Hands-on pass for `PRD_v2.md` AC-1 through AC-9.

| Criterion | Status | Evidence |
|---|---|---|
| AC-1 weaver init | PASS | project.toml, weaver.db, glossary_candidates.tsv created; 6 segments; deterministic IDs=True; Next hint present=True; elapsed=0.04s |
| AC-2 weaver inspect | PASS | required fields present=True; database unchanged=True; elapsed=0.01s |
| AC-3 glossary review | PASS | examples shown=True; approve/edit/reject/skip/undo/q flows exited cleanly; status counts={'approved': 1, 'edited': 1}; progress persisted |
| AC-4 weaver translate | PASS | conflict exit=6; resume from in_progress translated all; retry_failed exit=0; counts={'translated': 6}; elapsed=0.02s; output contains Selected=True |
| AC-5 weaver edit | PASS | edit exit=0; manual text persisted='Manual override from acceptance gate.'; missing id exit=5; retry preserves manual=True; retry exit=0 |
| AC-6 export markdown | PASS | default exit=0; translation-only exit=0; review exists=True; chapter files=2 |
| AC-7 export epub | PASS | exit=0; output exists=True; title=Aozora Weaver Sample; spine items=2 |
| AC-8 weaver validate | PASS | clean exit=0; critical exit=1; json keys=['findings', 'project', 'summary', 'total_segments']; critical=1 |
| AC-9 error handling | PASS | provider unavailable exit=3; unreadable EPUB exit=4; config parse exit=7; messages include likely cause and next command |

## Reproduce

```powershell
uv run python -m bench.run_acceptance_gate --write-doc
```
