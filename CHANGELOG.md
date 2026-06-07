# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-06-06

The first release. A complete, deterministic cleaning pipeline with a full audit
trail.

### Added

- `clean(source, *, config=None)` — the single public entry point. Accepts a
  path, raw `bytes`, or a binary/text file-like object.
- **Readers**: `.xlsx` (openpyxl), `.csv` and `.tsv` with delimiter and encoding
  (UTF-8 / cp1252 / Latin-1) sniffing.
- **F1** table-start detection (skips titles, banners, metadata, blank rows).
- **F2** header detection + normalisation: multi-row merged headers, duplicate
  (`valor`, `valor_2`), empty (`column_3`) and leading-digit (`col_2024`) names,
  slugified to `snake_case`.
- **F3** merged cells: `fill` (propagate) or `first-only`.
- **F4** Excel serial dates with both 1900 and 1904 epochs.
- **F5** localised numbers (`1.234,56` vs `1,234.56`) inferred per column.
- **F6** per-column type inference: `int`, `float`, `date`, `datetime`, `bool`,
  `str`, with mixed-column handling.
- **F7** disguised nulls (`-`, `N/A`, `#REF!`, `#DIV/0!`, …) → `None`, extensible.
- **F8** trailing-junk trimming (totals, signatures, footnotes).
- **F9** `CleanReport` — JSON-serialisable, every fix recorded with location and
  confidence; per-cell fixes aggregated per column with counts and samples.
- `CleanResult.to_pandas()` via the optional `messy-table[pandas]` extra.
- `Config` for locale, header, sheet, merge mode, extra null tokens, strict mode,
  and the file-safety limits.
- `strict=True` raises `AmbiguityError` (always with a `Config` suggestion) where
  permissive mode would warn.

### Security

- Decompression-bomb defence for `.xlsx`: absolute uncompressed-size and
  compression-ratio limits checked before openpyxl opens the archive.
- Hard cell ceiling (`Config.max_cells`) and text-size limit bound memory.

[0.1.0]: https://github.com/messy-table/messy-table/releases/tag/v0.1.0
