# KiBridge & KiRouter v1.0.6

The first stable release of an open-source autorouter bridge for KiCad 10. Send your board to a local browser-based router, route with Freerouting, pull the result back into KiCad. Plus a sandboxed workspace for AI-assisted PCB review with GitHub Copilot.

**Tested against real boards.** Six bugs found and fixed while routing a real Arduino Nano Every + L7805 + LED PCB.

## Quick start

**1. Install the plugin (Windows, one click):**
```cmd
INSTALL.bat
```
Restart KiCad's PCB Editor. Five new buttons appear under `PSS Tools`.

**2. Install Java 17 and Freerouting (one time, ~5 min):**
- [Java 17 Temurin](https://adoptium.net/temurin/releases/)
- [Freerouting JAR](https://github.com/freerouting/freerouting/releases) → drop into `router/kirouter/freerouting/bin/`
- Full instructions: [docs/freerouting.md](docs/freerouting.md)

**3. Start KiRouter:**
```cmd
cd router
START_KIROUTER.bat
```
Browser opens at `http://localhost:8765`. First run creates a `.venv/`.

**4. Route a board:**
In KiCad: **KiBridge: Send to KiRouter** → switch to browser → **Auto-route** → **Accept routes** → back to KiCad → **KiBridge: Import from KiRouter** → **Ctrl+S**.

## What's in this release

**KiBridge plugin** — five toolbar buttons under `PSS Tools`:

| Button | Purpose |
|---|---|
| KiBridge: Inspect Board | Read-only summary, JSON + TXT report |
| KiBridge: Open Workspace | Generates `kibridge_workspace/` for Copilot |
| KiBridge: Apply Workspace | Validates and applies Copilot's actions |
| KiBridge: Send to KiRouter | POST current board to `localhost:8765` |
| KiBridge: Import from KiRouter | Pull routed result, backup, apply |

**KiRouter web app:**
- HTML5 Canvas board viewer (pan/zoom/layer toggles/net highlight)
- Auto-route button driving Freerouting subprocess (live progress + log)
- DRC checker with 6 rules and on-canvas crosshair markers
- Accept/Discard for routing results
- Send-to-KiCad instructional modal

## Architecture

![Workflow diagram](docs/images/workflow.png)

Two independent tools sharing one board JSON over `localhost` HTTP. The plugin runs inside KiCad's embedded Python (stdlib only); the web app runs in its own Python process with Flask. They talk over `127.0.0.1:8765` only — the server refuses to bind to `0.0.0.0`, the plugin refuses to talk to non-local hosts.

Freerouting is called as a clean subprocess. No license entanglement between Apache 2.0 (KiBridge) and GPL v3 (Freerouting / KiCad).

## What it doesn't do (and why)

- **AI autorouting** — LLMs can't do grid routing reliably. Token budgets explode on real netlists, spatial precision suffers, DRC convergence isn't there. Freerouting was built for this. The LLM's job is higher-level: strategy and review through the workspace folder.
- **Schematic editing** — PCB-only. The schematic is the source of truth for connectivity.
- **Cloud sync / telemetry / accounts** — none. Everything runs offline after Freerouting is installed.
- **One-click "fix my board"** — every modification goes through a confirm dialog. The user is always in the loop.

## Tested against

- Windows 10/11 + KiCad 10.0.1
- Python 3.11
- Freerouting 2.2.3 (subprocess)
- Java 17 Temurin

Reports on macOS and Linux welcomed — open an issue.

## Bugs found and fixed against a real PCB

| Version | Issue |
|---|---|
| 1.0.1 | Freerouting "0 unrouted nets" treated as fatal; analytics phone-home disabled |
| 1.0.2 | Plugin wasn't sending pad nets — KiRouter saw "Nets: 0" |
| 1.0.3 | Bracket characters `[A]` in padstack names broke Freerouting's parser |
| 1.0.4 | NPTH (unnumbered mechanical) pads broke DSN with blank pin numbers |
| 1.0.5 | Board bbox truncated to Edge.Cuts, ignoring components outside it |
| 1.0.6 | **Freerouting v2.x SES coordinate scale bug — auto-detection now compensates** |

All six found by routing a real PCB end-to-end. Unit tests pass on synthetic data; the integration bugs only show up against real KiCad output.

The 1.0.6 fix is particularly interesting: Freerouting v2.x declares `(resolution um 10)` in its SES output (matching the DSN input) but writes coordinates with 10× more precision than declared. Result: every routed track was placed 10× further from the origin than intended. KiBridge now auto-detects the real scale by cross-checking SES placement entries against the original board JSON. Robust to Freerouting fixing the bug in a future release.

## Tests

10-phase CI with 188+ test cases, all green:

```
Compile plugin              -- syntax check
Compile router              -- syntax check
AST sandbox                 22 cases
Plugin end-to-end           7 ops
KiRouter Stage-2 round-trip 30 cases
DSN/SES converters          25 cases
DRC rules                   17 cases
Routing engine + JobManager 28 cases (fake Freerouting)
Stage-3 server endpoints    25 cases (fake Freerouting)
Plugin-to-server round-trip 41 cases (fake pcbnew + fake Freerouting)
```

Stage 3 and 4 tests run in CI without a JAR or Java. Real Freerouting is only needed to actually route boards.

## Acknowledgments

- [Freerouting](https://github.com/freerouting/freerouting) — the routing engine
- [KiCad](https://www.kicad.org/) — the EDA suite everything bolts onto

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

— **Igmar Melis / PSS Tools**
