# Illuminate

A semantic visual workbench for Panda3D, built for AI-assisted scene inspection, temporary editing, and visual review through the Model Context Protocol (MCP).

**Inspect a scene. Preview a change. Capture the result. Apply only after approval.**

Illuminate exposes named, adapter-registered objects rather than dumping a whole scene graph into an assistant's context. It grew out of development on Littleglow, a folklore-inspired Panda3D game. This repository contains the reusable workbench, not the game or its assets.

## Status

Early developer preview, version 0.1.0. The protocol, semantic editing, authenticated bridge, canonical captures, session lifecycle, and apply gate have automated tests. Project integration is still in progress; a packaged assistant plugin is not yet included. This is not a standalone 3D editor or a production security guarantee.

Windows is the primary development host. The protocol and core are platform-neutral; other platforms have not been fully validated.

## What it does

- Compact scene summaries and inspection by stable semantic ID.
- Revision-checked temporary edit batches with rollback and undo.
- Canonical camera captures that restore the previous camera state.
- Authenticated loopback bridge, with Panda operations dispatched on its owning thread.
- Trusted project launch configuration and contained run artifacts.
- Explicit apply gate: matching baseline/final views, source fingerprint check, adapter validation, and an approval note.

The eight MCP tools are `launch_scene`, `scene_summary`, `inspect_nodes`, `preview_changes`, `capture_views`, `undo_changes`, `apply_changes`, and `close_scene`.

## Development setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/). Dependencies are locked in `uv.lock`.

```sh
git clone https://github.com/BadgersMC/Illuminate.git
cd Illuminate
uv sync --extra dev --locked
uv run --extra dev pytest -q
```

Panda3D capture tests require a working graphics context, even when rendering offscreen.

## Integrating a project

Your Panda3D application must supply a scene adapter: register the editable nodes and canonical views, wire the main-thread command dispatcher and bridge, and implement persistence if needed. Merely naming an arbitrary Panda3D module in the launch registry does not integrate it.

Create a local `illuminate.project.toml` (ignored by Git), replacing these illustrative paths and module with your own:

```toml
[projects.my_game]
python = "C:/projects/my-game/.venv/Scripts/python.exe"
module = "my_game.illuminate_adapter"
cwd = "C:/projects/my-game"
scene_ids = ["village"]
```

Configure your MCP client's stdio server to execute `uv run illuminate-mcp` from this repository, with these environment variables:

- `ILLUMINATE_PROJECTS_FILE`: absolute path to your trusted project TOML.
- `ILLUMINATE_RUNS_ROOT`: absolute directory for local session artifacts.

**The generic entry point has no persistence adapter.** Its `apply_changes` operation rejects persistence by default. To enable it, a project-specific server must construct `IlluminateService` with its own `apply_gate_factory`; see `src/illuminate/adapters.py` and `src/illuminate/server/apply.py` for the contracts.

## Trust boundaries

Run only trusted project modules. The launch registry is trusted local configuration, not a sandbox. Keep the bridge on loopback, keep tokens and local run artifacts private, and never treat preview approval as permission to persist source changes. The approval note is an application gate, not independent proof of human authorization: the calling client must enforce its approval policy.

No third-party game models or textures are included. Dependency licenses remain their own.

## Project structure

- `src/illuminate/protocol.py`: bounded versioned messages.
- `src/illuminate/core/`: semantic registry and reversible edits.
- `src/illuminate/bridge/`: authenticated transport and runtime lifecycle.
- `src/illuminate/panda/`: scene registration, mutation, dispatch, and captures.
- `src/illuminate/server/`: launch configuration, sessions, artifacts, and apply gate.
- `src/illuminate/mcp_server.py`: MCP tools and stdio entry point.
- `tests/`: protocol, editing, bridge, capture, and server tests.

Read the [requirements](docs/requirements.md), [architecture](docs/implementation.md), and [task sheet](docs/tasks.md) for implemented behavior and remaining work. Contributions should preserve layer boundaries and include regression tests for behavior changes.

## License

[MIT](LICENSE).
