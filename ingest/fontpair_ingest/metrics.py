"""OS/2, cmap, and script coverage."""

from __future__ import annotations

from typing import Any, Optional

from fontpair_ingest.config import SCRIPT_COVERAGE_THRESHOLD

# Reference codepoint sets (subset of Unicode used for coverage flags)
LATIN = list(range(0x20, 0x7F))
LATIN_EXT = list(range(0x00A0, 0x0180))
CYRILLIC = list(range(0x0400, 0x0500))
GREEK = list(range(0x0370, 0x0400))
DEVANAGARI = list(range(0x0900, 0x0980))
ARABIC = list(range(0x0600, 0x0700))
CJK = list(range(0x4E00, 0x4F00))  # sample block for presence check


def _coverage_fraction(codepoints: set[int], reference: list[int]) -> float:
    if not reference:
        return 0.0
    hits = sum(1 for cp in reference if cp in codepoints)
    return hits / len(reference)


def script_flags_from_cmap(cmap: dict[int, str] | None) -> dict[str, Any]:
    """Derive script coverage from a Unicode cmap."""
    if not cmap:
        return {
            "latin": False,
            "latin_ext": False,
            "cyrillic": False,
            "greek": False,
            "devanagari": False,
            "arabic": False,
            "cjk": False,
            "codepoint_count": 0,
        }

    cps = set(cmap.keys())
    threshold = SCRIPT_COVERAGE_THRESHOLD

    def flag(ref: list[int]) -> bool:
        return _coverage_fraction(cps, ref) >= threshold

    return {
        "latin": flag(LATIN),
        "latin_ext": flag(LATIN_EXT),
        "cyrillic": flag(CYRILLIC),
        "greek": flag(GREEK),
        "devanagari": flag(DEVANAGARI),
        "arabic": flag(ARABIC),
        "cjk": flag(CJK),
        "codepoint_count": len(cps),
    }


def name_record(font: Any, name_id: int) -> Optional[str]:
    name_table = font.get("name")
    if name_table is None:
        return None
    rec = name_table.getName(nameID=name_id, platformID=3, platEncID=1, langID=0x409)
    if rec is None:
        rec = name_table.getName(nameID=name_id)
    if rec is None:
        return None
    return str(rec.toUnicode()).strip()
