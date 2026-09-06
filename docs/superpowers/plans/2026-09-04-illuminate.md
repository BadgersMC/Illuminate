# Illuminate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable local Panda3D visual workbench, MCP server, Codex skill, and Littleglow adapter, then use the completed workflow to make the private waystation visually readable.

**Architecture:** A stdio MCP server owns run artifacts and launches a project-registered workbench. An authenticated loopback bridge queues bounded commands onto Panda3D's main thread; semantic scene registrations and a revisioned in-memory overlay prevent arbitrary process access. Project adapters alone validate and persist approved edits.

**Tech Stack:** Python 3.12, official MCP Python SDK v2, Panda3D 1.10.16, Pillow 11, pytest 8, standard-library sockets/JSON/subprocess/TOML, Codex plugin and skill manifests.

**Spec:** `docs/superpowers/specs/2026-09-04-illuminate-design.md`

## Global Constraints

- Work only in local files. Do not run Git commands, create branches, create worktrees, or commit.
- Follow SPEAR for every production unit: read its `REQ-` entry, write a failing test, implement the minimum behavior, check dependency direction, then refine with green tests.
- Bind only to `127.0.0.1`; authenticate one controller with a random per-session token that is never written to run artifacts.
- Never expose arbitrary Python evaluation, imports, shell commands, filesystem browsing, transient object addresses, or unrestricted Panda attributes through MCP.
- Mutate Panda3D objects only on Panda's main thread through the bridge command queue.
- Address editable objects by adapter-registered semantic IDs.
- Keep all preview changes temporary until explicit `apply_changes` with the current overlay revision and a non-empty approval note.
- A failed batch or apply must leave the prior overlay or source intact.
- Keep gameplay destinations, interaction IDs, collision roles, distributed state, and tutorial progression outside visual overrides.
- Tool responses default to compact semantic summaries and deltas; screenshots are stored as files rather than embedded as base64.
- The first real acceptance run must improve Littleglow's waystation and survive a clean relaunch.

---

### Task 1: SPEAR project baseline and protocol contracts

**Files:**
- Create: `pyproject.toml`
- Create: `docs/tech-stack.md`
- Create: `docs/requirements.md`
- Create: `docs/implementation.md`
- Create: `docs/tasks.md`
- Create: `src/illuminate/__init__.py`
- Create: `src/illuminate/protocol.py`
- Create: `tests/test_protocol.py`

**Interfaces:**
- Produces: `PROTOCOL_VERSION`, `Operation`, `ErrorCode`, `Request`, `Response`, `ProtocolError`, `decode_request(bytes)`, and `encode_response(Response)`.
- Later tasks consume only these protocol types across the socket boundary.

- [x] **Step 1: Write the SPEAR documents and mark ILM-0101 in progress**

Define EARS requirements `REQ-PRT-001` through `REQ-PRT-006` for versioned JSON messages, size limits, unknown-field rejection, typed errors, redacted secrets, and bounded identifiers. Record dependency direction:

```text
protocol <- core <- bridge
                <- server
adapters -> protocol/core/bridge
```

Create `docs/tasks.md` with ILM-0101 through ILM-0801 corresponding to Tasks 1-8 below and mark ILM-0101 `[~]`.

- [x] **Step 2: Write failing protocol tests**

```python
def test_request_rejects_unknown_operation_and_fields() -> None:
    with pytest.raises(ProtocolError) as unknown:
        decode_request(b'{"version":1,"id":"r1","operation":"eval","payload":{}}')
    assert unknown.value.code is ErrorCode.UNKNOWN_OPERATION

    with pytest.raises(ProtocolError) as extra:
        decode_request(
            b'{"version":1,"id":"r1","operation":"scene_summary",'
            b'"payload":{},"token":"must-not-be-in-message"}'
        )
    assert extra.value.code is ErrorCode.INVALID_REQUEST


def test_response_encoding_never_contains_registered_secret() -> None:
    response = Response.success("r1", {"session_id": "s1"})
    assert b"secret-token" not in encode_response(response)
```

