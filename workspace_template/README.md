# KiBridge Workspace

This folder is the bridge between **KiCad** and **VS Code / GitHub Copilot**.
It was created automatically by the KiBridge plugin.

## How to use it

1. In KiCad PCB Editor, click **KiBridge: Open Workspace** whenever you want
   the AI to see the *current* state of the board. The plugin overwrites
   `snapshot/` with fresh data.
2. Open this folder in VS Code (`File -> Open Folder`).
3. Open Copilot (Chat / Edits / Agent).
4. Ask Copilot to review the snapshot. It already knows the rules
   because `.github/copilot-instructions.md` is preloaded into its
   context.
5. Copilot writes into `review/`:
   - `findings.md` — its human-readable review
   - `actions.json` — declarative action plan
   - `scripts/*.py` — Python scripts using the `kibridge_api` module
6. **You read what it wrote**, edit/delete anything you don't like.
7. Back in KiCad, click **KiBridge: Apply Workspace**.
   - The plugin validates everything, runs a dry-run, and shows you
     a preview dialog with every operation listed.
   - On confirm, it copies your `.kicad_pcb` into `backups/` and
     applies the changes.
   - A log is written to `apply_log/`.

## Folder layout

```
kibridge_workspace/
├── README.md                       this file
├── .github/copilot-instructions.md the contract Copilot follows
├── snapshot/                       (plugin -> Copilot, read-only for AI)
│   ├── meta.json
│   ├── board_inspect.json
│   ├── footprints.json
│   ├── tracks.json
│   └── design_rules.json
├── review/                         (Copilot -> plugin)
│   ├── findings.md
│   ├── actions.json
│   └── scripts/
├── apply_log/                      (plugin writes after each apply)
└── backups/                        (plugin copies .kicad_pcb before applying)
```

## Safety rules baked into the plugin

- The plugin **always** copies your `.kicad_pcb` into `backups/` before
  applying anything. If something goes wrong, rename the backup back.
- All scripts are AST-validated. Any script that imports anything other
  than `kibridge_api`, or uses `eval`, `exec`, `open`, dunder attributes, or
  similar escape vectors, is **refused without execution**.
- Any unknown `op` in `actions.json` causes the entire file to be
  refused — no partial application.
- Modifying ops require `"confirm_changes": true` at the top of
  `actions.json` AND a second confirmation dialog in KiCad.
