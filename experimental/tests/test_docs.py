import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY_TERMS = (
    "registry / spine",
    "spine id",
    "ID map",
    "founding source",
    "claims",
    "who-wins rules (survivorship)",
    "materializer",
    "pending records",
    "review queue / steward",
    "health views",
    "dry run",
)


def test_plain_language_guide_contains_the_complete_kit_glossary() -> None:
    path = ROOT / "docs" / "HOW-IT-WORKS.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    missing = [term for term in GLOSSARY_TERMS if term not in text]
    assert missing == []


def test_readme_leads_readers_to_the_plain_language_guide() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "HOW-IT-WORKS.md").read_text(encoding="utf-8")
    filing_start = guide.index("Deploy it once")
    filing_end = guide.index("\n\n", filing_start)
    filing_cabinet = guide[filing_start:filing_end]
    loop_start = guide.index("## Using it is a four-step loop")
    loop_end = guide.index("\n## What", loop_start)
    four_step_loop = guide[loop_start:loop_end].strip()
    filing_position = readme.index(filing_cabinet)
    loop_position = readme.index(four_step_loop)
    link_position = readme.index("[HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)")
    assert filing_position < loop_position < link_position
    assert "(docs/HOW-IT-WORKS.md)" in readme


def test_docs_distinguish_the_dictionary_from_the_deployed_scope() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "HOW-IT-WORKS.md").read_text(encoding="utf-8")
    generation = (ROOT / "docs" / "model-generation.md").read_text(encoding="utf-8")
    for text in (readme, guide, generation):
        assert "139" in text
        assert "15" in text
    assert "does not extract PDF facts" in guide
    assert "file-pointer registration are not\ndeployed" in readme


def test_tutorial_csvs_cover_every_configured_feed_column() -> None:
    config = yaml.safe_load(
        (ROOT / "src" / "onramp" / "sources" / "example_cmms.yml").read_text(
            encoding="utf-8"
        )
    )
    files_by_entity = {
        "tag": ROOT / "tutorial" / "example_locations.csv",
        "equipment": ROOT / "tutorial" / "example_assets.csv",
    }
    for entity_name, path in files_by_entity.items():
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        feed = config["feeds"][entity_name]
        required_columns = {feed["source_id"], *feed["fields"].values()}
        assert path.stem == feed["from"].rsplit(".", 1)[-1]
        assert set(reader.fieldnames or []) == required_columns
        assert rows
    tutorial_readme = (ROOT / "tutorial" / "README.md").read_text(encoding="utf-8")
    provenance = (ROOT / "docs" / "PROVENANCE.md").read_text(encoding="utf-8")
    assert "original to this kit" in tutorial_readme
    assert "Neutral CSVs under `tutorial/`" in provenance


def test_tutorial_notebooks_preflight_and_validate_the_documented_defaults() -> None:
    upload = (ROOT / "notebooks" / "01_upload_and_profile.py").read_text(encoding="utf-8")
    mapping = (ROOT / "notebooks" / "02_map_and_dryrun.py").read_text(encoding="utf-8")
    health = (ROOT / "notebooks" / "03_health.py").read_text(encoding="utf-8")
    assert 'dbutils.widgets.text("source_name", "example_cmms")' in upload
    assert 'dbutils.widgets.text("feed_table_name", "example_locations")' in upload
    assert "feed_table_name=example_assets" in upload
    assert 'spark.catalog.tableExists(feed["from"])' in mapping
    assert "Missing configured source tables" in mapping
    assert "from src.validate import validate" in health
    assert "validation_run_id" in health
