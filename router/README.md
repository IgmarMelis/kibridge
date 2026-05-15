# KiRouter

Local web app autorouter for KiCad. Companion to the
[KiBridge plugin](../plugin/).

![Sample board render](../docs/images/sample_board.png)

## What it does

KiRouter runs an HTTP server on `localhost:8765` and serves a browser UI
that visualizes a PCB and (in upcoming stages) drives an autorouter on it.
The KiBridge plugin sends the board state here over HTTP; KiRouter sends
the routed result back.

**Local-only by design.** The server binds to `127.0.0.1`. It refuses to
bind to `0.0.0.0`. Your designs never leave your machine.

## Status (v1.0.0 — Stage 3)

| Feature | Status |
|---|---|
| HTTP server (Flask) | done |
| Board state API (POST/GET/DELETE) | done |
| Browser UI with Canvas board renderer | done |
| Pan / zoom / layer toggles | done |
| Net list with click-to-highlight | done |
| Sample board loader (`Load Sample`) | done |
| Live cursor coordinates + zoom display | done |
| Freerouting subprocess integration | done |
| Auto-route button with live progress | done |
| Accept / discard routing result | done |
| DRC checker (6 rules) | done |
| DRC overlay on canvas | done |
| "Send to KiCad" button | **disabled — coming Stage 4 (KiBridge integration)** |

## Running

### Windows

Double-click `START_KIROUTER.bat`. On first run it creates a `.venv/` and
installs Flask. After that, every launch is instant. Your browser opens to
`http://localhost:8765` automatically.

### macOS / Linux

```bash
./start_kirouter.sh
```

Same first-run venv creation, same auto-launch.

### Manual

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m kirouter
```

Optional flags:

```
--host        bind host (default 127.0.0.1; refuses 0.0.0.0)
--port        bind port (default 8765)
--no-browser  do not auto-open browser
--debug       Flask debug mode
```

## Architecture

```
plugin/kibridge/  (KiCad)
        │
        │  HTTP POST /api/board
        ▼
router/kirouter/server.py     (Flask)
        │
        │ in-memory state.py
        ▼
