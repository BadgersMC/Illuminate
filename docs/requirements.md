# Illuminate requirements

## Protocol

### REQ-PRT-001 — Versioned messages
When a bridge request is decoded, the system shall accept only the current protocol version and a registered operation.

### REQ-PRT-002 — Bounded messages
If a message exceeds 1 MiB or an identifier exceeds 128 UTF-8 characters, the system shall reject it before dispatch.

### REQ-PRT-003 — Closed schema
If a request contains unknown top-level fields, invalid JSON, or a non-object payload, the system shall return a typed protocol error without dispatch.

### REQ-PRT-004 — Typed responses
When a request succeeds or fails, the system shall encode a response carrying the matching request ID and exactly one of result or error.

### REQ-PRT-005 — Secret separation
While a session is active, authentication secrets shall remain in the handshake and process environment and shall never appear in request payloads, responses, representations, or run artifacts.

### REQ-PRT-006 — Semantic identity
When a scene object crosses the protocol boundary, the system shall identify it by a bounded adapter-registered semantic ID rather than a transient object address.

## Scene editing

### REQ-SCN-001 — Registered surface
When a scene is inspected or edited, the system shall expose only adapter-registered roots, nodes, properties, parameters, and primitive factories.

### REQ-SCN-002 — Temporary overlay
When a valid preview batch is submitted at the current revision, the system shall apply it in memory, record inverse values, and advance the revision without writing source files.

### REQ-SCN-003 — Atomic rejection
If any operation in a preview batch is invalid or fails, the system shall restore earlier operations in that batch and preserve the prior revision and history.

### REQ-SCN-004 — Revision conflict
If a preview, undo, or apply request names a stale revision, the system shall reject it without mutation.

### REQ-SCN-005 — Undo
When undo is requested at the current revision, the system shall apply recorded inverses and retain a new auditable revision.

## Bridge and capture

### REQ-BRG-001 — Loopback authentication
When the bridge starts, it shall bind only to `127.0.0.1`, accept one controlling connection, and require its random session token during the initial handshake.

### REQ-BRG-002 — Panda thread ownership
When a bridge command accesses Panda3D state, the system shall execute it through a bounded queue pumped by Panda3D's owning thread.

### REQ-BRG-003 — Bounded lifecycle
When a bridge closes or disconnects, it shall stop accepting work, resolve pending commands with typed errors, remove its Panda task, and release its socket idempotently.

### REQ-CAP-001 — Canonical capture
When registered views are captured, the system shall restore the original camera and overlay visibility after writing images and metadata.

### REQ-CAP-002 — Compact inspection
When scene information is requested, the system shall return bounded semantic summaries or requested-node deltas rather than raw Panda objects or unbounded trees.

## Sessions and apply

### REQ-RUN-001 — Trusted launch registry
When a workbench is launched, the system shall use a trusted project configuration and shall not accept an arbitrary executable, module, working directory, environment key, or command argument from an MCP request.

### REQ-RUN-002 — Contained artifacts
When a run artifact is written, its resolved path shall remain beneath the selected run directory and the write shall use atomic replacement.

### REQ-RUN-003 — Process cleanup
When a session closes, the system shall request graceful shutdown and then use bounded terminate and kill escalation if needed.

### REQ-APP-001 — Explicit apply gate
When changes are applied, the system shall require the current revision, a non-empty approval note, matching baseline/final view sets, and passing adapter validation.

### REQ-APP-002 — Source conflict protection
If the source fingerprint differs from the baseline, the system shall block apply and leave the existing source unchanged.

### REQ-APP-003 — Adapter-owned persistence
When apply succeeds, only the project adapter shall serialize, validate, and atomically replace its allowlisted destination files.

## Integration and packaging

### REQ-ADP-001 — Protected Littleglow semantics
When Littleglow consumes an Illuminate override, the system shall reject destination, spawn, interaction, collision-role, progression, or distributed-state fields.

### REQ-ADP-002 — Clean relaunch equivalence
When an approved Littleglow overlay is applied, a clean ordinary waystation launch shall reproduce the applied semantic visual values without Illuminate running.

### REQ-ADP-003 — Readable waystation
When a new player enters the private waystation, the rendered composition shall visibly distinguish the tended clearing, Charm Hollow threshold, Fairy Ring side, and onward Hearthhollow path.

### REQ-PLG-001 — Guided workflow
When the Illuminate skill is invoked, it shall expose the four stages Preparing, Seeing, Shaping, and Setting; preserve baseline and review artifacts; and never infer apply approval from preview approval.