- [x] **Step 3: Run tests and verify RED**

Run: `uv sync --extra dev; uv run pytest tests/test_protocol.py -q`  
Expected: collection fails because `illuminate.protocol` does not exist.

- [x] **Step 4: Implement strict frozen protocol values**

Use frozen dataclasses and enums. Limit messages to 1 MiB, request IDs and semantic IDs to 128 UTF-8 characters, accept only the public operations defined by the spec, and reject extra top-level fields. Authentication belongs to the socket handshake, never `Request.payload`.

- [x] **Step 5: Verify and finish ILM-0101**

Run: `uv run pytest tests/test_protocol.py -q`  
Expected: all protocol tests pass. Mark ILM-0101 `[x]` and ILM-0201 `[~]`.

---

### Task 2: Semantic registry and revisioned temporary overlay

**Files:**
- Create: `src/illuminate/core/scene.py`
- Create: `src/illuminate/core/overlay.py`
- Create: `src/illuminate/core/edits.py`
- Create: `tests/core/test_scene.py`
- Create: `tests/core/test_overlay.py`

**Interfaces:**
- Produces: `EditableProperty`, `SemanticNode`, `SceneRegistry`, `EditKind`, `EditOperation`, `EditBatch`, `AppliedBatch`, `Overlay`, `OverlayConflictError`, and `EditRejectedError`.
- `SceneRegistry.register(node_id, parent_id, kind, editable, handle)` retains the opaque handle only in-process.
- `Overlay.preview(batch, registry, mutator) -> AppliedBatch` and `Overlay.undo(expected_revision, scope, mutator) -> int` are atomic.

- [x] **Step 1: Write failing registry and overlay tests**

```python
def test_scene_summary_is_semantic_bounded_and_contains_no_handle() -> None:
    registry = SceneRegistry("waystation", max_summary_nodes=2)
    registry.register("root", None, "root", frozenset(), object())
    registry.register("door", "root", "model", {EditableProperty.TRANSFORM}, object())
    summary = registry.summary(depth=1)
    assert [node["id"] for node in summary["nodes"]] == ["root", "door"]
    assert "handle" not in repr(summary)


def test_edit_batch_is_atomic_and_revision_checked() -> None:
    overlay, registry, mutator = overlay_fixture()
    batch = EditBatch(0, (
        EditOperation("door", EditKind.SET_POSITION, [1.0, 2.0, 3.0]),
        EditOperation("protected", EditKind.SET_VISIBILITY, False),
    ))
    with pytest.raises(EditRejectedError):
        overlay.preview(batch, registry, mutator)
    assert overlay.revision == 0
    assert mutator.values["door.position"] == [0.0, 0.0, 0.0]


def test_undo_restores_inverse_values() -> None:
    overlay, registry, mutator = overlay_fixture()
    overlay.preview(position_batch(expected_revision=0), registry, mutator)
    assert overlay.undo(1, "latest", mutator) == 2
    assert mutator.values["door.position"] == [0.0, 0.0, 0.0]
```

