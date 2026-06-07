# Architecture

This document explains every significant decision so a senior engineer can
understand the project in ten minutes.

## What this is

A **zero-infrastructure Python library**. No server, no database, no network, no
container. That single fact shapes everything below: the threat model is
*untrusted files*, not network attackers; "deploy" means *publish to PyPI*, not
*run a service*. Sections of a generic project template that assume a service
(Docker Compose, CORS, auth, health checks) do not apply and are deliberately
absent — adding them would be ceremony, not safety.

## Stack and why

| Choice | Decision | Rationale |
|---|---|---|
| Language | Python ≥ 3.10 | The ecosystem the target users (data/AI engineers) already live in. 3.10 unlocks `X | Y` types and structural niceties while staying broadly available. |
| Core dependency | **openpyxl only** | The mature, maintained, pure-Python `.xlsx` reader. It returns epoch-correct datetimes, exposes number formats and merged ranges, and supports read-only streaming. Reimplementing xlsx parsing would be slower to correctness and a security liability. It is the *only* mandatory dependency — the core installs tiny. |
| CSV/encoding | **stdlib only** (`csv`, `codecs`) | No `chardet`/`pandas` needed for the 80% case (UTF-8/cp1252/Latin-1 + common delimiters). Keeps the dependency surface minimal. |
| pandas | **optional extra** | `to_pandas()` is a convenience, never a requirement. Forcing pandas on every user would bloat installs and contradict the "light core" principle. |
| Build | hatchling | Modern, standards-based (PEP 517/621), no `setup.py`. |
| Lint/format | ruff | One fast tool for lint + format + import sorting + security (bandit) rules. |
| Types | mypy `--strict` + `py.typed` | The public surface is fully typed and ships its types. The only `Any` boundary is the openpyxl interface, isolated in the readers. |
| Tests | pytest + reproducible fixtures | Fixtures are generated deterministically (see `tests/_fixtures.py`) so there are no binary blobs to drift, and each carries its gabarito. |

## The pipeline

`clean()` ([api.py](src/messy_table/api.py)) runs a sequence of small, pure-ish
stages. Each stage does one thing and records what it did.

```
read ─▶ detect table start ─▶ detect table end ─▶ slice to body
     ─▶ unmerge (F3) ─▶ detect header (F2) ─▶ name header ─▶ slice off header
     ─▶ nulls (F7) ─▶ numbers (F5) ─▶ dates (F4) ─▶ finalize types (F6)
     ─▶ emit CleanResult + CleanReport
```

### Why this order

- **Detectors run before unmerging.** openpyxl reports a merged cell's value only
  in its top-left anchor, so a full-width merged *title banner* reads as a single
  filled cell and stays sparse — exactly what start-detection needs to skip it.
  If we unmerged first, the banner would fill the row and look like data.
- **Density is merge-aware** ([util.py](src/messy_table/util.py)
  `merge_covered_cells`). A *vertically* merged cell (a category spanning rows) is
  counted as filled even before unmerging, so a trailing category row is not
  mistaken for junk. A *horizontal* banner is not, so titles still get skipped.
- **Unmerge happens before header detection** so a merged group header (`Vendas`
  over `2023`/`2024`) is filled and can be combined column-wise.
- **Nulls run before numbers/dates** so `N/A` becomes `None` and does not poison a
  column's type (the "95% numeric + a few N/A → numeric" case).
- **Type finalisation runs last**, once values are their real Python types.

### Modules

| Module | Responsibility |
|---|---|
| [grid.py](src/messy_table/grid.py) | `Grid`: a dense value matrix + *sparse* metadata (number formats, bold, merged ranges). Sparse metadata avoids allocating a wrapper per cell on large sheets. |
| [readers/](src/messy_table/readers/) | Source → `Grid`. The untrusted-input boundary and the only place `Any` enters. |
| [detectors/](src/messy_table/detectors/) | Locate structure (start/header/end). They decide and record confidence; they never mutate values. |
| [transformers/](src/messy_table/transformers/) | Mutate values and record every change. |
| [report.py](src/messy_table/report.py) | `CleanReport`, `Action`, `Issue`, `ColumnInfo`, and the `ReportBuilder` that aggregates per-cell changes. |
| [context.py](src/messy_table/context.py) | The shared pipeline state; centralises the strict-vs-permissive decision (`ctx.ambiguous`). |

