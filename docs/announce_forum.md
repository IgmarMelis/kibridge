Hi all,

I just published **KiBridge & KiRouter** — an open-source pair of tools for KiCad 10 that together let you autoroute boards through a local browser-based UI, then bring the routes back into KiCad with one click.

Repo: https://github.com/IgmarMelis/kibridge
Apache 2.0 licensed.

## What it is

**KiBridge** is a KiCad plugin (5 toolbar buttons under `PSS Tools`). **KiRouter** is a small Flask web app that opens in your browser at `localhost:8765`.

The plugin sends your board to KiRouter, which drives [Freerouting](https://github.com/freerouting/freerouting) as a subprocess. When routing finishes, you click `KiBridge: Import from KiRouter` in KiCad — the routed tracks come back in. The plugin makes an automatic timestamped backup of your `.kicad_pcb` first.

**Everything is local.** The server refuses to bind to anything but `127.0.0.1`. No accounts, no telemetry, no cloud. Designs never leave your machine.

## Why two tools instead of one big plugin

The plugin runs inside KiCad's embedded Python so it has to stay tiny, dependency-free (stdlib only), and crash-resistant. The web app runs in its own process with Flask, threading, subprocess calls to Freerouting, and a Canvas-based board renderer. Splitting them keeps the plugin safe and lets the routing UI evolve independently.

## Bonus: AI workflow (optional)

There's also a separate workflow where the plugin generates a `kibridge_workspace/` folder that GitHub Copilot or any LLM can read. The LLM writes back an `actions.json` of suggested changes; the plugin validates and applies them through an AST sandbox (so the LLM can describe changes but can't execute arbitrary Python). This is purely high-level review — placement suggestions, design rule analysis, that kind of thing. The actual routing is done by Freerouting because LLMs aren't good at grid routing.

## What it doesn't do

- AI autorouting (LLMs don't work for this — token budget, spatial precision, DRC convergence)
- Schematic editing (PCB only)
- Cloud sync of any kind
- One-click "fix my board" — every modification goes through a confirm dialog

## Status

Tested on Windows 10/11 + KiCad 10.0.1 + Freerouting 2.2.3 against a real Arduino Nano Every + L7805 + LED indicator board. Found and fixed 6 bugs along the way, including an interesting one where Freerouting v2.x writes SES coordinates at 10× the precision it declares — KiBridge auto-detects the actual scale by comparing SES placement with the original board JSON.

10-phase CI with 188+ test cases.

macOS and Linux *should* work (the code is portable) but the install scripts are Windows-only right now. If anyone tests on those platforms please open an issue with what happens.

## Install

Detailed instructions in the README. Short version:

1. Download the zip from the releases page
2. Run `INSTALL.bat` (copies the plugin into KiCad's plugins folder)
3. Install Java 17+ and drop a Freerouting JAR into `router/kirouter/freerouting/bin/`
4. `cd router && START_KIROUTER.bat`
5. Open your board in KiCad, click `KiBridge: Send to KiRouter`

Happy to answer questions and especially happy to hear about boards where it breaks. Real failure reports are how we move from v1.0 to v1.1.

— Igmar