- [x] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/core -q`  
Expected: imports fail because the core modules do not exist.

- [x] **Step 3: Implement the registry and overlay transaction**

Validate every operation and capture every inverse before mutating anything. If mutation N fails, apply inverses for `0..N-1` in reverse order and retain the old revision/history. Supported kinds are transform components, color scale, visibility, registered light values, registered parameters, and adapter-approved simple primitives.

- [x] **Step 4: Verify and finish ILM-0201**

Run: `uv run pytest tests/core -q`  
Expected: all core tests pass. Mark ILM-0201 `[x]` and ILM-0301 `[~]`.

---

### Task 3: Authenticated loopback transport and Panda main-thread bridge

**Files:**
- Create: `src/illuminate/bridge/transport.py`
- Create: `src/illuminate/bridge/queue.py`
- Create: `src/illuminate/bridge/runtime.py`
- Create: `tests/bridge/test_transport.py`
- Create: `tests/bridge/test_runtime.py`

**Interfaces:**
- Produces: `BridgeAddress`, `BridgeCommand`, `CommandQueue`, `LoopbackBridgeServer`, and `IlluminateBridge`.
- `IlluminateBridge.attach(base, registry, adapter, token, port=0) -> IlluminateBridge` installs exactly one Panda task.
- `IlluminateBridge.pump(max_commands=8)` executes queued commands on the attaching thread.

- [x] **Step 1: Write failing transport security tests**

```python
def test_bridge_binds_loopback_and_rejects_bad_token() -> None:
    server = LoopbackBridgeServer(token="correct", handler=lambda request: None)
    server.start()
    try:
        assert server.address.host == "127.0.0.1"
        with pytest.raises(AuthenticationError):
            connect_and_handshake(server.address, "wrong")
    finally:
        server.close()


def test_only_pump_thread_executes_scene_handler() -> None:
    queue = CommandQueue(owner_thread_id=threading.get_ident())
    submitted = submit_from_worker(queue, request("scene_summary"))
    assert not submitted.done()
    queue.pump(handler)
    assert submitted.result().ok
    with pytest.raises(WrongThreadError):
        pump_from_worker(queue, handler)
```

Also test one-controller enforcement, 1 MiB rejection before JSON parsing, handshake timeout, malformed newline frames, disconnect cleanup, and idempotent close.

- [x] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/bridge -q`  
Expected: imports fail because bridge modules do not exist.

- [x] **Step 3: Implement transport and queue**

Use a daemon accept/read thread only for bounded socket I/O. Queue decoded `Request` objects and await per-command futures with timeouts. The Panda task calls `pump`; handlers return serializable values. Redact the token from exceptions, representations, diagnostics, and responses.

- [x] **Step 4: Add a headless Panda lifecycle test**

Create a real `ShowBase(windowType="none")`, register one `NodePath`, attach the bridge, submit `scene_summary`, step the task manager, and assert the future completes. Destroy twice and assert both the Panda task and listening socket are gone.

- [x] **Step 5: Verify and finish ILM-0301**

Run: `uv run pytest tests/bridge -q`  
Expected: all bridge tests pass without leaked tasks or sockets. Mark ILM-0301 `[x]` and ILM-0401 `[~]`.

---

### Task 4: Panda scene adapter, edit mutator, and canonical captures

**Files:**
- Create: `src/illuminate/panda/registration.py`
- Create: `src/illuminate/panda/mutator.py`
- Create: `src/illuminate/panda/capture.py`
- Create: `src/illuminate/panda/dispatcher.py`
- Create: `tests/panda/test_mutator.py`
- Create: `tests/panda/test_capture.py`
- Create: `tests/panda/test_dispatcher.py`

**Interfaces:**
- Produces: `PandaSceneRegistration`, `PandaMutator`, `CameraView`, `CaptureRequest`, `CaptureRecord`, and `PandaCommandDispatcher`.
- `PandaSceneRegistration.add_node(node_id, node_path, editable, parent_id=None)` maps stable IDs to `NodePath` handles.
- `capture_views(base, registration, requests, output_dir) -> tuple[CaptureRecord, ...]` writes PNGs plus camera metadata.

- [x] **Step 1: Write failing real-Panda tests**

```python
def test_mutator_changes_and_restores_registered_node(headless_base) -> None:
    node = headless_base.render.attach_new_node("door")
    registration = PandaSceneRegistration("scene")
    registration.add_node("door", node, {EditableProperty.TRANSFORM})
    mutator = PandaMutator(registration)
    inverse = mutator.apply(EditOperation("door", EditKind.SET_POSITION, [1, 2, 3]))
    assert tuple(node.get_pos()) == pytest.approx((1, 2, 3))
    mutator.apply(inverse)
    assert tuple(node.get_pos()) == pytest.approx((0, 0, 0))


def test_capture_uses_registered_camera_and_writes_manifest(software_base, tmp_path) -> None:
    records = capture_views(
        software_base,
        registered_triangle_scene(software_base),
        (CameraView("arrival", (0, -8, 3), (0, 0, 1)),),
        tmp_path,
    )
    assert records[0].path.exists()
    assert records[0].width == 640
    assert records[0].height == 360
    assert records[0].sha256
```

