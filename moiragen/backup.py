"""Backups of Moiragen's memory folder.

Before anything rewrites memory (like the echo clean-up), copy the whole
memory folder into memory/backups/<date>_<label>/ and check that every file
arrived intact. The backups live inside memory/, so, like the rest of memory,
they stay on this computer and are never pushed to Git.

To undo a change, stop Moiragen and call restore_memory(<backup folder>).
"""

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from . import config

BACKUP_DIR_NAME = "backups"
MANIFEST = "manifest.json"   # list of files + checksums, written into each backup


def _files(root: Path) -> list[Path]:
    """Every file in a memory folder, except the backups themselves and
    half-written temporary files."""
    found = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if not p.is_file() or rel.parts[0] == BACKUP_DIR_NAME:
            continue
        if p.suffix == ".tmp" or rel.as_posix() == MANIFEST:
            continue
        found.append(p)
    return sorted(found)


def _sha256(path: Path) -> str:
    """A fingerprint of the file's bytes: two files with the same fingerprint are identical."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(root: Path) -> dict[str, str]:
    """{relative path: fingerprint} for every file in the folder."""
    return {p.relative_to(root).as_posix(): _sha256(p) for p in _files(root)}


def backup_memory(label: str = "backup") -> Path:
    """Copy the memory folder into memory/backups/ and verify the copy.

    If nothing has changed since the newest backup, that backup is reused
    instead of making an identical second copy. Returns the backup folder.
    """
    root = Path(config.MEMORY_DIR)
    backups = root / BACKUP_DIR_NAME
    current = manifest(root)

    newest = sorted(backups.glob(f"*/{MANIFEST}"))  # names start with the date, so this is oldest -> newest
    if newest and json.loads(newest[-1].read_text(encoding="utf-8")) == current:
        return newest[-1].parent

    target = backups / f"{datetime.now():%Y-%m-%d_%H%M%S}_{label}"
    for rel in current:
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dest)

    # Check every file arrived byte-for-byte before trusting the backup.
    if manifest(target) != current:
        raise RuntimeError(f"Backup check failed: {target} does not match the memory folder.")
    (target / MANIFEST).write_text(json.dumps(current, indent=1), encoding="utf-8")
    return target


def restore_memory(backup: Path) -> None:
    """Put a backup's files back into the memory folder (stop Moiragen first).

    Files are copied over the current ones; files that did not exist when the
    backup was made are left alone.
    """
    backup = Path(backup)
    saved = json.loads((backup / MANIFEST).read_text(encoding="utf-8"))
    root = Path(config.MEMORY_DIR)
    for rel in saved:
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup / rel, dest)
