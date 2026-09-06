# Illuminate implementation blueprint

## Package layout

```text
src/illuminate/
  protocol.py
  core/                 semantic registry, edits, revisioned overlay
  bridge/               authenticated socket and Panda command queue
  panda/                NodePath registration, mutation, capture, dispatch
  server/               artifacts, projects, sessions, apply
  adapters.py           adapter protocols and immutable plans/reports
  mcp_server.py          eight stdio MCP tools
plugin/illuminate/       packaged MCP declaration and guided Codex skill
```

## Layer rules

```text
protocol <- core <- bridge
                <- server
protocol/core <- panda
protocol/core/bridge/server <- project adapters
```

`protocol` and `core` import only the standard library. `bridge` owns sockets and queues but no project code. `panda` is the only reusable layer that imports Panda3D. `server` may import the official MCP SDK only in `mcp_server.py`. Target projects register semantic objects and own persistence.

## Data flow

```text
Codex -> stdio MCP tool -> SessionManager -> BridgeClient
  -> authenticated loopback JSON -> CommandQueue
  -> Panda main-thread dispatcher -> registry/overlay/mutator/capture
  -> compact response and run artifacts
```

Preview validates a complete batch, captures inverses, applies operations, and advances the overlay revision. Apply verifies approval, view parity, validation, revision, and base fingerprint before delegating an atomic source write. No generic layer accepts source code or a filesystem path from a scene request.

## Error model

Expected failures use typed protocol, authentication, revision-conflict, edit-rejected, session, artifact, validation, and source-conflict exceptions. Terminal cleanup is idempotent. Error responses expose operation and semantic IDs but redact credentials and internal object representations.