Also test protected properties, removed nodes, non-finite transforms, empty captures, collision-overlay visibility restoration, and restoration of the player's original camera after a capture batch.

- [x] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/panda -q`  
Expected: imports fail because Panda adapter modules do not exist.

- [x] **Step 3: Implement bounded Panda operations**

Use explicit functions for each `EditKind`; do not call `getattr` from request data. Marshal vectors/colors as finite numeric tuples. Capture at an explicit scene time when the adapter provides one, restore camera and overlay visibility in `finally`, and use Panda's software offscreen pipe for automated capture tests.

- [x] **Step 4: Implement dispatcher operations**

Map only `scene_summary`, `inspect_nodes`, `preview_changes`, `capture_views`, `undo_changes`, and `close_scene` to the registry, overlay, mutator, and capture service. `apply_changes` delegates to the registered project apply adapter in Task 6.

- [x] **Step 5: Verify and finish ILM-0401**

Run: `uv run pytest tests/panda tests/core -q`  
Expected: all Panda and core tests pass. Mark ILM-0401 `[x]` and ILM-0501 `[~]`.

---

### Task 5: Run artifacts, trusted project registry, and workbench lifecycle

**Files:**
- Create: `src/illuminate/server/artifacts.py`
- Create: `src/illuminate/server/projects.py`
- Create: `src/illuminate/server/sessions.py`
- Create: `src/illuminate/server/client.py`
- Create: `tests/server/test_artifacts.py`
- Create: `tests/server/test_projects.py`
- Create: `tests/server/test_sessions.py`

**Interfaces:**
- Produces: `RunArtifacts`, `ProjectConfig`, `ProjectRegistry`, `Session`, `SessionManager`, and `BridgeClient`.
- `ProjectRegistry.load(path) -> ProjectRegistry` reads trusted local TOML whose project IDs map to fixed executable/arguments/cwd/environment allowlists.
- `SessionManager.launch(project_id, scene_id, run_dir, visible) -> Session` owns one child and bridge client.

- [x] **Step 1: Write failing lifecycle and containment tests**

```python
def test_run_artifacts_reject_paths_outside_run_root(tmp_path) -> None:
    artifacts = RunArtifacts(tmp_path / "run")
    with pytest.raises(ArtifactPathError):
        artifacts.path("../escape.json")


def test_launch_uses_registered_command_not_request_command(tmp_path) -> None:
    registry = registry_with_fake_project(tmp_path)
    manager = SessionManager(registry)
    session = manager.launch("fixture", "triangle", tmp_path / "run", visible=False)
    assert session.project_id == "fixture"
    assert "caller-command" not in session.launch_argv


def test_close_escalates_after_bounded_grace_period(fake_hung_process) -> None:
    manager = manager_with(fake_hung_process)
    manager.close("s1", discard_unapplied=True)
    assert fake_hung_process.terminate_called
    assert fake_hung_process.kill_called
```

Also test startup timeout, bad handshake, premature process exit, unique run creation, refusal to overwrite a non-run directory, dirty-close refusal, and token absence from every artifact.

- [x] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/server -q`  
Expected: imports fail because server modules do not exist.

- [x] **Step 3: Implement artifacts and project configuration**

Write JSON through temporary sibling files followed by `os.replace`. Project TOML contains fixed `python`, `module`, `cwd`, allowed `scene_ids`, and non-secret environment additions. Runtime-injected port/token/run values are appended internally and cannot be supplied as arbitrary launch arguments.

