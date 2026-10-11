"""Walk font files and produce face records."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from fontTools.ttLib import TTFont

from fontpair_ingest.config import GOOGLE_LICENSE_DIRS, REJECTS_PATH
from fontpair_ingest.metrics import name_record, script_flags_from_cmap


@dataclass
class FaceRecord:
    id: str
    file_path: str
    family_name_key: str
    style_name: str
    weight: int
    width: int
    italic: bool
    is_variable: bool
    vf_axes: list[dict[str, Any]]
    vf_instance_name: str | None
    units_per_em: int
    script_flags: dict[str, Any]
    source: str
    license_dir: str
    family_dir: str


@dataclass
class RejectRecord:
    path: str
    error: str


FONT_SUFFIXES = {".ttf", ".otf"}


def _log_reject(path: Path, error: Exception) -> None:
    REJECTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {"path": str(path), "error": repr(error)}
    with REJECTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def _family_has_variable_font(family_dir: Path) -> bool:
    for p in family_dir.rglob("*"):
        if p.suffix.lower() not in FONT_SUFFIXES:
            continue
        if "static" in p.parts:
            continue
        try:
            with TTFont(p, lazy=True) as font:
                if "fvar" in font:
                    return True
        except Exception:
            continue
    return False


def iter_font_paths(corpus_root: Path, license_dirs: tuple[str, ...] = GOOGLE_LICENSE_DIRS) -> Iterator[Path]:
    """Yield font paths under ofl/apache/ufl with static-dir skip rule."""
    for lic in license_dirs:
        base = corpus_root / lic
        if not base.is_dir():
            continue
        for family_dir in sorted(base.iterdir()):
            if not family_dir.is_dir():
                continue
            skip_static = _family_has_variable_font(family_dir)
            for path in sorted(family_dir.rglob("*")):
                if path.suffix.lower() not in FONT_SUFFIXES:
                    continue
                if skip_static and "static" in path.parts:
                    continue
                yield path


def _fs_selection_italic(os2: Any) -> bool:
    if os2 is None:
        return False
    return bool(os2.fsSelection & 1)


def _vf_axes(font: TTFont) -> list[dict[str, Any]]:
    fvar = font.get("fvar")
    if fvar is None:
        return []
    axes = []
    for axis in fvar.axes:
        axes.append(
            {
                "tag": axis.axisTag,
                "min": float(axis.minValue),
                "max": float(axis.maxValue),
                "default": float(axis.defaultValue),
            }
        )
    return axes


def _named_instances(font: TTFont) -> list[dict[str, Any]]:
    fvar = font.get("fvar")
    if fvar is None or not getattr(fvar, "instances", None):
        return []
    instances = []
    for inst in fvar.instances:
        name_id = inst.subfamilyNameID
        name = name_record(font, name_id) or f"instance-{name_id}"
        coords = {fvar.axes[i].axisTag: float(v) for i, v in enumerate(inst.coordinates)}
        instances.append({"name": name, "coordinates": coords})
    return instances


def extract_face(
    path: Path,
    source: str = "google-fonts",
    license_dir: str = "",
    family_dir: str = "",
) -> list[FaceRecord]:
    """Parse one font file; may return multiple records for VF named instances."""
    faces: list[FaceRecord] = []
    try:
        with TTFont(path, lazy=True) as font:
            fam_key = name_record(font, 16) or name_record(font, 1) or path.parent.name
            style = name_record(font, 17) or name_record(font, 2) or "Regular"
            head = font["head"]
            os2 = font.get("OS/2")
            weight = int(os2.usWeightClass) if os2 else 400
            width = int(os2.usWidthClass) if os2 else 5
            italic = _fs_selection_italic(os2)
            cmap = font.getBestCmap()
            script_flags = script_flags_from_cmap(cmap)
            upem = int(head.unitsPerEm)
            is_vf = "fvar" in font
            axes = _vf_axes(font)

            base = {
                "file_path": str(path),
                "family_name_key": fam_key,
                "style_name": style,
                "weight": weight,
                "width": width,
                "italic": italic,
                "is_variable": is_vf,
                "vf_axes": axes,
                "units_per_em": upem,
                "script_flags": script_flags,
                "source": source,
                "license_dir": license_dir,
                "family_dir": family_dir,
            }

            instances = _named_instances(font) if is_vf else []
            if instances:
                for inst in instances:
                    faces.append(
                        FaceRecord(
                            id=str(uuid.uuid4()),
                            vf_instance_name=inst["name"],
                            **base,
                        )
                    )
            else:
                faces.append(
                    FaceRecord(
                        id=str(uuid.uuid4()),
                        vf_instance_name=None,
                        **base,
                    )
                )
    except Exception as exc:
        _log_reject(path, exc)
    return faces


def discover_corpus(corpus_root: Path) -> tuple[list[FaceRecord], int]:
    """Walk corpus and collect faces; returns (faces, reject_count)."""
    if REJECTS_PATH.exists():
        REJECTS_PATH.unlink()

    faces: list[FaceRecord] = []
    reject_before = 0
    if REJECTS_PATH.exists():
        reject_before = sum(1 for _ in REJECTS_PATH.open())

    for path in iter_font_paths(corpus_root):
        lic = path.parts[-3] if len(path.parts) >= 3 else ""
        fam = path.parts[-2] if len(path.parts) >= 2 else ""
        faces.extend(
            extract_face(
                path,
                source="google-fonts",
                license_dir=lic,
                family_dir=fam,
            )
        )

    reject_count = 0
    if REJECTS_PATH.exists():
        reject_count = sum(1 for _ in REJECTS_PATH.open())
    return faces, reject_count
