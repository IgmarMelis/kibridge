# Contributing to KiBridge & KiRouter

Thanks for your interest. This is an early-stage project and contributions
are very welcome — bug reports, ideas, code, docs, all of it.

## Quick guide

### Bug reports

Open an issue with:
- Your **OS** and **KiCad version**
- A short reproduction (what you did, what you expected, what happened)
- The traceback if there was one (KiBridge surfaces them in a dialog)
- The contents of `kibridge_workspace/apply_log/` if the bug is in apply

### Pull requests

1. Fork the repo and create a feature branch.
2. Keep PRs focused. One feature or one fix per PR.
3. Run the tests before submitting (see below).
4. Update `CHANGELOG.md` under "Unreleased".
5. Include a short description of *why* in the PR body, not just *what*.

### Running tests

The plugin has an end-to-end test that uses fake `pcbnew` and `wx` modules
(no real KiCad install needed):

```bash
python tests/test_kibridge_e2e.py
```

The AST sandbox tests verify the script validator refuses unsafe code:

```bash
python tests/test_sandbox.py
```

KiRouter (when present) has its own pytest suite under `router/tests/`.

## Coding standards

- **Python:** PEP 8, 4-space indent, type hints encouraged but not required.
- **Line length:** 88 (Black-compatible). Not strictly enforced.
- **No new dependencies in `plugin/kibridge/`** without strong justification.
  The plugin runs in KiCad's pcbnew Python — only the standard library
  and `wx` (which KiCad provides) are guaranteed.
- **KiRouter dependencies** go in `router/requirements.txt`.

## Project values

- **Safety first.** Every change to a `.kicad_pcb` is preceded by a backup
  and a preview dialog. No exceptions.
- **AI is the assistant, not the driver.** The plugin and router are
  deterministic. The user always confirms.
- **Local-only.** Designs never leave the user's machine. No telemetry,
  no analytics, no cloud calls.
- **Standalone.** Every component should run without the others — the
  plugin works without the router, the router works without Copilot.

## Code of conduct

Be respectful. PCB design is full of opinions; differences are fine,
contempt is not.

## License

By contributing, you agree that your contributions are licensed under
the [Apache License, Version 2.0](LICENSE).