- [x] **Step 4: Implement session lifecycle**

Start the visible Panda process normally and non-visible helpers with hidden-window flags on Windows. Await the bridge address/ready record through a one-use inherited readiness file beneath the run directory, delete it after connecting, and enforce bounded graceful/terminate/kill cleanup.

- [x] **Step 5: Verify and finish ILM-0501**

Run: `uv run pytest tests/server -q`  
Expected: all artifact and lifecycle tests pass. Mark ILM-0501 `[x]` and ILM-0601 `[~]`.

---

### Task 6: Apply gate and MCP tools

**Files:**
- Create: `src/illuminate/adapters.py`
- Create: `src/illuminate/server/apply.py`
- Create: `src/illuminate/mcp_server.py`
- Create: `tests/test_apply.py`
- Create: `tests/test_mcp_server.py`

**Interfaces:**
- Produces: `ApplyAdapter`, `ApplyPlan`, `ApplyReport`, the eight spec-defined MCP tools, and the `illuminate` skill.
- `ApplyAdapter.plan(scene_id, base_fingerprint, operations) -> ApplyPlan`
- `ApplyAdapter.validate(plan) -> ValidationReport`
- `ApplyAdapter.persist(plan) -> ApplyReport`

- [x] **Step 1: Write failing apply-gate tests**

```python
def test_apply_requires_latest_revision_comparison_and_approval(apply_fixture) -> None:
    with pytest.raises(ApplyBlockedError, match="approval"):
        apply_fixture.apply(expected_revision=2, approval_note="")
    with pytest.raises(ApplyBlockedError, match="comparison"):
        apply_fixture.apply(expected_revision=2, approval_note="approved")


def test_source_conflict_preserves_original(tmp_path) -> None:
    target = tmp_path / "scene.json"
    target.write_text('{"revision":1}', encoding="utf-8")
    gate = apply_gate_for(target, expected_fingerprint="old")
    with pytest.raises(SourceConflictError):
        gate.apply(1, "approved after review")
    assert target.read_text(encoding="utf-8") == '{"revision":1}'
```

Test every MCP tool against a fake `SessionManager`, ensuring schema validation, compact results, absolute capture paths, revision forwarding, and no tools named `eval`, `shell`, `read_file`, or `write_file`.

- [x] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_apply.py tests/test_mcp_server.py -q`  
Expected: imports fail because apply and MCP modules do not exist.

- [x] **Step 3: Implement the apply transaction**

Require current revision, non-empty approval, matching base fingerprint, matching baseline/final view IDs, and passing adapter validation. The adapter writes a temporary sibling, parses and validates it, then calls `os.replace`. Write `apply-report.json` only after success and include exact semantic changes and destination paths.

- [x] **Step 4: Implement the stdio MCP server**

Use official MCP v2 `MCPServer` and expose exactly:

```text
launch_scene
scene_summary
inspect_nodes
preview_changes
capture_views
undo_changes
apply_changes
close_scene
```

Tool docstrings state mutation behavior and return typed JSON-compatible dictionaries. Logging goes to stderr, never stdout. Pin the resolved MCP v2 dependency in `uv.lock`.

- [x] **Step 5: Verify and finish ILM-0601**

Run: `uv run pytest -q`.  
Expected: all Illuminate tests pass and all eight MCP tools satisfy their schemas. Mark ILM-0601 `[x]` and ILM-0701 `[~]`.

---

### Task 7: Littleglow adapter, waystation cleanup, and end-to-end proof

**Files in the separate Littleglow project checkout:**
- Create: `src/littleglow/client/scene_overrides.py`
- Create: `src/littleglow/client/illuminate_waystation.py`
- Create: `assets/scenes/tutorial-waystation.illuminate.json`
- Create: `illuminate.project.toml`
- Create: `tests/client/test_scene_overrides.py`
- Create: `tests/client/test_illuminate_waystation.py`
- Modify: `src/littleglow/client/panda_places.py`
- Modify: `src/littleglow/client/waystation_demo.py`
- Modify: `src/littleglow_render/tutorial_places.py`
- Modify: `src/littleglow/client/tutorial_place_data.py`
- Modify: `pyproject.toml`
- Modify: `docs/tasks.md`

**Interfaces:**
- Produces: `SceneOverrideDocument`, `LittleglowApplyAdapter`, `register_waystation_scene(app)`, and `littleglow-illuminate-waystation`.
- The override document permits only spec-approved visual fields keyed by known semantic IDs.
- The regular `littleglow-waystation-demo` loads the same applied override without starting Illuminate.

- [x] **Step 1: Update Littleglow requirements before implementation**

Add EARS requirements covering visual override containment, protected gameplay fields, semantic node stability, visible door anchoring, and clean-relaunch equivalence. Mark the Illuminate adapter subtask `[~]` beneath TUT-0402; keep TUT-0402 itself `[~]` until human acceptance.

- [x] **Step 2: Write failing override and adapter tests**

```python
def test_override_rejects_gameplay_and_unknown_fields(tmp_path) -> None:
    path = write_override(tmp_path, {"charm-door": {"destination_place_id": "evil"}})
    with pytest.raises(SceneOverrideError, match="destination_place_id"):
        SceneOverrideDocument.load(path, known_node_ids={"charm-door"})


