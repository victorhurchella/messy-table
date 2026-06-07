# Heuristics

Every heuristic in messy-table, what signal it uses, and the thresholds it trips
on. Thresholds live as named constants in code; this file is the prose companion.
When you change a threshold, update both.

A shared idea runs through all of them: produce a **confidence** in `[0, 1]`.
Below `Config.confidence_threshold` (default **0.6**) the decision is *ambiguous*
— a warning in permissive mode, an `AmbiguityError` (with a `Config` suggestion)
in strict mode.

## Density, merge-aware (shared primitive)

`util.merge_covered_cells` + `util.density_threshold`.

A row's *filled count* = non-blank cells **plus** cells covered by a **row-spanning**
merge (vertical/block). Horizontal one-row merges (banners) are excluded so titles
stay sparse.

`density_threshold(width, ratio=0.5)`:
- width 1 → **1** (single-column tables are real).
- width ≥ 2 → `max(2, ceil(0.5 · width))` (a lone stray cell never counts as data).

## F1 — table start (`detectors/table_start.py`)

- Compute the merge-aware filled count per row; `width` = the max across rows.
- A row is *substantial* if its filled count ≥ `density_threshold(width)`.
- The table starts at the first row of the **longest contiguous run** of
  substantial rows. (A blank row between a metadata block and the table breaks the
  run, so the longer table run wins.)
- Confidence = `clamp(body_density − above_density + 0.5)`. Skipping rows with a
  sparse preamble is high-confidence; skipping into a still-dense region is not.
- `Config(header=<int>)` pins the start and bypasses detection.

**Known limit:** a metadata block *immediately* above the table with no blank
separator and the same column count can be absorbed. A blank separator (the common
real case) resolves it; otherwise pin `header`.

## F2 — header (`detectors/header.py` + `transformers/header_names.py`)

Detection (grid already body-sliced and unmerged, so the header is at row 0):

- **Headerless?** If row 0 is not text-heavy (`text_ratio < 0.5`), has no
  horizontal merge, and shares the exact per-column category signature of row 1,
  there is no header → synthesise `column_1…` and start data at row 0 (warned).
- **How many header rows?** Start at 1. While the current top header row intersects
  a **horizontal merge** (a spanned group cell), consume the next row too — up to
  `MAX_HEADER_ROWS` (3). This ties multi-row detection to real structure rather
  than a fragile text test.
- Confidence: 0.9 if row 0 is text-heavy, else 0.55.

Naming (`header_names.py`): NFKD accent-strip → lowercase → non-word → `_` →
collapse/trim. Empty → `column_{i}`; leading digit → `col_…`; duplicates get
`_2`, `_3`. Every rename is recorded.

## F3 — merged cells (`transformers/merged_cells.py`)

`fill` (default): copy each merge's anchor value to every other cell in its range.
`first-only`: leave them `None` (openpyxl's default) — a no-op. Each filled cell is
recorded. Skipped on very large (streaming) sheets, with a warning.

## F4 — Excel serial dates (`transformers/dates.py`)

Date-formatted xlsx cells already arrive as `datetime` (openpyxl applies the
epoch). F4 targets the *messy* case: a column of **bare numbers** that are really
dates. Converted only when **both** hold:

1. every value sits in the serial range **20000–60000** (≈ 1954–2064), **and**
2. there is corroboration — the cell's number format looks like a date
   (`fmt_is_date`, confidence **0.9**) **or** the column name hints at a date
   (`data`, `vencimento`, `date`, … → confidence **0.7**).

Bare numbers with no hint are left numeric (so an `ano`/`year` column survives).
Conversion uses the workbook epoch (1899-12-30 base absorbs the 1900 leap bug;
1904-01-01 for Mac). Integer serial → `date`; fractional → `datetime`.

## F5 — localised numbers (`transformers/numbers.py`)

Only columns where ≥ **70%** (`NUMERIC_COLUMN_RATIO`) of non-blank string cells look
numeric are treated as numeric. Per-value *decimal vote*:

- both `.` and `,` present → the **last** one is the decimal point;
- one separator present → it is *thousands grouping* only if it splits into clean
  3-digit runs (`1.234`, `12.345.678`), otherwise it is the decimal point.

The column's majority vote picks the convention; confidence = winner / total votes
(so a 50/50 split → 0.5, below threshold → ambiguous). `Config(locale=…)` overrides
the vote (confidence 1.0). Currency symbols, spaces, NBSP, apostrophes and a
trailing `%` (divide by 100) are handled.

## F6 — column types (`transformers/types.py`)

Per column, over surviving non-null values:

- all `date`/`datetime` → `date`, or `datetime` if any carry a time (bare dates are
  promoted to datetime for uniformity);
- all `int` → `int`; any fractional → `float`;
- all boolean (native or text tokens `true/false/sim/não/yes/no/…`) → `bool`;
- otherwise → `str` (lossless fallback, with a "mixes types" warning when the column
  genuinely mixed numbers and text).

## F7 — disguised nulls (`transformers/nulls.py`)

Case-insensitive, trimmed match against the built-in token set (`-`, `--`, `n/a`,
`n/d`, `null`, `none`, `nil`, `nan`, and the Excel error literals `#REF!`,
`#DIV/0!`, `#VALUE!`, …) plus `Config.null_values_extra`. Matches become `None`.

## F8 — trailing junk (`detectors/table_end.py`)

Walk up from the bottom; trim a row while it is **sparse** (below the body density
threshold), **empty**, or starts with a **summary keyword** (`total`, `subtotal`,
`soma`, `fonte`, `gerado em`, `assinatura`, …). Stop at the first real data row.
Confidence 0.85 when a keyword matched, else 0.7.

## CSV delimiter & encoding (`readers/csv.py`)

- **Encoding:** decode cascade `utf-8-sig` → `cp1252` → `latin-1` (the last never
  fails). The first that decodes wins.
- **Delimiter:** structural, not `csv.Sniffer` (which preamble rows fool). For each
  candidate (`, ; \t |`) score by how many lines share a modal field count ≥ 2,
  requiring at least half the lines to split. Best agreement wins; ties broken by
  more fields. If nothing qualifies → **single column** (a lone decimal comma is not
  a delimiter). `.tsv` forces tab.
