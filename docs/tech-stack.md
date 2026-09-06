# Illuminate technical stack

- Python `>=3.12,<3.13` managed by `uv`.
- Official MCP Python SDK v2 over stdio.
- Panda3D `1.10.16` for the reusable bridge and test workbench.
- Pillow `>=11,<12` for deterministic contact sheets.
- Pytest `>=8.3,<9` for SPEAR/TDD verification.
- Standard-library sockets, JSON, subprocess, threading, hashing, paths, and TOML before adding dependencies.
- Windows is the first supported development host; the protocol and core remain platform-neutral.

Dependency direction is `protocol <- core <- bridge/server`, with project adapters depending inward. The core and protocol packages never import Panda3D or MCP.

