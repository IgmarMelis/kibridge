I've been working on this for the past week and just open-sourced it: **KiBridge & KiRouter** — a KiCad plugin plus a local browser-based autorouter UI that drives Freerouting under the hood.

**Repo:** https://github.com/IgmarMelis/kibridge (Apache 2.0)

## What it does

You click `KiBridge: Send to KiRouter` in KiCad's toolbar. Your browser opens at `localhost:8765` with your board rendered on an HTML5 canvas — pan, zoom, layer toggles, net highlighting, the works. You hit `Auto-route`, watch Freerouting work in real time with progress bar and log tail, then `Accept routes`. Back in KiCad you click `KiBridge: Import from KiRouter`, confirm the dialog (which makes an automatic backup of your `.kicad_pcb`), and the tracks land in your board. Save with Ctrl+S.

It also has a built-in DRC with 6 rules and on-canvas crosshair markers for violations.

## Why I built it

The Freerouting GUI is awkward to drive manually — export DSN, switch windows, import SES, etc. I wanted one button in KiCad and a nice browser UI for everything else. Plus I wanted a sandbox for AI-assisted PCB review without giving an LLM the keys to my `.kicad_pcb` file (that's a separate workflow via a watched workspace folder).

## What it doesn't do

- **AI autorouting.** LLMs aren't good at grid routing. Token budgets explode on real netlists. Freerouting was built for this and we use it.
- **Cloud anything.** Server refuses to bind to 0.0.0.0. Plugin refuses non-localhost URLs. Your boards are your IP.
- **One-click magic.** Every modification goes through a confirm dialog.

## Tech

Plugin is pure stdlib Python (KiCad's embedded interpreter). Web app is Flask + Canvas. Freerouting is called as a subprocess so the Apache 2.0 / GPL v3 licenses stay cleanly separated.

10-phase CI with 188+ test cases. Tested on Windows 10/11 + KiCad 10.0.1 + Freerouting 2.2.3.

## Bugs already fixed in the 1.0.x patch series

Found and fixed against a real Arduino Nano Every + L7805 PCB. Highlights:
- Freerouting v2.x writes SES coordinates at 10× the precision it declares — KiBridge auto-detects by comparing SES placement to original board JSON
- NPTH mechanical pads (no pad number) were breaking DSN export
- Bracket characters in padstack names broke Freerouting's tokenizer
- Edge.Cuts bbox was being trusted even when smaller than components

Real boards find bugs no synthetic test could.

## What I'd love feedback on

- macOS / Linux — code is portable but I only have Windows scripts so far
- KiCad 9 — currently 10 only; some API differences
- Weird footprint cases — custom shapes, hierarchical sheets, multi-board projects
- Performance on big boards (100+ components, 200+ nets)

Open an issue if it breaks on your board. Happy to ship v1.0.7 the same day for clean reproducible bugs.
