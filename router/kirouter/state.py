"""
Board state — in-memory holder for the current KiRouter session.

We deliberately keep this simple: one board at a time, no persistence,
no multi-user. KiRouter is a local single-user tool. If the server
restarts, the board state is lost; the user re-sends from KiBridge.

Thread-safe enough for Flask's threaded development server.
"""
from __future__ import annotations

import threading
import time
from typing import Any


class BoardState:
    def __init__(self):
        self._lock = threading.Lock()
        self._board: dict | None = None
        self._received_at: float | None = None
        self._source: str = "none"

    def set(self, board: dict, source: str = "api") -> None:
        with self._lock:
            # Defensive: if the incoming bbox doesn't actually cover every
            # pad/track/via, expand it. The plugin's bbox sometimes lags
            # the real component spread (in-progress boards w/o Edge.Cuts).
            board = self._fix_bbox(board)
            self._board = board
            self._received_at = time.time()
            self._source = source

    @staticmethod
    def _fix_bbox(board: dict) -> dict:
        """
        Ensure meta.board_bbox contains every footprint, pad, track,
        and via. If the supplied bbox is missing or too small, expand it.
        """
        meta = board.get("meta") or {}
        bb = meta.get("board_bbox") or {}

        xs: list[float] = []
        ys: list[float] = []
        if bb:
            for k in ("x_min", "x_max"):
                if k in bb: xs.append(float(bb[k]))
            for k in ("y_min", "y_max"):
                if k in bb: ys.append(float(bb[k]))

        for fp in board.get("footprints", []):
            try:
                xs.append(float(fp.get("x_mm", 0)))
                ys.append(float(fp.get("y_mm", 0)))
            except Exception:
                pass
            for pad in fp.get("pads", []):
                try:
                    xs.append(float(pad.get("x_mm", 0)))
                    ys.append(float(pad.get("y_mm", 0)))
                except Exception:
                    pass
        for t in board.get("tracks", []):
            for end in (t.get("start"), t.get("end")):
                if end:
                    try:
                        xs.append(float(end.get("x_mm", 0)))
                        ys.append(float(end.get("y_mm", 0)))
                    except Exception:
                        pass
        for v in board.get("vias", []):
            try:
                xs.append(float(v.get("x_mm", 0)))
                ys.append(float(v.get("y_mm", 0)))
            except Exception:
                pass

        if not xs:
            return board

        MARGIN = 10.0
        fixed = {
            "x_min": round(min(xs) - MARGIN, 3),
            "y_min": round(min(ys) - MARGIN, 3),
            "x_max": round(max(xs) + MARGIN, 3),
            "y_max": round(max(ys) + MARGIN, 3),
        }

        # Mutate only if needed
        if fixed != bb:
            new_meta = dict(meta)
            new_meta["board_bbox"] = fixed
            board = dict(board)
            board["meta"] = new_meta
        return board

    def get(self) -> dict | None:
        with self._lock:
            return self._board

    def info(self) -> dict[str, Any]:
        with self._lock:
            if self._board is None:
                return {
                    "loaded": False,
                    "received_at": None,
                    "source": self._source,
                }
            footprints = self._board.get("footprints", [])
            tracks = self._board.get("tracks", [])
            vias = self._board.get("vias", [])
            return {
                "loaded": True,
                "received_at": self._received_at,
                "source": self._source,
                "counts": {
                    "footprints": len(footprints),
                    "tracks":     len(tracks),
                    "vias":       len(vias),
                    "nets":       len(self._collect_nets()),
                },
                "meta": self._board.get("meta", {}),
            }

    def _collect_nets(self) -> set[str]:
        if self._board is None:
            return set()
        nets: set[str] = set()
        for t in self._board.get("tracks", []):
            n = t.get("net")
            if n:
                nets.add(n)
        for v in self._board.get("vias", []):
            n = v.get("net")
            if n:
                nets.add(n)
        for fp in self._board.get("footprints", []):
            for pad in fp.get("pads", []):
                n = pad.get("net")
                if n:
                    nets.add(n)
        return nets

    def clear(self) -> None:
        with self._lock:
            self._board = None
            self._received_at = None
            self._source = "none"


# Singleton for the running server
state = BoardState()
