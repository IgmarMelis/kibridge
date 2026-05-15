# `kibridge_api` reference

This is the complete API surface available to scripts under
`kibridge_workspace/review/scripts/`. Scripts may import **only** `kibridge_api`.

All coordinates are in **millimetres**. Layer names are strings
(e.g. `"F.SilkS"`, `"User.1"`). The runner injects the active board
and the dry_run flag — your script should not try to manage them.

## Read-only helpers

### `kibridge_api.list_nets() -> list[str]`
Returns every net name that has at least one pad on the board.

### `kibridge_api.find_net_code(net_name: str) -> int | None`
Resolves a net name to its KiCad netcode, or `None` if no pad is on
that net.

## Additive ops

### `add_silkscreen_note(text, x_mm, y_mm, layer="F.SilkS", size_mm=1.0) -> bool`
Adds a `PCB_TEXT` to `F.SilkS` or `B.SilkS`. Returns `True` on success.

### `add_fab_note(text, x_mm, y_mm, layer="F.Fab", size_mm=1.0) -> bool`
Adds a text note to `F.Fab` or `B.Fab`.

### `add_user_marker(x_mm, y_mm, radius_mm=1.5, note="") -> bool`
Adds a circle on `User.1` at (x,y) with optional text label below.
`User.1` is a designer-visible layer that is not exported to Gerbers
by default — safe for review markers.

### `highlight_net(net_name) -> bool`
Selects every track on the named net. Pure UI selection, zero board
modification, but is logged as an operation.

## Modifying ops

These require `"confirm_changes": true` at the top of `actions.json`,
and the plugin shows a second confirmation dialog before applying.

### `set_track_widths_for_net(net_name, width_mm) -> int`
Sets the width of every track (vias not affected) on the named net.
Returns the count of tracks affected.

### `add_stitching_via(x_mm, y_mm, net_name, width_mm=0.6, drill_mm=0.3) -> bool`
Adds a through-hole via at (x,y), F.Cu↔B.Cu, on the named net.
Useful for stitching ground pours.

## What `kibridge_api` is NOT

- It is not a wrapper around `pcbnew`. The function set is curated.
- It does NOT expose: deleting items, modifying pads, modifying
  footprints, modifying nets, modifying zones, saving the board, or
  any file I/O.
- The runner refuses any script that imports anything other than
  `kibridge_api`, so you cannot reach `pcbnew` "around" the API.

## Sandbox rules (script_runner.py)

The script is parsed with `ast` and rejected before execution if it:

- imports anything other than `kibridge_api`,
- accesses any dunder attribute (`x.__class__`, `x.__import__`, ...),
- calls any of:
  `eval`, `exec`, `compile`, `open`, `__import__`, `input`,
  `breakpoint`, `globals`, `locals`, `vars`, `getattr`, `setattr`,
  `delattr`, `hasattr`.

If the script passes the AST check, it is executed with a curated
`__builtins__` dict containing only safe names: `len`, `range`, `list`,
`dict`, `tuple`, `set`, `frozenset`, `str`, `int`, `float`, `bool`,
`True`, `False`, `None`, `print`, `isinstance`, `issubclass`, `abs`,
`min`, `max`, `round`, `sum`, `sorted`, `reversed`, `enumerate`, `zip`,
`map`, `filter`, `any`, `all`, plus a few exception classes.