def test_applied_preview_matches_clean_relaunch(tmp_path) -> None:
    first = launch_headless_waystation(tmp_path)
    first.preview(position_edit("charm-door", (3.2, 4.6, 0.0)))
    first.capture_required_comparison()
    first.apply("approved test change")
    expected = first.inspect("charm-door")
    first.close(discard_unapplied=False)

    second = launch_headless_waystation(tmp_path)
    assert second.inspect("charm-door") == expected
    second.close(discard_unapplied=True)
```

Add scene-readability structural tests asserting a visible threshold node, dark aperture, amber spill light, door interaction within the threshold bounds, distinct Fairy Ring and Hearthhollow path anchors, and absence of the old `soft-path` stretched sphere.

- [x] **Step 3: Run tests and verify RED**

Run from Littleglow: `uv run pytest tests/client/test_scene_overrides.py tests/client/test_illuminate_waystation.py -q`  
Expected: imports fail because the override and adapter modules do not exist.

- [x] **Step 4: Implement the protected Littleglow adapter**

Register stable semantic nodes for the waystation root, communal lantern, Charm threshold/aperture/spill light, Fairy Ring anchor, Hearthhollow trail, decorative details, collision preview, avatar, and canonical cameras. Fingerprint the base manifest plus override document. Persist only visual override keys; reject all other keys before temporary-file creation.

- [x] **Step 5: Establish the cleaned structural baseline**

Replace the stretched-sphere path builder with a shallow trail and golden-angle stepping stones. Build the Charm Hollow entrance from overlapping root segments around a dark recessed aperture with a restrained amber point light. Place the semantic interaction marker inside the visible threshold. Arrange the scene according to the approved south/center/west/east/north composition and 70:20:10 moss/bark/amber palette.

- [x] **Step 6: Run the real Illuminate visual workflow**

Launch `waystation`, capture all six canonical baseline views, inspect only the relevant semantic nodes, preview bounded adjustment batches, undo rejected experiments, and create the final same-camera contact sheet. Do not call `apply_changes` until the user explicitly approves the comparison.

- [ ] **Step 7: Apply, relaunch, and verify**

After approval, call `apply_changes`, close the workbench, launch a clean ordinary `littleglow-waystation-demo`, and recapture the canonical views. Assert the clean scene matches the persisted semantic values and the entrance/return interactions remain functional.

Run:

```powershell
uv run python -m compileall -q src
uv run pytest -q
```

Expected: the full Littleglow suite passes, the applied override contains no protected fields, and no Panda tasks/processes remain after tests.

- [ ] **Step 8: Complete human acceptance and task tracking**

The user verifies that the clearing reads as a tended woodland waystation, the Charm Hollow entrance and onward route are identifiable without explanation, fades and round-trip transitions work, and no collision/camera regression is visible. Mark the adapter subtask and TUT-0402 `[x]`, then mark Illuminate ILM-0701 `[x]` and ILM-0801 `[~]`.

---

### Task 8: Package the proven workflow as a reusable Codex plugin

**Files:**
- Create: `plugin/illuminate/.codex-plugin/plugin.json`
- Create: `plugin/illuminate/.mcp.json`
- Create: `plugin/illuminate/skills/illuminate/SKILL.md`
- Create: `plugin/illuminate/skills/illuminate/agents/openai.yaml`
- Create: `tests/test_plugin_contract.py`

**Interfaces:**
- Produces: the installable local `illuminate` plugin, its MCP declaration, and the guided `$illuminate` skill.
- Consumes: the proven CLI entry point and artifact contract from Tasks 1-7.

- [ ] **Step 1: Write the failing plugin contract test**

```python
def test_plugin_exposes_proven_server_and_four_stage_skill() -> None:
    plugin = load_json("plugin/illuminate/.codex-plugin/plugin.json")
    mcp = load_json("plugin/illuminate/.mcp.json")
    skill = Path("plugin/illuminate/skills/illuminate/SKILL.md").read_text()
    assert plugin["name"] == "illuminate"
    assert "illuminate" in mcp["mcpServers"]
    assert "Preparing the scene" in skill
    assert "Setting the scene" in skill
    assert "apply_changes" in skill
