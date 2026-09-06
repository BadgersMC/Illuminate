import pytest

from illuminate.core.scene import (
    EditableProperty,
    SceneRegistry,
    SceneRegistryError,
)


def test_scene_summary_is_semantic_bounded_and_contains_no_handle() -> None:
    registry = SceneRegistry("waystation", max_summary_nodes=2)
    registry.register("root", None, "root", frozenset(), object())
    registry.register(
        "door",
        "root",
        "model",
        {EditableProperty.TRANSFORM},
        object(),
    )

    summary = registry.summary(depth=1)

    assert [node["id"] for node in summary["nodes"]] == ["root", "door"]
    assert summary["truncated"] is False
    assert "handle" not in repr(summary)


def test_summary_depth_and_node_limit_are_enforced() -> None:
    registry = SceneRegistry("waystation", max_summary_nodes=2)
    registry.register("root", None, "root", frozenset(), object())
    registry.register("door", "root", "model", frozenset(), object())
    registry.register("light", "door", "light", frozenset(), object())

    shallow = registry.summary(depth=0)
    bounded = registry.summary(depth=4)

    assert [node["id"] for node in shallow["nodes"]] == ["root"]
    assert [node["id"] for node in bounded["nodes"]] == ["root", "door"]
    assert bounded["truncated"] is True


def test_registry_rejects_duplicate_missing_parent_and_long_ids() -> None:
    registry = SceneRegistry("waystation")
    registry.register("root", None, "root", frozenset(), object())

    with pytest.raises(SceneRegistryError, match="already registered"):
        registry.register("root", None, "root", frozenset(), object())
    with pytest.raises(SceneRegistryError, match="parent"):
        registry.register("orphan", "missing", "model", frozenset(), object())
    with pytest.raises(SceneRegistryError, match="128"):
        registry.register("n" * 129, "root", "model", frozenset(), object())

