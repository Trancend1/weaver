# Weaver Benchmarks

Performance baseline for the v0.1.0 release candidate.

## Fixture

- Fixture: `tests/fixtures/synthetic_200_chapter.epub`
- Shape: 200 chapters, 50 text blocks per chapter, 10,000 total blocks
- Generator: `bench/generate_synthetic_fixture.py`
- Runner: `bench/run_performance_budgets.py`

## Latest Run

| Operation | Budget | Measured | Result | Notes |
|---|---:|---:|---|---|
| weaver init | < 30 s | 2.25 s | PASS | 200 chapters / 10,000 blocks |
| glossary extraction | < 20 s | 1.95 s | PASS | same 200-chapter fixture, extraction only |
| weaver inspect | < 1 s | 0.01 s | PASS | 10,000-segment project |
| resume scan on startup | < 5 s | 0.08 s | PASS | 10,000 reset rows |
| weaver translate fake provider | < 50 ms/segment | 5.63 ms/segment | PASS | 5.63 ms/segment over 10,000 segments |
| weaver export markdown | < 10 s | 0.43 s | PASS | 10,000 segments |
| weaver export epub | < 30 s | 0.71 s | PASS | 10,000 segments |
| weaver validate | < 15 s | 0.09 s | PASS | 10,000 segments |
| SQLite DB size | - | - | N/A | 5.95 MB < 100 MB |
| weaver status | < 1 s | - | N/A | Not an MVP-0 command; `weaver inspect` is the status surface. |

## Reproduce

```powershell
uv run python -m bench.generate_synthetic_fixture
uv run python -m bench.run_performance_budgets --write-doc
```

Budgets come from `docs/SECURITY_AND_PERFORMANCE.md`.
`weaver status` is listed there as a future/status surface budget,
but MVP-0 ships `weaver inspect` as the user-facing status command.
