from pathlib import Path

from fontpair_ingest.metadata_pb import parse_metadata_pb

FIXTURE = Path(__file__).parent / "fixtures" / "sample" / "METADATA.pb"


def test_parse_metadata_pb() -> None:
    meta = parse_metadata_pb(FIXTURE)
    assert meta.name == "Sample Sans"
    assert meta.designer == "Test Designer"
    assert meta.category == "SANS_SERIF"
    assert len(meta.fonts) == 2
    assert meta.fonts[0].filename == "SampleSans-Regular.ttf"
    assert meta.fonts[1].weight == 700
