# Illuminate Design

**Status:** Proposed for implementation  
**Date:** September 4, 2026  
**Scope:** A reusable, local-first Panda3D visual workbench, MCP server, Codex skill, and first Littleglow adapter

## Purpose

Illuminate gives an agent a compact, observable way to launch, inspect, adjust, compare, and deliberately persist a Panda3D scene. It follows the artifact-backed workflow of the Codex pet creator: visual iteration is organized as a run with explicit stages, deterministic checks, review media, and a final apply gate.

Illuminate is not a replacement for Panda3D, a general 3D modeller, or an unrestricted remote Python console. Its first release exists to shorten the loop between a semantic scene description, a live Panda render, visual judgment, and a reviewable source change.

## Product boundaries

The first release shall:

- Work with any Panda3D application through a reusable bridge and project adapter.
- Ship with a Littleglow adapter and use it to revise the private waystation scene.
- Launch and close a dedicated workbench application through an adapter-owned command.
- Inspect a bounded registered scene root rather than the entire Python process.
- Apply temporary transform, color, visibility, light, camera, and registered parameter edits.
- Capture canonical and caller-selected views.
- Keep edits temporary until an explicit `apply_changes` operation.
- Produce compact JSON artifacts and image files for review.
- Persist only through an adapter-defined source writer.
- Run locally over loopback with per-session authentication.

The first release shall not:

- Expose arbitrary Python evaluation, shell execution, imports, or filesystem browsing through MCP.
- Edit mesh vertices, armatures, animation curves, shaders, or texture pixels.
- Replace Blender or another dedicated asset-authoring package.
- Connect to a shipped game client or a remote machine.
- Modify gameplay rules, distributed state, collision roles, zone destinations, or tutorial progression through visual edits.
- Apply changes automatically after a capture or visual review.

## Visible workflow

Every Illuminate run has four user-visible stages:

1. **Preparing the scene.** Resolve the project adapter, scene, launch command, registered roots, editable properties, and run directory.
2. **Seeing the scene.** Launch a clean workbench session, record a compact semantic scene summary, and capture baseline views.
3. **Shaping the scene.** Apply reversible in-memory edit batches, inspect affected nodes, and capture comparisons without modifying source files.
4. **Setting the scene.** Validate the overlay, generate before/after review artifacts, receive explicit approval, and persist with `apply_changes`.

The run remains inspectable after failure. A failed process, rejected edit, failed validation, or failed apply operation records a structured diagnostic rather than silently discarding evidence or partially changing source.

## Architecture

Illuminate consists of four independently testable parts.

### Codex skill

The `illuminate` skill owns workflow and judgment. It prepares a run, invokes the MCP tools, keeps one visible stage active, requests only useful captures, interprets deterministic validation, asks for visual approval when required, and calls `apply_changes` only after approval.

The skill favors semantic summaries and deltas over raw scene-tree dumps. It opens only the captures necessary for the current decision and retains baseline, final comparison, validation, and apply reports.

### MCP server

The MCP server is a standalone Python process using the official MCP Python SDK over stdio. It owns no Panda3D objects. It validates tool requests, manages workbench subprocesses, connects to the bridge over loopback, converts bridge responses into compact MCP results, and writes run artifacts only beneath the selected run directory.

### Panda bridge

The reusable bridge is imported by a target Panda3D workbench application. It registers one or more editable scene roots and services commands from a queue on Panda3D's main thread. Network or MCP worker threads never mutate `NodePath` objects directly.

The bridge exposes only registered operations and serializable values. It never accepts Python source, callables, arbitrary attribute names, or unbounded scene patterns.

### Project adapter

An adapter defines:

- How to launch the project's dedicated workbench.
- Which scenes and roots are available.
- Which semantic node identifiers and properties are editable.
- Which canonical camera views belong to each scene.
- How an approved overlay is validated and persisted.
- Which project checks must pass before an apply operation is accepted.

The reusable core depends only on adapter protocols. Project adapters may depend on their projects; projects do not import an MCP server.

## Process and transport model

The MCP server launches the adapter's dedicated Panda3D workbench with a loopback port, random single-session token, scene identifier, and run directory. Secrets are passed through the child environment and are never written to run artifacts or returned by scene tools.

The bridge binds only to `127.0.0.1`, requires the token on its initial handshake, permits one controlling connection, limits message size, and rejects unknown operations or fields. Messages are newline-delimited JSON with a protocol version, request identifier, operation, payload, and typed success or error response.

On Windows, subprocesses launch hidden unless the requested workbench is the visible scene window. The MCP server owns cleanup of the child it launches. Closing a session first requests graceful Panda shutdown, then performs bounded termination if the process does not exit.

## Scene identity and editable state

Nodes are addressed by stable semantic identifiers registered by the project adapter, never by transient Panda object addresses or ambiguous display names. A scene summary includes only:

- Scene and session identifiers.
- Registered root identifiers.
- Semantic node identifier, kind, parent identifier, visibility, and editable-property names.
- World-space bounds and transform when requested.
- Counts of renderable, light, collision, and interaction nodes.
- Current overlay revision and dirty state.

An edit batch includes an expected overlay revision and one or more typed operations. Supported first-release operations are:

- Set local position, heading/pitch/roll, or scale.
- Set or clear color scale.
- Show or hide a node.
- Set registered light color, intensity, or attenuation.
- Set registered numeric or enum builder parameters.
- Create, update, or remove adapter-approved simple primitives.

Every accepted batch increments the overlay revision and records inverse values. `undo_changes` removes the latest batch or all batches. A stale revision is rejected without mutation.

## MCP tools

The initial public tool surface is deliberately small:

