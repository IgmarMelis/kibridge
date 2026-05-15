# Workflow

## The loop

```
   +---------------------------+         +-----------------------------+
   |                           |         |                             |
   |  KiCad PCB Editor         |         |  VS Code + GitHub Copilot   |
   |                           |         |                             |
   |  [KiBridge: Open Workspace]    |         |                             |
   |          |                |         |                             |
   |          | export         |         |                             |
   |          v                |         |                             |
   |  kibridge_workspace/snapshot/  |---------|--> read by Copilot          |
   |                           |         |                             |
   |                           |         |  Copilot writes:            |
   |  kibridge_workspace/review/    |<--------|--   findings.md             |
   |                           |         |     actions.json            |
   |                           |         |     scripts/*.py            |
   |          ^                |         |                             |
   |          | read           |         |                             |
   |          |                |         |                             |
   |  [KiBridge: Apply Workspace]   |         |                             |
   |   - validate              |         |                             |
   |   - dry-run + preview     |         |                             |
   |   - confirm dialog        |         |                             |
   |   - backup .kicad_pcb     |         |                             |
   |   - apply                 |         |                             |
   |   - save board            |         |                             |
   |   - write apply_log       |         |                             |
   |                           |         |                             |
   +---------------------------+         +-----------------------------+
```

## Step-by-step

### 1. Open Workspace (in KiCad)

The plugin:
- creates `kibridge_workspace/` next to the board (idempotent),
- writes `snapshot/` with 5 fresh JSON files,
- on FIRST run, copies the template files (`.github/copilot-instructions.md`,
  `README.md`, empty `findings.md` and `actions.json`),
- offers to open the folder.

Subsequent clicks ONLY refresh `snapshot/`. They never touch the
contents of `review/` — that is your space (and Copilot's).

### 2. Open in VS Code

Open `kibridge_workspace/` itself (not the parent project folder). Copilot
in VS Code reads `.github/copilot-instructions.md` automatically and
treats it as your workspace's standing instructions.

### 3. Ask Copilot

Sample prompts that work well:

> "Read snapshot/board_inspect.json and write findings.md, then
> propose concrete fixes in actions.json."

> "The 5V net is currently 0.2mm. Generate a script under
> review/scripts/ that widens it to 0.6mm."

> "Are there any signals routed under the MAX485 transceiver that
> should be relocated? Use tracks.json and footprints.json to check."

Copilot writes only into `review/`. The plugin will refuse anything
that ended up outside this folder.

### 4. Review what Copilot wrote

Open `review/findings.md`, `review/actions.json`, and any scripts.
Edit, delete, or trim freely. Whatever ends up saved is what gets
considered.

### 5. Apply

Click **KiBridge: Apply Workspace** in KiCad. Read the preview dialog
carefully:

- Every operation is listed.
- `[actions.json]` vs `[script_name.py]` tells you where each
  operation came from.
- Modifying ops trigger a second confirm dialog before execution.

### 6. Verify

- The PCB Editor view refreshes after apply.
- Inspect `kibridge_workspace/apply_log/<timestamp>_apply.json` to see what
  ran.
- If something is wrong, the original `.kicad_pcb` is sitting in
  `kibridge_workspace/backups/` with a timestamp.

## Restoring from a backup

```
1. Close the .kicad_pcb in KiCad.
2. Delete (or rename) the modified .kicad_pcb in your project folder.
3. Copy kibridge_workspace/backups/<your_board>.kicad_pcb.kibridge_backup_<ts>
   back to your project folder and rename it to <your_board>.kicad_pcb.
4. Re-open in KiCad.
```

## Tips

- Click **Open Workspace** any time the board changes meaningfully.
  Copilot should always work from a fresh snapshot.
- Keep `kibridge_workspace/` in your project's git repo. The history of
  reviews and apply logs is genuinely useful.
- Add `kibridge_workspace/backups/` to `.gitignore` if you don't want
  committed backups.