router/kirouter/static/...    (HTML/JS/CSS Canvas UI)
```

The server is intentionally tiny: a single in-memory `BoardState`
singleton and ~150 lines of route handlers. All visualization happens
client-side in the browser. Future routing engines (Freerouting,
custom A*) will hook in via additional endpoints (`/api/route`,
`/api/result`, `/api/drc`) without changing the existing API.

## API reference

### `GET /api/health`

Liveness probe.

```json
{ "ok": true, "product": "KiRouter", "company": "PSS Tools", "version": "1.0.0" }
```

### `GET /api/info`

Summary of the loaded board (or `loaded: false` if none).

```json
{
  "loaded": true,
  "received_at": 1778410908.47,
  "source": "kibridge",
  "counts": { "footprints": 6, "tracks": 7, "vias": 2, "nets": 9 },
  "meta": { "schema_version": 3, "kicad_version": "10.0.1" }
}
```

### `POST /api/board[?source=<label>]`

Replace the current board state. Body must be JSON containing at least
`meta` and `footprints`. Returns:

```json
{ "ok": true, "received_at": "...", "info": "...same as /api/info..." }
```

### `GET /api/board`

Returns the full board JSON, or 404 if none loaded.

### `DELETE /api/board`

Clears state. Returns `{ "ok": true }`.

### `GET /api/engines`

List available routing engines and their availability.

```json
{
  "engines": [{
    "name": "freerouting",
    "available": {
      "ok": true,
      "java": "/usr/bin/java",
      "jar":  "/path/to/freerouting.jar",
      "jar_size": 12345678,
      "errors": []
    }
  }]
}
```

### `POST /api/route`

Start a routing job. Body (all optional):

```json
{ "engine": "freerouting", "max_passes": 30, "timeout_seconds": 600 }
```

Returns `202 Accepted` with the new job:

```json
{ "ok": true, "job_id": "a1b2c3d4e5f6", "status": { ... } }
```

Returns `503` if the engine is unavailable (Java or JAR missing) and
`409` if a job is already running.

### `GET /api/route/status` and `GET /api/route/status/<job_id>`

Poll a running or completed job:

```json
{ "ok": true, "active": true, "status": {
    "job_id": "a1b2c3d4e5f6",
    "status": "running",        // pending | running | done | failed
    "progress": 45.0,
    "log_tail": ["pass 12 of 30", ... ],
    "engine":  "freerouting",
    "result_summary": null
}}
```

When `status` is `done`, `result_summary` contains the counts and elapsed
time.

### `GET /api/result`

Returns the routed board (only after `done`):

```json
{
  "ok":           true,
  "engine":       "freerouting",
  "elapsed":      4.7,
  "added_tracks": [ ... ],
  "added_vias":   [ ... ],
  "board":        { ... full merged board ... }
}
```

### `POST /api/result/accept`

Replace the live board state with the route result. Subsequent
`GET /api/board` returns the routed version.

### `POST /api/drc`

Run DRC against the current board. Returns:

```json
{
  "ok":     true,
  "total":  3,
  "counts": { "error": 2, "warning": 1, "info": 0 },
  "violations": [
    {
      "code":  "track_track_clearance",
      "level": "warning",
      "msg":   "Tracks on 'VCC' and 'GND' too close (edge dist 0.12mm < min 0.2mm)",
      "x_mm":  35.0, "y_mm": 18.5,
      "layer": "F.Cu",
      "nets":  ["VCC", "GND"]
    }
  ]
}
```

DRC rules implemented:
- `track_width_below_min`
- `via_diameter_below_min`
- `via_drill_below_min`
- `track_outside_board`
- `track_pad_short`
- `track_track_clearance`

## Board JSON schema

The shape KiBridge sends and KiRouter expects:

```jsonc
{
  "meta": {
    "schema_version": 3,
    "plugin_version": "1.0.0",
    "kicad_version":  "10.0.1",
    "board_path":     "...",
    "exported_at":    "ISO-8601",
    "board_bbox":     { "x_min": 0, "y_min": 0, "x_max": 60, "y_max": 40 }
  },
  "design_rules": {
    "design_settings": { "min_track_width_mm": 0.2 },
    "net_classes":     [ { "name": "Power", "track_width_mm": 0.5 } ]
  },
  "footprints": [
    { "ref": "U1", "value": "...", "x_mm": 30, "y_mm": 20,
      "layer": "F.Cu", "rotation_deg": 0,
      "pads": [
        { "number": "1", "x_mm": 26.46, "y_mm": 18.73,
          "size_mm": [1.5, 1.0], "shape": "rect", "net": "VCC" }
      ]
    }
  ],
  "tracks": [
    { "net": "VCC", "layer": "F.Cu", "width_mm": 0.5, "length_mm": 22,
      "start": { "x_mm": 8, "y_mm": 18.5 },
      "end":   { "x_mm": 33.5, "y_mm": 18.7 } }
  ],
  "vias": [
    { "net": "GND", "layer": "F.Cu/B.Cu", "x_mm": 26.46, "y_mm": 21.97,
      "width_mm": 0.6, "drill_mm": 0.3 }
  ]
}
```

A working example: `kirouter/static/sample_board.json`.

## Development

Run all KiRouter tests:

```bash
python tests/test_server_roundtrip.py     # Stage 2 — board state API
python tests/test_dsn_ses.py              # Stage 3 — DSN export, SES parser
python tests/test_drc.py                  # Stage 3 — DRC rules
python tests/test_route_engine.py         # Stage 3 — engine + JobManager
python tests/test_server_stage3.py        # Stage 3 — new endpoints
```

The Stage 3 engine + server tests use a fake Freerouting (no Java or
JAR required), so the full suite runs in CI in seconds.

Regenerate the README screenshot:

```bash
python ../scripts/render_sample.py
```
