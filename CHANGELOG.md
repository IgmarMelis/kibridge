# Changelog

All notable changes to KiBridge & KiRouter are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.6] — 2026-05-12

### Fixed
- **The big one: Freerouting SES coordinate scale mismatch.**
  Freerouting v2.x declares `(resolution um 10)` in its SES output
  (matching the DSN input) but writes coordinates with 10× more
  precision than declared — effectively `0.01 µm` per unit instead of
  the documented `0.1 µm`. This caused all routed tracks to be placed
  10× further from the origin than they should be, so the routes
  visually appeared in empty space far from the components both in
  KiRouter's canvas and after importing into KiCad.

  The SES parser now auto-detects the actual scale by cross-checking
  the SES placement section against the reference board's known
  footprint positions. If Freerouting reports A1 placed at unit
  coordinate `2055500` but we know A1 is really at `20.555 mm`, the
  parser derives the true `mm_per_unit` from the ratio and applies it
  to every track and via in the file.

  Robust to Freerouting fixing this bug in a future release: if the
  declared resolution matches reality, the detected ratio just
  confirms it.



### Fixed
- **Board bounding box now actually contains the board.** The plugin
  was trusting `GetBoardEdgesBoundingBox()` (the Edge.Cuts outline),
  which on in-progress boards is often smaller than the components or
  missing entirely. We now take the union of: the Edge.Cuts bbox (if
  any), every footprint origin, and every pad position — then add a
  10mm margin. Effect: Freerouting receives a workspace large enough
  to actually route in, and the KiRouter canvas viewport zooms to
  cover the whole design instead of cropping components.
- **Server-side defensive bbox expansion** in `BoardState.set()`. Even
  if a client (the plugin, or a curl POST) sends a too-small bbox,
  KiRouter recomputes it from the actual pad/track/via positions before
  storing. The plugin and the server fix the same problem from both
  ends — belt-and-braces.

### Added
- **"Send to KiCad" button is now active.** Clicking it opens a modal
  showing the current routing state (engine, track count, vias) and
  step-by-step instructions for completing the import in KiCad. The
  browser cannot directly trigger a KiCad action plugin (cross-origin
  security boundary), so the workflow remains: click here for the
  reminder, then switch to KiCad and click `KiBridge: Import from
  KiRouter`.



### Fixed
- **DSN exporter: NPTH (non-plated through-hole) / mechanical pads.**
  KiCad allows pads with no pad-number (typically used for mounting holes
  or mechanical resistor terminals). The DSN exporter was emitting these
  as `(pin <padstack>  <x> <y>)` with a blank number, which Freerouting
  rejects with `Package.read_pin_info: number expected`. Such pads are
  now skipped both in the component image and in the per-net pin list,
  so the structure stays consistent. (Bug surfaced with an Arduino Nano
  Every footprint where R1 had 4 pads, two of them unnumbered.)

## [1.0.3] — 2026-05-11

### Fixed
- **DSN exporter: bracket characters in padstack names.** Names like
  `Rect[A]Pad_1200x1600_um` were being split by Freerouting's tokenizer
  on the `[` character, causing the parser to fail with
  `Package.read_pin_info: number expected at 'img_R1'`. Padstack names
  are now plain alphanumeric + underscore: `Rect_Pad_1200x1600_um`,
  `Round_Pad_600_um`.

## [1.0.2] — 2026-05-11

### Fixed
- **Plugin: missing pad-level data in the board JSON sent to KiRouter.**
  `build_board_json` was reusing `workspace_exporter._export_footprints`,
  which only emits `pad_count` (an integer summary for the Copilot
  workspace) and omits per-pad coordinates, sizes, and net names. The
  server therefore reported "Nets: 0" and Freerouting saw a board with
  no unrouted nets. The plugin now uses a dedicated
  `_export_footprints_with_pads` that walks every pad and includes its
  net via `pad.GetNetname()`.

## [1.0.1] — 2026-05-11

### Fixed
- **Freerouting integration: "0 unrouted nets" no longer treated as a
  failure.** When the board has nothing to route, Freerouting exits
  cleanly without writing a `.ses` file. The runner now detects this
  case from the log output and synthesizes an empty session so the
  caller can proceed normally instead of raising `FreeroutingFailed`.
