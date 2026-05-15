# Architecture

KiBridge and KiRouter are two separate tools that work together. Each runs
in a different environment, has a different job, and communicates with the
others through clean, file- or HTTP-based contracts.

## The four pieces

```
┌──────────────────┐    workspace folder    ┌──────────────────┐
│  KiBridge        │ ───  (file bridge) ──► │  Copilot/VS Code │
│  (KiCad plugin)  │ ◄─────────────────     │  (review/        │
│                  │                        │   strategy)      │
└────────┬─────────┘                        └──────────────────┘
         │
         │  HTTP (localhost:8765)
         ▼
┌──────────────────┐
│  KiRouter        │
│  (web app)       │
│  - Flask backend │
│  - Browser UI    │
│  - Routing engine│
└──────────────────┘
```

| Piece | Runs in | Job |
|---|---|---|
| **KiBridge plugin** | KiCad's pcbnew Python | Read/write the board. Export snapshot to disk. Apply reviews. Export to KiRouter. Import from KiRouter. |
| **Workspace folder** | Filesystem next to `.kicad_pcb` | The contract between KiBridge and Copilot. Snapshot in, review out. |
| **Copilot in VS Code** | User's editor | Review the snapshot, write `findings.md`, propose an action plan, write Python scripts that use `kibridge_api`. |
| **KiRouter** | Local Python process + browser | Visualize the board, run the autorouter, send the result back. |

## Why these boundaries?

The split is deliberate, and each line is there for a reason:

- **KiCad plugin ≠ heavy logic.** KiCad plugins run in the editor's process, with limited UI primitives and a pcbnew API that varies between KiCad versions. We keep the plugin small and reliable: just enough to export data and apply changes safely. Heavy work happens elsewhere.

- **Files between KiCad and Copilot.** Files survive crashes, are version-controllable, are diffable, are editable by humans. A live API would be faster but lose all of those properties. The slight latency of "click, refresh, click" is the price for full debuggability.

- **HTTP between KiCad and KiRouter.** The router's job is interactive and visual. A browser is the right environment. HTTP is the simplest possible protocol. Localhost-only means no auth, no privacy concerns, no cloud.

- **The router is its own product.** Someone could use KiRouter without ever installing KiBridge — paste in a `.kicad_pcb` upload, route, download. We won't ship that v1.0 but the architecture allows it.

## Safety model

The plugin enforces three guarantees regardless of what Copilot or KiRouter say:

1. **Backup before any board mutation.** The `.kicad_pcb` is copied to `kibridge_workspace/backups/<timestamp>` before any change. If apply fails halfway, restoration is one file rename.
2. **Strict whitelist on incoming actions.** `actions.json` is rejected wholesale if any `op` is not in the whitelist. Modifying ops require `"confirm_changes": true` AND a second user confirmation dialog.
3. **AST-validated, sandboxed scripts.** Scripts under `kibridge_workspace/review/scripts/` may only `import kibridge_api`. Imports of `os`, `sys`, `pcbnew`, `eval`, `exec`, `open`, `__import__`, dunder access, and similar escape vectors are refused at parse time. Execution happens with a curated `__builtins__` dict.

The threat model is "Copilot makes a mistake." It is **not** an adversarial sandbox. For an adversarial threat model, scripts would have to run in a separate process with OS-level isolation; that's out of scope.

## What changed from v0.2.x

The plugin was renamed from KiBridge to KiBridge for the public release. PSS Tools (the company name) is preserved as the KiCad menu category, so the buttons live under "PSS Tools" in the External Plugins menu.

| Old | New |
|---|---|
| `kibridge` (Python package) | `kibridge` |
| `kibridge_api` (script API module) | `kibridge_api` |
| `kibridge_workspace/` | `kibridge_workspace/` |
| `kibridge_reports/` | `kibridge_reports/` |
| `*_kibridge_inspect_*.json` | `*_kibridge_inspect_*.json` |
| `*.kibridge_backup_*` | `*.kibridge_backup_*` |
| `"PSS Tools"` (KiCad category) | unchanged |

Existing workspaces from 0.2.x can be migrated by renaming the folder, or just deleted — clicking "KiBridge: Open Workspace" recreates everything.
