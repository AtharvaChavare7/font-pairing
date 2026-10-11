"""Group faces into families and assign stable ids."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fontpair_ingest.discover import FaceRecord
from fontpair_ingest.metadata_pb import parse_metadata_pb


@dataclass
class FamilyRecord:
    id: str
    name: str
    source: str
    license: str
    license_path: str | None
    hostable: bool
    designer: str
    category_raw: str
    popularity: int | None
    clone_group_id: str | None
    tags: list[str] = field(default_factory=list)


def _license_file(family_dir: Path) -> str | None:
    for name in ("OFL.txt", "LICENSE.txt", "UFL.txt", "APACHE.txt", "LICENSE"):
        p = family_dir / name
        if p.is_file():
            return str(p)
    for p in family_dir.glob("*.txt"):
        if "license" in p.name.lower() or p.name.startswith("OFL"):
            return str(p)
    return None


def group_faces_into_families(
    faces: list[FaceRecord],
    corpus_root: Path,
) -> tuple[list[FamilyRecord], list[dict[str, Any]]]:
    """
    Group faces by typographic family name key.
    Returns (families, face_rows) with family_id attached.
    """
    by_key: dict[tuple[str, str, str], list[FaceRecord]] = {}
    for face in faces:
        key = (face.family_name_key, face.license_dir, face.family_dir)
        by_key.setdefault(key, []).append(face)

    families: list[FamilyRecord] = []
    face_rows: list[dict[str, Any]] = []

    for (name_key, license_dir, family_slug), group in sorted(by_key.items()):
        sample = group[0]
        family_dir = Path(sample.file_path).parent
        meta_path = family_dir / "METADATA.pb"
        designer = ""
        category = ""
        display_name = name_key
        if meta_path.is_file():
            meta = parse_metadata_pb(meta_path)
            if meta.name:
                display_name = meta.name
            designer = meta.designer
            category = meta.category

        family_id = str(uuid.uuid4())
        lic_path = _license_file(family_dir)
        hostable = license_dir in ("ofl", "apache", "ufl")

        families.append(
            FamilyRecord(
                id=family_id,
                name=display_name,
                source=sample.source,
                license=license_dir,
                license_path=lic_path,
                hostable=hostable,
                designer=designer,
                category_raw=category,
                popularity=None,
                clone_group_id=None,
                tags=[],
            )
        )

        for face in group:
            inst = face.vf_instance_name
            style_name = inst if inst else face.style_name
            face_rows.append(
                {
                    "id": face.id,
                    "family_id": family_id,
                    "style_name": style_name,
                    "weight": face.weight,
                    "width": face.width,
                    "italic": face.italic,
                    "is_variable": face.is_variable,
                    "vf_axes": face.vf_axes,
                    "file_path": face.file_path,
                    "units_per_em": face.units_per_em,
                    "script_flags": face.script_flags,
                    "codepoint_count": face.script_flags.get("codepoint_count", 0),
                }
            )

    return families, face_rows