## The audit trail

The core contract is **nothing changes without a record**. Two shapes of record:

- **Structural** (table start, header, trimming): one `Action` with a human-readable
  `detail` and a confidence.
- **Per-cell** (nulls, numbers, dates, coercions): aggregated per
  `(kind, column, rule)` into one `Action` carrying an exact `count` and up to
  `EXAMPLE_CAP` sample locations. This keeps a 50k-row file's report small while
  staying exact — the test suite asserts the count equals the cells changed.

## Confidence, strict mode, warnings

Every heuristic produces a confidence in `[0, 1]`. Below
`Config.confidence_threshold` (default 0.6) the decision is *ambiguous*: in
permissive mode it becomes a `warnings` entry; in `strict=True` it raises
`AmbiguityError` — always carrying a copy-pasteable `Config` suggestion. Thresholds
are documented in [docs/heuristics.md](docs/heuristics.md).

## Security (threat model: untrusted files)

- **Decompression bombs.** `.xlsx` is a ZIP. Before openpyxl opens it, we sum the
  archive's declared uncompressed sizes and check both an absolute cap
  (`max_uncompressed_bytes`, 512 MiB) and a ratio cap (`max_compression_ratio`,
  200×). A bomb is rejected with `UnsupportedFormatError`.
- **Memory/CPU ceiling, enforced during the read.** `max_cells` (5M) is checked as
  rows are streamed, not from the sheet's declared `<dimension>` (which is
  attacker-controlled) — so a lying dimension cannot smuggle a huge sheet past the
  cap. Oversized text input is rejected up front.
- **Merge amplification.** openpyxl materialises a `MergedCell` per merged cell, so
  a crafted file with thousands of large *overlapping* merges would cost O(total
  merged area) — tens of seconds. Excel forbids overlaps, so a valid sheet's merge
  area never exceeds its own cell count; we pre-scan the declared merge area and,
  if it exceeds the sheet, read merge-free with a warning. (Found and fixed via an
  adversarial security pass; regression-tested in `tests/test_security.py`.)
- **XML entities.** openpyxl's parser does not resolve external entities or DTDs,
  so XXE / billion-laughs via the embedded XML is not reachable through our usage.
- **No secrets, no env, no network.** There is nothing to leak. `.env*` is
  git-ignored defensively, but the library neither reads env nor makes calls.
- **No bare/broad excepts** (enforced by ruff `BLE`); errors are typed and
  actionable.

## Performance

Acceptance gate: 50k × 30 in < 5 s. We always stream values via read-only
`values_only` first (fast, low-memory, and it never triggers openpyxl's
dimension scan); small, well-formed sheets are then re-read with styles to pick up
merges/number-formats/bold. Sheets above `LARGE_SHEET_CELLS` (200k) stay on the
stream and emit a warning that merged-cell propagation is skipped at that scale. A
realistic 50k × 30 file reads in ~3.5 s. See [tests/test_perf.py](tests/test_perf.py).

**openpyxl quirk worth knowing:** an `.xlsx` *missing* its `<dimension>` tag forces
openpyxl to parse the sheet XML twice (once to size it, once to read), ~50% slower.
Every file from Excel/Sheets/LibreOffice/normal-openpyxl carries the tag; only
some `write_only`-generated files omit it. If dimension-less large files ever need
to hold the budget, a self-parsed value reader (or a `python-calamine` fast-path
extra) is the v0.2 lever.

## How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'        # or: uv pip install -e '.[dev]'

pytest                          # full suite incl. the perf gate
pytest -m "not perf"            # fast loop
ruff check . && ruff format --check .
mypy
```

## Deliberate scope (v0.1)

Out of scope by design: legacy `.xls`, `.ods`, Google Sheets, multiple tables per
sheet, semantic content fixing, any LLM call, and a CLI. The roadmap in the README
sequences these. The library stays small and the public API is one function.
