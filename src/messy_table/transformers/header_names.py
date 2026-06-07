"""F2 (naming half) — turn raw header text into clean ``snake_case`` identifiers.

Handles the four messes the spec calls out:

* slugify ``"Vendas (R$)"`` → ``vendas_r``  (accents stripped, punctuation folded)
* fill empty headers   → ``column_3``
* de-duplicate         → ``valor``, ``valor_2``
* leading-digit names  → ``2024`` → ``col_2024``  (valid identifiers)

Every rename is recorded so the report shows the original→clean mapping.
"""

from __future__ import annotations

import re
import unicodedata

from messy_table.context import Context
from messy_table.report import ActionKind

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_MULTI_UNDERSCORE = re.compile(r"_+")


def normalize_headers(raw_names: list[str], ctx: Context) -> list[tuple[str | None, str]]:
    """Return ``[(original_or_None, clean_name), ...]`` and set ``ctx.column_names``."""
    counts: dict[str, int] = {}
    result: list[tuple[str | None, str]] = []

    for index, raw in enumerate(raw_names):
        slug = _slugify(raw)
        original: str | None = raw.strip() or None
        if not slug:
            base = f"column_{index + 1}"
            rule = "empty"
        else:
            base = slug
            rule = "slugify"

        if base not in counts:
            counts[base] = 1
            name = base
        else:
            counts[base] += 1
            name = f"{base}_{counts[base]}"
            while name in counts:
                counts[base] += 1
                name = f"{base}_{counts[base]}"
            counts[name] = 1
            rule = "deduplicate"

        if name != original:
            ctx.report.record(
                ActionKind.HEADER_RENAMED,
                rule,
                column=name,
                col=index,
                original=original,
                final=name,
            )
        result.append((original, name))

    ctx.column_names = [name for _, name in result]
    return result


def _slugify(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    slug = _NON_WORD.sub("_", ascii_text.lower().strip())
    slug = _MULTI_UNDERSCORE.sub("_", slug).strip("_")
    if slug and slug[0].isdigit():
        slug = f"col_{slug}"
    return slug