- `launch_scene(project, scene, run_dir, visible)` starts one clean workbench and returns its session metadata.
- `scene_summary(session_id, root_id?, depth?, include_bounds?)` returns bounded semantic structure.
- `inspect_nodes(session_id, node_ids, properties?)` returns current base and overlaid values.
- `preview_changes(session_id, expected_revision, operations)` atomically validates and applies one temporary batch.
- `capture_views(session_id, views, width?, height?, overlays?)` writes images and a capture manifest.
- `undo_changes(session_id, expected_revision, scope)` reverses temporary batches.
- `apply_changes(session_id, expected_revision, approval_note)` validates and persists the complete overlay through the adapter.
- `close_scene(session_id, discard_unapplied)` closes the workbench and records final status.

Tools return summaries, paths, revisions, and diagnostics rather than embedded base64 images or full source files. Captures are returned as absolute local paths for native image inspection.

## Temporary overlay and apply gate

Base scene state is immutable from Illuminate's perspective. Preview operations form an ordered in-memory overlay owned by the bridge and mirrored in the run manifest. A failed batch leaves the previous revision untouched.

`apply_changes` requires:

- A live matching session.
- The latest overlay revision.
- A non-empty approval note.
- A clean adapter validation result.
- A generated baseline/final comparison manifest.
- No unsupported or unresolved operation.

The adapter first serializes the intended source result to a temporary sibling file, validates it, and replaces the target atomically. If validation or replacement fails, the original source remains intact. The apply report lists every persisted semantic change and exact destination file.

For Littleglow, visual tuning is stored in a compact JSON override document keyed by semantic scene and node identifiers. It may override transforms, colors, light properties, visibility, registered builder parameters, and simple decorative primitives. Python manifests remain authoritative for place identity, destinations, spawn semantics, collision roles, interaction IDs, and progression.

## Run artifacts

Each run uses a self-contained directory:

```text
run/
  request.json
  session.json
  baseline/
    scene-summary.json
    captures.json
    *.png
  overlay/
    changes.json
    history.json
  final/
    captures.json
    *.png
  qa/
    comparison.json
    validation.json
    contact-sheet.png
  apply-report.json
  diagnostics.jsonl
```

Temporary bridge credentials and process handles are never stored here. Failed and abandoned runs retain enough information to understand what happened but cannot later apply without launching a new session and revalidating the overlay.

## Visual QA and token efficiency

Each adapter defines canonical views. The Littleglow waystation begins with:

- Player arrival view.
- Lanternkeeper and communal lantern view.
- Charm Hollow entrance approach.
- Fairy Ring side.
- Hearthhollow path side.
- Overhead composition view.

Illuminate creates baseline and final captures at the same camera transforms and scene time, plus a labeled contact sheet. Deterministic QA checks missing nodes, invalid transforms, non-finite values, bounds escaping the registered scene envelope, unresolved collisions, blank captures, and mismatched view sets.

Visual approval evaluates readability and composition rather than pixel equality. The skill requests a new capture only after a meaningful edit batch. Scene summaries default to shallow semantic nodes, inspection is ID-targeted, and tool results report changes rather than unchanged properties.

## Error and recovery behavior

- A bridge disconnect marks the session unavailable; no apply is possible until a fresh session restores and revalidates the overlay.
- A Panda exception becomes a typed diagnostic with operation and semantic node ID; it does not expose an interactive traceback through the bridge.
- A capture failure leaves the overlay live and retryable.
- An invalid edit batch is atomic and does not increment the revision.
- A validation failure blocks apply while preserving the temporary overlay.
- A source conflict or changed base fingerprint blocks apply and requires a fresh baseline.
- Closing with unapplied edits requires explicit discard intent.
- Repeated close and cleanup operations are idempotent.

## Testing strategy

Development follows SPEAR and TDD.

- Pure protocol tests cover schemas, revision checks, edit validation, inverse history, bounded summaries, and typed errors.
- Bridge tests use headless Panda3D with real `NodePath`, light, camera, and capture objects.
- MCP tests use a fake bridge and temporary run directory; they never need a visible window.
- Lifecycle tests launch a minimal real Panda workbench on an ephemeral loopback port and prove authentication, timeout, graceful close, and forced cleanup.
- Adapter contract tests prove that rejected operations cannot alter protected gameplay fields.
- Littleglow integration tests launch the waystation headlessly, preview and undo an edit, capture canonical views, apply an approved override in a temporary project copy, and verify the relevant client tests remain green.
- Human acceptance launches the visible waystation, produces a baseline/final contact sheet, persists the approved cleanup, relaunches from source, and confirms the scene matches the applied result.

## First Littleglow use

The first real Illuminate run cleans the private waystation:

- Replace the stretched-sphere path with a shallow worn trail and embedded stepping stones.
- Build a readable root-framed Charm Hollow opening with a dark interior and amber spill light.
- Place the door interaction directly inside the visible threshold.
- Compose arrival south, lantern and Lanternkeeper centrally, Fairy Ring west, Charm Hollow east, and closed Hearthhollow path north.
- Use moss as the dominant color, bark as support, and amber as the accent under the 70:20:10 discipline.
- Add a restrained set of seed-pod, acorn-cap, and resting-stone details.

The first use is accepted when a new player can identify the tended waystation, Charm Hollow entrance, and onward path without explanation; the entrance and return interactions are visibly anchored; before/after views exist; the applied source survives relaunch; and the full Littleglow test suite remains green.

## Delivery boundary

Illuminate lives in its own project checkout. Its reusable Python package, MCP server, tests, and documentation live there. The Littleglow adapter and scene override integration are developed as the first consumer. After the workflow is proven, the Codex skill and MCP configuration are packaged as a local personal plugin named `illuminate`.
