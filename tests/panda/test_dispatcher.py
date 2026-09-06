from panda3d.core import NodePath, PandaNode

from illuminate.core.overlay import Overlay
from illuminate.core.scene import EditableProperty
from illuminate.panda.dispatcher import PandaCommandDispatcher
from illuminate.panda.mutator import PandaMutator
from illuminate.panda.registration import PandaSceneRegistration
from illuminate.protocol import ErrorCode, Operation, Request


def dispatcher_fixture(tmp_path):
    root = NodePath(PandaNode("root"))
    door = root.attach_new_node("door")
    registration = PandaSceneRegistration("waystation")
    registration.add_node("root", root, frozenset())
    registration.add_node(
        "door",
        door,
        {EditableProperty.TRANSFORM, EditableProperty.VISIBILITY},
        parent_id="root",
        kind="model",
    )
    dispatcher = PandaCommandDispatcher(
        registration=registration,
        overlay=Overlay(),
        mutator=PandaMutator(registration),
        base=None,
        views={},
        capture_dir=tmp_path,
    )
    return dispatcher, door


def test_dispatcher_previews_then_inspects_only_requested_node(tmp_path) -> None:
    dispatcher, door = dispatcher_fixture(tmp_path)
    preview = dispatcher.dispatch(
        Request(
            1,
            "r1",
            Operation.PREVIEW_CHANGES,
            {
                "expected_revision": 0,
                "operations": [
                    {
                        "node_id": "door",
                        "kind": "set_position",
                        "value": [1.0, 2.0, 3.0],
                    }
                ],
            },
        ),
        dispatcher.registration.registry,
    )
    inspected = dispatcher.dispatch(
        Request(1, "r2", Operation.INSPECT_NODES, {"node_ids": ["door"]}),
        dispatcher.registration.registry,
    )

    assert preview.ok and preview.result == {"revision": 1, "changed_node_ids": ["door"]}
    assert inspected.ok
    assert inspected.result["nodes"] == [
        {
            "id": "door",
            "kind": "model",
            "parent_id": "root",
            "editable": ["transform", "visibility"],
            "position": [1.0, 2.0, 3.0],
            "hpr": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "visible": True,
        }
    ]
    assert tuple(door.get_pos()) == (1.0, 2.0, 3.0)


def test_dispatcher_rejects_stale_revision_as_typed_error(tmp_path) -> None:
    dispatcher, door = dispatcher_fixture(tmp_path)
    response = dispatcher.dispatch(
        Request(
            1,
            "r1",
            Operation.PREVIEW_CHANGES,
            {
                "expected_revision": 2,
                "operations": [
                    {"node_id": "door", "kind": "set_position", "value": [1, 2, 3]}
                ],
            },
        ),
        dispatcher.registration.registry,
    )

    assert not response.ok
    assert response.error_code is ErrorCode.REVISION_CONFLICT
    assert tuple(door.get_pos()) == (0.0, 0.0, 0.0)


def test_dispatcher_does_not_accept_server_owned_operations(tmp_path) -> None:
    dispatcher, _door = dispatcher_fixture(tmp_path)
    response = dispatcher.dispatch(
        Request(1, "r1", Operation.LAUNCH_SCENE, {}),
        dispatcher.registration.registry,
    )
    assert not response.ok
    assert response.error_code is ErrorCode.UNKNOWN_OPERATION