```

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run pytest tests/test_plugin_contract.py -q`  
Expected: failure because the plugin package does not exist.

- [ ] **Step 3: Create the plugin and skill from the proven run**

Use the plugin-creator and skill-creator workflows. The skill presents these four visible stages and keeps only one active:

```text
1. Preparing the scene.
2. Seeing the scene.
3. Shaping the scene.
4. Setting the scene.
```

It must capture a baseline before previewing, avoid redundant captures, inspect only affected semantic nodes, require comparison and validation before applying, never infer apply approval from a preview request, and preserve the spec's repair and convergence rules.

- [ ] **Step 4: Validate, install locally, and smoke-test discovery**

Run the plugin-creator validator and skill-creator validator, add the plugin to the personal marketplace using the plugin-creator flow, install it locally, and start a fresh Codex task to confirm `$illuminate` discovers the MCP server and can launch the Littleglow adapter without applying a change.

- [ ] **Step 5: Finish ILM-0801**

Run: `uv run pytest -q` and both official validators.  
Expected: every Illuminate test passes, the installed plugin is discoverable, and the smoke-test run closes without dirty edits or leaked processes. Mark ILM-0801 `[x]`.

---

## Plan self-review

- **Spec coverage:** Tasks 1-2 cover protocol, semantic identity, and reversible overlays; Tasks 3-4 cover authenticated transport, Panda main-thread ownership, inspection, edits, and captures; Tasks 5-6 cover lifecycle, artifacts, apply safety, and MCP; Task 7 proves the adapter, persistence boundary, visual cleanup, relaunch, and human acceptance; Task 8 packages the proven workflow as the guided skill and plugin.
- **Scope:** Vertex/armature/shader/texture authoring, remote clients, shipped-game attachment, and arbitrary code execution remain excluded.
- **Type consistency:** `SceneRegistry`, `Overlay`, `EditOperation`, `PandaSceneRegistration`, `SessionManager`, and `ApplyAdapter` each have one owner and flow forward through the plan.
- **Safety:** Tokens remain out of protocol artifacts; source writes are adapter-bounded, conflict-checked, validated, temporary, and atomically replaced.
- **No placeholders:** Every task names concrete files, interfaces, failure tests, implementation behavior, verification commands, and completion state.
