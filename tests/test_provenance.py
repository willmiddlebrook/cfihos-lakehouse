from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE_MARKERS = (
    "original to this kit",
    "cc by 4.0",
    "creative commons attribution 4.0",
)


def test_every_doc_and_notebook_declares_its_origin() -> None:
    files = sorted(
        path
        for folder in (ROOT / "docs", ROOT / "notebooks")
        if folder.exists()
        for path in folder.rglob("*")
        if path.is_file()
    )
    assert files
    missing = []
    for path in files:
        text = path.read_text(encoding="utf-8").casefold()
        if not any(marker in text for marker in PROVENANCE_MARKERS):
            missing.append(str(path.relative_to(ROOT)))
    assert missing == []
