# Roadmap

## Done

### v0.1 — Board Inspector
Read-only inspection plugin. JSON + TXT report.

### v0.2 — Workspace + Copilot edition (this release)
Two new buttons (`KiBridge: Open Workspace`, `KiBridge: Apply Workspace`).
Full snapshot export. Validated/sandboxed apply pipeline. Mandatory
backups. Whitelisted action ops (additive + a small modifying set).

## Next

### v0.3 — Per-action approval, more modifying ops
- Replace the all-or-nothing preview dialog with checkboxes per
  operation.
- Add modifying ops behind extra guards:
  - `move_footprint(ref, x_mm, y_mm)` — limited delta only,
  - `rotate_footprint(ref, deg)`,
  - `set_net_class(net_name, class_name)`.
- Export DRC violations into `snapshot/drc_violations.json` if KiCad
  version supports programmatic DRC.

### v0.4 — Routing suggestions on User.1
- New op: `propose_route(net, via_points)` writes a polyline on
  User.1 only — no actual track creation.
- Companion command in KiCad: "Convert KiBridge guides to tracks (review
  one by one)" that asks per-segment whether to materialise it.

### v0.5 — Schematic snapshot
- Parse `.kicad_sch` and add `snapshot/schematic.json` with
  symbol/net/connection data.
- Allows Copilot to reason about whether schematic and PCB nets
  agree.

## Not on the roadmap

- Full autorouting. Out of scope by design.
- Adversarial sandboxing of scripts (subprocess isolation, seccomp,
  etc). The Copilot-mistake threat model does not require it; if
  the project ever ships scripts authored by untrusted third parties
  this would be reopened.
- Cloud / multi-user features. The whole point of the design is that
  it runs on one engineer's laptop with no service dependencies.
