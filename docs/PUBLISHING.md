# KiBridge v1.0.6 — Publishing Playbook

Step-by-step to publish to GitHub and announce to the community. About 30-45 minutes of work.

## Step 1 — Create the GitHub repo (5 min)

1. Go to https://github.com/new
2. **Repository name:** `kibridge`
3. **Description:** `KiCad plugin + local web autorouter, bridged over localhost HTTP. Apache 2.0.`
4. **Public**
5. **Do NOT** initialize with README, .gitignore, or license — your zip has them already
6. Click **Create repository**

## Step 2 — Push the code (5 min)

Open a terminal in the folder where you unzipped `kibridge-1.0.6.zip`:

```bash
cd kibridge

# Initialize git
git init
git add .
git commit -m "Initial public release: KiBridge & KiRouter v1.0.6"

# Connect to GitHub (use your actual username)
git branch -M main
git remote add origin https://github.com/IgmarMelis/kibridge.git
git push -u origin main
```

If GitHub asks for credentials and you don't have a token set up:
1. Go to https://github.com/settings/tokens/new
2. Generate a "Personal access token (classic)" with `repo` scope
3. Use the token as the password when git prompts

## Step 3 — Verify CI is green (5 min)

After the push, GitHub Actions starts automatically. Watch it run:

```
https://github.com/IgmarMelis/kibridge/actions
```

You should see "CI" workflow with 10 green checkmarks within 1-2 minutes. If anything fails, fix before continuing. (None should — all 10 phases pass locally.)

## Step 4 — Create the v1.0.6 release (10 min)

1. Go to https://github.com/IgmarMelis/kibridge/releases/new
2. **Choose a tag:** type `v1.0.6` and click "Create new tag: v1.0.6 on publish"
3. **Release title:** `KiBridge & KiRouter v1.0.6`
4. **Description:** copy-paste the entire contents of [docs/RELEASE_NOTES_v1.0.6.md](RELEASE_NOTES_v1.0.6.md)
5. **Attach binaries:** drag-drop `kibridge-1.0.6.zip` so users can download it directly
6. **Set as the latest release** ✓ (checked by default)
7. Click **Publish release**

## Step 5 — Announce (15-20 min)

Three places where KiCad people hang out. Copy these templates, customize lightly.

### A) KiCad forum

Go to https://forum.kicad.info/ → Plugins → New Topic.

**Title:** `[Plugin] KiBridge & KiRouter — Freerouting bridge with AI-assisted review`

**Body:** see [`docs/announce_forum.md`](announce_forum.md)

### B) Reddit /r/PrintedCircuitBoard

Go to https://www.reddit.com/r/PrintedCircuitBoard/submit

**Title:** `I built a local browser-based autorouter for KiCad. Sends/receives over localhost, drives Freerouting. Open source.`

**Body:** see [`docs/announce_reddit.md`](announce_reddit.md)

### C) Hacker News (only if you want broader audience)

Go to https://news.ycombinator.com/submit

**Title:** `Show HN: KiBridge — local autorouter for KiCad with Copilot integration`

**Body:** Just the GitHub URL. HN doesn't need much else.

## Step 6 — Watch for feedback (ongoing)

Set up GitHub notifications:
1. https://github.com/IgmarMelis/kibridge → "Watch" button → "All Activity"
2. Reply to issues within 24h if possible — first impressions matter

Common things people will report:
- **macOS / Linux paths** — INSTALL.bat is Windows-only; people will ask for the equivalent on their OS
- **KiCad 9 compatibility** — the API is slightly different; if requests pile up, add a backport
- **Different footprints failing** — exotic pad shapes, hierarchical sheets, etc. Each is a small DSN exporter fix
- **Freerouting variants** — some people use older 1.x JARs; you may need to detect version and adjust

Treat each bug report as a v1.0.x patch: file, reproduce, test, fix, release. Don't refactor — keep shipping incremental fixes.

## After the launch

When you have ~5-10 user reports, you'll know what's worth working on. Likely candidates for v1.1:

- macOS / Linux first-class support (the code is portable, just needs INSTALL scripts)
- Multi-board projects (currently one .kicad_pcb at a time)
- Net-class-specific via sizes (DSN already supports it, just needs UI exposure)
- Place-then-route mode (move components and re-route in one operation)
- Demo gif in the README — a 20-second screen capture of the full workflow

Don't pre-build any of these. Wait for real user need.

— Good luck.
