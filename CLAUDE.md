# messy-table — project context

Product-specific context for working in this repo. Universal team standards live
in the global `~/.claude/CLAUDE.md`; this file is only what is specific to
messy-table.

## What it is

A Python library that turns messy real-world spreadsheets (Excel/CSV from ERPs,
legacy systems, hand-made reports) into clean, typed data **plus an auditable
report of every fix**. Pitch: `pandas.read_excel` assumes your sheet is
well-behaved; messy-table assumes it is not. Public API is one function: `clean()`.

This is a **zero-infrastructure library** — no server, DB, container, or network.
The threat model is *untrusted files*. Do not add Docker/Compose/CORS/auth; they
do not apply here.

## Stack (decided — do not relitigate without reason)

- Python ≥ 3.10, `src/` layout, full type hints, ships `py.typed`.
- **openpyxl is the only runtime dependency.** pandas is an *optional* extra
  (`messy-table[pandas]`) used solely by `to_pandas()`. Keep the core light.
- hatchling (build) · ruff (lint+format+security) · mypy `--strict` · pytest.

## Architecture (see ARCHITECTURE.md for the full picture)

Pipeline in [src/messy_table/api.py](src/messy_table/api.py):
`read → detect start → detect end → slice → unmerge → detect header → name →
nulls → numbers → dates → finalize types → emit`.

- `readers/` — source → `Grid`; the untrusted-input boundary and the only place
  `Any` is allowed (openpyxl is unstubbed).
- `detectors/` — locate structure, record confidence, **never mutate values**.
- `transformers/` — mutate values, **record every change**.
- `grid.py` — dense value matrix + sparse metadata (don't allocate per-cell objects).
- `report.py` / `context.py` — audit trail + strict/permissive decision (`ctx.ambiguous`).

## Domain glossary

- **Grid** — the in-memory matrix every stage operates on.
- **Detector** — finds where the table/header/data starts and ends.
- **Transformer** — applies one class of fix (nulls, numbers, dates, …).
- **CleanReport / Action / Issue** — the audit trail; `Action` is a recorded
  change, `Issue` is a low-confidence warning.
- **Gabarito** — the expected clean output for a fixture (`tests/_fixtures.py`).
- **Serial date** — an Excel date stored as a number (e.g. `45123` = 2023-07-16).
- **Locale inference** — deciding `1.234,56` vs `1,234.56` per *column*.
- **Epoch** — Excel's 1900 vs 1904 date origin.

## Non-negotiable invariants (baseline-ready — hardened, never loosened)

1. **Nothing changes without a report entry.** Every transformer records its work;
   per-cell changes aggregate per column with an *exact* count. There is a test.
2. **Heuristics carry explicit confidence**; below threshold → warn (permissive) or
   raise `AmbiguityError` *with a `Config` suggestion* (strict). Never fail silently.
3. **Core stays dependency-light** — adding a runtime dependency needs a real reason.
4. **Determinism** — no LLM, no randomness, no clock-dependence in the core.
5. Quality gates (CI-enforced): `ruff check`, `ruff format --check`, `mypy --strict`
   clean; **coverage ≥ 90%** (`fail_under` in pyproject); the **50k × 30 < 5s** perf
   gate passes; zero bare/broad `except` (ruff `BLE`).
6. **Security guards in readers are mandatory** — decompression-bomb and cell-count
   limits run before parsing untrusted input.

## Conventions

- Fixtures are **generated deterministically** from `tests/_fixtures.py` (no binary
  blobs); each new feature gets a fixture + gabarito and an end-to-end assertion.
- New heuristic or threshold → document it in `docs/heuristics.md` (prose) with the
  constant in code (source of truth).
- Run `pytest -m "not perf"` for fast loops; full `pytest` before shipping.
