import pytest

from src.trust import steward


class _Row(dict):
    def asDict(self, *, recursive: bool) -> dict[str, str]:
        assert recursive
        return dict(self)


class _AffectedMappings:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows

    def join(self, other: object, columns: str, how: str) -> "_AffectedMappings":
        assert other is _ABSORBED_KEY
        assert columns == "spine_id"
        assert how == "inner"
        return self

    def collect(self) -> list[_Row]:
        return self.rows


_ABSORBED_KEY = object()


class _MergeSpark:
    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows

    def createDataFrame(self, rows: list[tuple[str]], schema: str) -> object:
        assert rows == [("absorbed-spine",)]
        assert schema == "spine_id string"
        return _ABSORBED_KEY

    def table(self, name: str) -> _AffectedMappings:
        assert name == "cfihos_tutorial.cfihos_trust.id_map"
        return _AffectedMappings(self.rows)


def test_merge_rejects_survivor_missing_from_any_affected_entity_before_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spark = _MergeSpark(
        [
            _Row(
                source_system="source_a",
                entity="equipment",
                source_id="equipment-1",
                spine_id="absorbed-spine",
            ),
            _Row(
                source_system="source_b",
                entity="equipment",
                source_id="equipment-2",
                spine_id="absorbed-spine",
            ),
            _Row(
                source_system="source_c",
                entity="tag",
                source_id="tag-1",
                spine_id="absorbed-spine",
            ),
        ]
    )
    checked_entities: list[str] = []
    writes: list[str] = []

    def require_survivor(
        spark_arg: object, catalog: str, entity: str, spine_id: str
    ) -> None:
        assert spark_arg is spark
        assert catalog == "cfihos_tutorial"
        assert spine_id == "survivor-spine"
        checked_entities.append(entity)
        if entity == "tag":
            raise ValueError(
                "spine_id 'survivor-spine' does not exist for target entity 'tag'"
            )

    monkeypatch.setattr(steward, "_require_existing_spine", require_survivor)
    monkeypatch.setattr(
        steward, "_apply_id_map_rows", lambda *_: writes.append("id_map")
    )
    monkeypatch.setattr(steward, "_audit_event", lambda *_: writes.append("audit"))

    with pytest.raises(
        ValueError,
        match="survivor-spine.*does not exist for target entity.*tag",
    ):
        steward.apply_merge(
            spark,
            "cfihos_tutorial",
            "survivor-spine",
            "absorbed-spine",
            "steward",
            "same asset",
        )

    assert checked_entities == ["equipment", "tag"]
    assert writes == []