- **Freerouting analytics phone-home disabled.** Added
  `-Dfreerouting.analytics.enabled=false` to the subprocess command
  line — proper local-only hygiene.

### Added
- **Debug DSN/SES copies.** Every routing run now saves the input DSN
  (and the output SES if produced) to `~/.kirouter/debug/last_*.dsn`
  for inspection. Best-effort: failures here don't block routing.


- **`plugin/kibridge/kirouter_client.py`** — pure-stdlib (urllib) HTTP
  client for the plugin side. Builds the board JSON in KiRouter's schema
  from a KiCad `Board`, POSTs to `/api/board`, GETs `/api/result`, and
  applies tracks/vias back to the open board with proper net resolution
  (mm → nm conversion, layer mapping, net lookup by name). Refuses
  non-localhost hosts at the URL level.
- **`KiBridge: Send to KiRouter`** plugin button. Probes the server first
  (clear error if KiRouter isn't running), then sends the current board.
  Shows a dialog with the count of footprints/tracks/vias sent and
  next-step instructions.
- **`KiBridge: Import from KiRouter`** plugin button. Probes the server,
  confirms the loaded board matches (best-effort path match), shows a
  full confirmation dialog (engine, elapsed time, counts of new tracks
  and vias, warning if path mismatch), backs up the `.kicad_pcb` with
  the `kibridge_backup_` prefix, applies tracks/vias, and tells the user
  to press Ctrl+S. Errors per-item are surfaced without aborting the
  whole import.
- Two new icons (`icon_send.png`, `icon_import.png`) in the plugin
  toolbar.

### Added (v1.0 polish)
- `docs/images/workflow.png` — the architecture diagram for the README.
- `scripts/render_workflow.py` — regenerates the diagram from code.
- `tests/test_kirouter_client.py` — 41-case round-trip test that uses
  a fake `pcbnew` module + a `urllib.urlopen` monkey-patch routing into
  a Flask test client + the fake-Freerouting from Stage 3. Exercises
  the full plugin↔router pipeline including the apply-to-board step
  (verifies nm coords, layer mapping, net resolution, unknown-net
  skip, and backup file creation).
- Final top-level README rewrite with screenshots, workflow diagram,
  full feature list, honest scope statement (what we do NOT do and why),
  and the 10-phase CI explanation.

### Added
- **Project rebranding** from PSS KiCad Agent → KiBridge (plugin) +
  KiRouter (web app). "PSS Tools" preserved as the KiCad menu category
  (company signature).
- Apache 2.0 licensing, public-facing README, NOTICE, CONTRIBUTING.
- Monorepo layout: `plugin/kibridge/` + `router/kirouter/`.
- One-click `INSTALL.bat` / `UNINSTALL.bat` on Windows.
- New module name `kibridge_api` (was `pss_api`); workspace folder is now
  `kibridge_workspace/` (was `pss_workspace/`); backups suffixed
  `kibridge_backup_<ts>` (was `pss_backup_<ts>`).

### Added (Stage 2)
- **KiRouter web app** (`router/kirouter/`):
  - Flask HTTP server, binds `127.0.0.1:8765` only (refuses `0.0.0.0`).
  - In-memory `BoardState` with thread-safe POST/GET/DELETE/info endpoints.
  - Browser UI: HTML5 Canvas board renderer with pan/zoom, layer toggles,
    net list with click-to-highlight, sample board loader, live cursor
    coordinates, and zoom % indicator.
  - Sample LED-blinker board JSON for first-run demo.
  - `START_KIROUTER.bat` (Windows) and `start_kirouter.sh` (macOS/Linux)
    one-click launchers with first-run venv + dep install.
  - Round-trip tests (`router/tests/test_server_roundtrip.py`) — 30 cases.
- `docs/images/sample_board.png` rendered from the sample for the README.
- `scripts/render_sample.py` regenerates the screenshot.

### Added (Stage 3)
- **Freerouting integration** (`router/kirouter/freerouting/`):
  - `dsn_export.py` — Specctra DSN exporter (board JSON → `.dsn` text).
    Declares `(resolution um 10)` so coordinates are emitted as
    `mm × 10000` for sub-micron precision.
  - `ses_import.py` — Specctra SES parser (s-expression tokenizer +
    semantic walk → tracks/vias in our schema).
  - `runner.py` — subprocess runner. Locates the JAR (env var, repo
    `bin/`, or `~/.kirouter/`), checks Java, runs headless, captures
    stdout, surfaces clean errors (`FreeroutingNotFound`, `JavaNotFound`,
    `FreeroutingFailed`).
- **Routing engine layer** (`router/kirouter/router_engine/`):
  - `Engine` Protocol with one implementation: `FreeroutingEngine`.
  - `JobManager` — single-active-job state machine with thread-safe
    transitions (pending → running → done/failed), bounded log tail,
    progress callbacks.
- **DRC checker** (`router/kirouter/drc.py`) — pragmatic first-pass
  rules: track width below min, via diameter/drill below min, track
  endpoint outside board outline, track-pad short, track-track
  clearance (different nets, same layer).
- **New API endpoints:**
  - `GET  /api/engines` — list available engines + diagnostics.
  - `POST /api/route` — start a routing job (returns `202` + `job_id`).
  - `GET  /api/route/status[/<job_id>]` — poll progress + log tail.
  - `GET  /api/result` — get the routed board (only after `done`).
  - `POST /api/result/accept` — replace board state with the route
    result.
  - `POST /api/drc` — run DRC and return violations.
- **UI updates:**
  - **Auto-route** button now active. Shows live progress bar, percent
    indicator, scrolling log tail of the Freerouting subprocess, and an
    Accept/Discard panel when complete.
  - **Run DRC** button. Violations listed in a sidebar panel and drawn
    as red/yellow crosshair markers on the canvas.
  - Net counts now distinguish routed vs. unrouted.
- **Documentation:**
  - `docs/freerouting.md` — Java + JAR setup walkthrough, troubleshooting,
    explanation of why we don't bundle Freerouting (GPL/Apache compat).
- **Tests** (all green):
  - `router/tests/test_dsn_ses.py` — DSN export shape + SES parser.
  - `router/tests/test_drc.py` — 17 cases across all six DRC rules.
  - `router/tests/test_route_engine.py` — engine + JobManager tests
    using a fake Freerouting (subprocess-free, runs in CI without Java).
  - `router/tests/test_server_stage3.py` — all new server endpoints
    end-to-end with the same fake.

### Coming in 1.0 (Stage 4)
- Two new KiBridge plugin buttons:
  - **KiBridge: Send to KiRouter** — POST current board to
    `localhost:8765/api/board`.
  - **KiBridge: Import from KiRouter** — pull `/api/result`, validate,
    backup the `.kicad_pcb`, apply tracks/vias.
- Polish: demo gif, final README screenshots, GitHub release notes.

### Breaking changes from 0.2.x
- Module rename: scripts under `pss_workspace/review/scripts/` that
  used `import pss_api` must be updated to `import kibridge_api`.
- Folder rename: existing `pss_workspace/` folders should be renamed to
  `kibridge_workspace/`, or just delete them and re-run "Open Workspace".

## [0.2.1] — 2026-05-10

### Added
- Three distinct toolbar icons (blue magnifying glass, orange folder
  with up-arrow, green checkmark) replacing KiCad's default puzzle
  piece for each of the three plugin buttons.

## [0.2.0] — 2026-05-09

### Added
- "Open Workspace" + "Apply Workspace" action plugins.
- Workspace folder bridge between KiCad and VS Code/Copilot.
- AST-validated, sandboxed Python script runner.
- Mandatory `.kicad_pcb` backup before every apply.
- Preview dialog with second confirmation for modifying ops.
- 6 whitelisted operations: `add_silkscreen_note`, `add_fab_note`,
  `add_user_marker`, `highlight_net`, `set_track_widths_for_net`,
  `add_stitching_via`.

## [0.1.0] — 2026-05-08

### Added
- Initial read-only board inspector.
- JSON + TXT report generation under `<board>/pss_reports/`.
