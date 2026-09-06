import pytest
from panda3d.core import LColor, NodePath, PandaNode, PointLight

from illuminate.core.edits import EditKind, EditOperation
from illuminate.core.overlay import EditRejectedError
from illuminate.core.scene import EditableProperty
from illuminate.panda.mutator import PandaMutator
from illuminate.panda.registration import PandaSceneRegistration


def registration() -> tuple[PandaSceneRegistration, NodePath]:
    root = NodePath(PandaNode("root"))
    door = root.attach_new_node("door")
    scene = PandaSceneRegistration("waystation")
    scene.add_node("root", root, frozenset())
    scene.add_node("door", door, {EditableProperty.TRANSFORM}, parent_id="root")
    return scene, door


def test_mutator_changes_and_restores_registered_transform() -> None:
    scene, door = registration()
    mutator = PandaMutator(scene)
    operation = EditOperation("door", EditKind.SET_POSITION, [1.0, 2.0, 3.0])

    mutator.validate(operation, scene.registry)
    inverse = mutator.inverse(operation)
    mutator.apply(operation)
    assert tuple(door.get_pos()) == pytest.approx((1.0, 2.0, 3.0))

    mutator.apply(inverse)
    assert tuple(door.get_pos()) == pytest.approx((0.0, 0.0, 0.0))


@pytest.mark.parametrize(
    "value",
    ([1.0, 2.0], [1.0, 2.0, float("nan")], [1.0, 2.0, float("inf")]),
)
def test_mutator_rejects_invalid_vectors_without_changing_node(value) -> None:
    scene, door = registration()
    mutator = PandaMutator(scene)

    with pytest.raises(EditRejectedError):
        mutator.validate(
            EditOperation("door", EditKind.SET_POSITION, value),
            scene.registry,
        )

    assert tuple(door.get_pos()) == pytest.approx((0.0, 0.0, 0.0))


def test_registration_rejects_removed_node() -> None:
    scene, door = registration()
    door.remove_node()

    with pytest.raises(EditRejectedError, match="removed"):
        PandaMutator(scene).validate(
            EditOperation("door", EditKind.SET_POSITION, [1, 2, 3]),
            scene.registry,
        )


def test_light_color_intensity_and_attenuation_are_independently_reversible() -> None:
    root = NodePath(PandaNode("root"))
    light = PointLight("lantern")
    light.set_color(LColor(1.0, 0.5, 0.25, 1.0))
    light_path = root.attach_new_node(light)
    scene = PandaSceneRegistration("waystation")
    scene.add_node("root", root, frozenset())
    scene.add_node(
        "lantern",
        light_path,
        {EditableProperty.LIGHT},
        parent_id="root",
        kind="light",
    )
    mutator = PandaMutator(scene)

    intensity = EditOperation("lantern", EditKind.SET_LIGHT_INTENSITY, 0.5)
    attenuation = EditOperation(
        "lantern", EditKind.SET_LIGHT_ATTENUATION, [1.0, 0.1, 0.02]
    )
    intensity_inverse = mutator.inverse(intensity)
    attenuation_inverse = mutator.inverse(attenuation)
    mutator.validate(intensity, scene.registry)
    mutator.validate(attenuation, scene.registry)
    mutator.apply(intensity)
    mutator.apply(attenuation)

    assert tuple(light.get_color()) == pytest.approx((0.5, 0.25, 0.125, 1.0))
    assert tuple(light.get_attenuation()) == pytest.approx((1.0, 0.1, 0.02))

    mutator.apply(attenuation_inverse)
    mutator.apply(intensity_inverse)
    assert tuple(light.get_color()) == pytest.approx((1.0, 0.5, 0.25, 1.0))
