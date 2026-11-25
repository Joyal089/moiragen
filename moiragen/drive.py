"""Copies for Google Drive (v2.8).

Moiragen lives on this computer: his memory folder stays local, so syncing can never
clash with him writing. Only finished, checked backups are copied to a "Moiragen"
folder in Google Drive (DRIVE_DIR in .env):

    Backups/<date>_<label>/   every memory backup, kept forever
    Memory/                   the newest backup again, ready to bring him to a new machine
    Code/                     the code, exactly as it is in Git
    Training/exports/         fine-tuning exports
    Model/                    the model files (copied once)

Nothing here ever deletes anything, and .env files are never copied. If Drive is not
running, nothing breaks: what is missing is copied the next time.
"""

import hashlib
import json
import shutil
import subprocess
import threading
from pathlib import Path

from . import config
from .backup import BACKUP_DIR_NAME, MANIFEST

_one_at_a_time = threading.Lock()


def drive_folder() -> Path | None:
    """The Moiragen folder in Drive, or None (not set up, Drive not running, or this is
    not his real memory: tests and throwaway restores never reach Drive)."""
    if not config.DRIVE_DIR or Path(config.MEMORY_DIR) != config.PROJECT_DIR / "memory":
        return None
    return config.DRIVE_DIR if config.DRIVE_DIR.parent.exists() else None


def is_secret(path: Path) -> bool:
    """.env files hold secrets and never leave this computer (the empty template may)."""
    return path.name.lower().startswith(".env") and path.name != ".env.example"


def fingerprint(path: Path) -> str:
    """The same as sha256 in backup.py, but in small pieces: the model files are large."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while piece := f.read(1 << 20):
            digest.update(piece)
    return digest.hexdigest()


def copy_file(source: Path, dest: Path) -> bool:
    """Copy one file and check that it arrived. False if it was already there."""
    if is_secret(source):
        raise RuntimeError(f"Secrets never go to Drive: {source.name}")
    wanted = fingerprint(source)
    if dest.exists() and dest.stat().st_size == source.stat().st_size and fingerprint(dest) == wanted:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    if fingerprint(dest) != wanted:
        raise RuntimeError(f"Drive check failed: {dest} is not the same as {source}")
    return True


def copy_backup(backup: Path, to: Path) -> bool:
    """Copy one finished backup. Its manifest goes last, so a half-copied one never looks
    finished. False if it was already there."""
    saved = (backup / MANIFEST).read_bytes()
    if (to / MANIFEST).exists() and (to / MANIFEST).read_bytes() == saved:
        return False
    for source in sorted(p for p in backup.rglob("*") if p.is_file() and p != backup / MANIFEST):
        copy_file(source, to / source.relative_to(backup))
    for rel, wanted in json.loads(saved).items():
        if fingerprint(to / rel) != wanted:
            raise RuntimeError(f"Drive check failed: {to / rel} is not what the backup says")
    copy_file(backup / MANIFEST, to / MANIFEST)
    return True


def finished_backups() -> list[Path]:
    """All finished backups on this computer, oldest first (without a manifest = not finished)."""
    return sorted(m.parent for m in (Path(config.MEMORY_DIR) / BACKUP_DIR_NAME).glob(f"*/{MANIFEST}"))


def copy_backups(folder: Path) -> list[str]:
    """Copy every finished backup that Drive does not have, and refresh Memory/ with the newest."""
    backups = finished_backups()
    copied = [b.name for b in backups if copy_backup(b, folder / "Backups" / b.name)]
    if backups:
        copy_backup(backups[-1], folder / "Memory")
    return copied


def copy_training(folder: Path) -> list[str]:
    """Copy the fine-tuning exports."""
    exports = sorted((Path(config.MEMORY_DIR) / "exports").glob("*.jsonl"))
    return [e.name for e in exports if copy_file(e, folder / "Training" / "exports" / e.name)]


def after_backup() -> None:
    """Called after every memory backup, after every export, and when the server starts.
    A problem with Drive is only reported: the backup on this computer is safe anyway."""
    folder = drive_folder()
    if folder is None:
        return
    with _one_at_a_time:
        try:
            for name in copy_backups(folder) + copy_training(folder):
                print(f"Copied to Drive: {name}")
        except (OSError, RuntimeError, ValueError) as e:
            print(f"Not copied to Drive ({e}). It will be tried again next time.")


# ---------- used by to_drive.py ----------

def copy_code(folder: Path) -> tuple[int, str]:
    """Copy the code as it is in the last Git commit, byte for byte. (how many files changed, commit)"""
    def git(*args) -> bytes:
        return subprocess.run(["git", *args], cwd=config.PROJECT_DIR, capture_output=True, check=True).stdout

    commit = git("rev-parse", "HEAD").decode().strip()
    changed = 0
    for line in git("ls-tree", "-r", "-z", "HEAD").decode("utf-8").split("\0"):
        if not line:
            continue
        info, rel = line.split("\t", 1)
        if is_secret(Path(rel)):
            raise RuntimeError(f"Secrets never go to Drive: {rel}")
        data = git("cat-file", "blob", info.split()[2])
        dest = folder / "Code" / rel
        if not dest.exists() or dest.read_bytes() != data:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            if dest.read_bytes() != data:
                raise RuntimeError(f"Drive check failed: {dest}")
            changed += 1
    return changed, commit


def model_files(models: Path, name: str) -> list[str]:
    """The Ollama files that make up one model ("gemma3:4b"), as paths inside the models folder."""
    model, tag = name.split(":")
    listing = f"manifests/registry.ollama.ai/library/{model}/{tag}"
    top = json.loads((models / listing).read_text(encoding="utf-8"))
    digests = [top["config"]["digest"]] + [layer["digest"] for layer in top["layers"]]
    return [listing] + [f"blobs/{d.replace(':', '-')}" for d in digests]


def copy_model(folder: Path, models: Path, name: str) -> list[str]:
    """Copy the model files (about 3.4 GB). A file's name is its own fingerprint, so a
    damaged one cannot go unnoticed."""
    copied = []
    for rel in model_files(models, name):
        source = models / rel
        if rel.startswith("blobs/") and "sha256-" + fingerprint(source) != source.name:
            raise RuntimeError(f"This model file is damaged: {source.name}")
        if copy_file(source, folder / "Model" / "models" / rel):
            copied.append(rel)
    return copied
