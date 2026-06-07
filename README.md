# messy-table

> `pandas.read_excel` assumes your spreadsheet is well-behaved. **messy-table assumes it is not.**

Turn messy real-world spreadsheets — Excel/CSV exported from ERPs, legacy systems,
hand-made reports — into clean, typed data, and get back an **auditable report of
every fix that was applied**.

```python
from messy_table import clean

result = clean("relatorio_vendas.xlsx")

result.data        # list[dict] — clean, typed rows
result.columns     # per-column name / dtype / null summary
result.report      # every transformation that was applied
result.warnings    # low-confidence decisions
result.to_pandas() # DataFrame (optional extra)
```

## Why

AI agents and data pipelines receive arbitrary spreadsheets from users and today
re-implement, by hand and fragilely, the same heuristics: find where the table
starts, fix the headers, convert Excel serial dates, interpret `1.234,56`.
messy-table is the canonical answer to that step — deterministic, dependency-light,
and fully auditable.

## Install

```bash
pip install messy-table            # core — depends only on openpyxl
pip install 'messy-table[pandas]'  # adds result.to_pandas()
```

Python ≥ 3.10. Ships `py.typed` — fully type-checked.

## Before & after

A typical ERP export — a title banner, a blank row, pt-BR numbers, an `N/A`, and a
trailing totals row:

```
Relatório de Vendas 2024
(gerado em 01/02/2024)

Produto      | Valor (R$) | Qtd | Ativo
Café         | 1.234,56   | 10  | sim
Chá          | 2.000,00   | 5   | nao
Açúcar       | -          | 3   | sim
TOTAL        | 3.234,56   | 18  |
```

```python
>>> result = clean("vendas.xlsx")
>>> result.data
[{'produto': 'Café',   'valor_r': 1234.56, 'qtd': 10, 'ativo': True},
 {'produto': 'Chá',    'valor_r': 2000.0,  'qtd': 5,  'ativo': False},
 {'produto': 'Açúcar', 'valor_r': None,    'qtd': 3,  'ativo': True}]
>>> [(c.name, c.dtype) for c in result.columns]
[('produto', 'str'), ('valor_r', 'float'), ('qtd', 'int'), ('ativo', 'bool')]
```

The title, blank row and `TOTAL` line are gone; numbers are parsed in the column's
inferred locale; `-` is a null; `sim/nao` became booleans — and the report says so.

## Features (v0.1)

| Feature | What it does |
|---|---|
| **Table-start detection** | Skips titles, logos, stray cells and metadata before the real header. |
| **Header detection & normalisation** | Finds the header (or its absence); resolves duplicate/empty/multi-row headers; slugifies to `snake_case`. |
| **Merged cells** | Propagates a merged value across its range (`fill`) or keeps it top-left only (`first-only`). |
| **Excel serial dates** | Converts `45123` → a real date when the column has a date profile (both 1900 and 1904 epochs). |
| **Localised numbers** | `1.234,56` (pt-BR/EU) vs `1,234.56` (en-US), inferred per **column**, never per cell. |
| **Column type inference** | `int`/`float`/`date`/`datetime`/`bool`/`str`, with mixed-column handling. |
| **Disguised nulls** | `-`, `N/A`, `n/d`, `#REF!`, `#DIV/0!`, blanks → `None` (extensible). |
| **Trailing junk** | Removes totals, signatures and footnotes after the data ends. |
| **Cleaning report** | Structured, JSON-serialisable record of every correction with location and confidence. |
| **Input formats** | `.xlsx`, `.csv` (delimiter + encoding sniffing), `.tsv`. |

## The report

Nothing changes without a record. Per-cell fixes are aggregated per column with a
count and sample locations, so the report stays small even on huge files:

```python
>>> print(result.report.to_json())
{
  "summary": {"table_start_detected": 1, "table_end_trimmed": 1,
              "header_renamed": 1, "null_normalized": 1,
              "number_parsed": 4, "type_coerced": 2},
  "actions": [
    {"kind": "table_start_detected", "rule": "density", "confidence": 0.8,
     "detail": "skipped 3 leading row(s) (title/metadata/blank); table starts at row 3"},
    {"kind": "number_parsed", "rule": "locale:pt_BR", "column": "valor_r",
     "count": 4, "confidence": 1.0,
     "examples": [{"row": 0, "original": "1.234,56", "final": 1234.56}]},
    ...
  ]
}
```

## Configuration

The 80% case needs no config. For the rest:

```python
from messy_table import clean, Config

result = clean(
    "dados.csv",
    config=Config(
        locale="pt_BR",            # force number/date interpretation; default "auto"
        header="auto",             # "auto" | int (row index) | None (no header)
        sheet=0,                   # index or name of the worksheet
        merged_cells="fill",       # "fill" | "first-only"
        null_values_extra=["s/i"], # add to the built-in null list
        strict=False,              # True: raise AmbiguityError instead of warning
    ),
)
```

In `strict=True`, a low-confidence decision raises `AmbiguityError` — always with a
copy-pasteable `Config` suggestion to resolve it.

## Security

messy-table parses untrusted files, so it defends against it: `.xlsx` archives are
checked for decompression-bomb shape (absolute size and ratio) **before** they are
opened, and a hard cell ceiling bounds memory. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — pipeline, stack rationale, security decisions.
- [docs/heuristics.md](docs/heuristics.md) — every heuristic and its thresholds.

## License

MIT — see [LICENSE](LICENSE).
