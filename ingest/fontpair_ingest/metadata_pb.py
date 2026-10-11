"""Parse Google Fonts METADATA.pb (text protobuf)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MetadataFont:
    name: str = ""
    style: str = ""
    weight: int = 400
    filename: str = ""


@dataclass
class MetadataAxis:
    tag: str = ""
    min_value: float = 0.0
    max_value: float = 0.0
    default_value: float = 0.0


@dataclass
class FamilyMetadata:
    name: str = ""
    designer: str = ""
    category: str = ""
    subsets: list[str] = field(default_factory=list)
    fonts: list[MetadataFont] = field(default_factory=list)
    axes: list[MetadataAxis] = field(default_factory=list)


_SCALAR = re.compile(r'^(\w+):\s*(?:"([^"]*)"|(\S+))\s*$')
_BLOCK = re.compile(r"(\w+)\s*\{([^}]*)\}", re.MULTILINE)


def _fields_in_block(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _SCALAR.match(line)
        if m:
            key = m.group(1)
            val = m.group(2) if m.group(2) is not None else m.group(3)
            out[key] = val
    return out


def parse_metadata_pb(path: Path) -> FamilyMetadata:
    text = path.read_text(encoding="utf-8", errors="replace")
    meta = FamilyMetadata()
    header_end = text.find("fonts {")
    if header_end < 0:
        header_end = text.find("axes {")
    if header_end < 0:
        header_end = len(text)
    header = text[:header_end]

    for line in header.splitlines():
        line = line.strip()
        if line.startswith("subsets:"):
            m = _SCALAR.match(line)
            if m and m.group(2):
                meta.subsets.append(m.group(2))
            continue
        m = _SCALAR.match(line)
        if m and m.group(1) in ("name", "designer", "category"):
            val = m.group(2) if m.group(2) is not None else m.group(3)
            setattr(meta, m.group(1), val)

    for kind, body in _BLOCK.findall(text):
        fields = _fields_in_block(body)
        if kind == "fonts":
            meta.fonts.append(
                MetadataFont(
                    name=fields.get("name", ""),
                    style=fields.get("style", ""),
                    weight=int(fields.get("weight", "400") or 400),
                    filename=fields.get("filename", ""),
                )
            )
        elif kind == "axes":
            meta.axes.append(
                MetadataAxis(
                    tag=fields.get("tag", ""),
                    min_value=float(fields.get("min_value", "0") or 0),
                    max_value=float(fields.get("max_value", "0") or 0),
                    default_value=float(fields.get("default_value", "0") or 0),
                )
            )

    return meta
