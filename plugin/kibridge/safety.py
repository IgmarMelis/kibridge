"""
safety - mandatory backup logic before any board modification.

The contract: NEVER call pcbnew.SaveBoard or any mutating op without
first calling backup_board(). If the backup fails, the apply must abort.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime


def backup_board(board_path: str, backups_dir: str) -> str:
    """
    Copy <board_path> into backups_dir with a timestamped suffix.
    Returns the full path of the backup file. Raises on failure.
    """
    if not board_path or not os.path.isfile(board_path):
        raise FileNotFoundError(f"Board file not found: {board_path}")

    os.makedirs(backups_dir, exist_ok=True)
    base = os.path.basename(board_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(backups_dir, f"{base}.kibridge_backup_{ts}")
    shutil.copy2(board_path, dst)
    if not os.path.isfile(dst) or os.path.getsize(dst) != os.path.getsize(board_path):
        raise IOError(f"Backup verification failed for {dst}")
    return dst
