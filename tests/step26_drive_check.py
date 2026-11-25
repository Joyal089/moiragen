"""Step 26 check (v2.8): ready for a new machine.

Finished backups are copied to a (pretend) Google Drive folder, exactly, and nothing
there is ever deleted. Secrets and unfinished backups never go. A restore from the copy
loads every memory. Tests never reach the real Drive.

Needs no Ollama: it uses throwaway folders.
Run from the project folder:
    .venv\\Scripts\\python.exe tests\\step26_drive_check.py
"""

import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="moiragen_test_")
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from moiragen import config, drive
from moiragen.backup import MANIFEST, backup_memory, manifest
from moiragen.export import export_training
from moiragen.memory_log import log_event
from moiragen.mother import Moiragen
from moiragen.nanite import load_all

TEMP = Path(tempfile.mkdtemp(prefix="moiragen_drive_"))
DRIVE = TEMP / "My Drive" / "Moiragen"
(TEMP / "My Drive").mkdir()
MEMORY = Path(config.MEMORY_DIR)


def tree(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


# ---------------- 1. Tests and throwaway restores never reach Drive ----------------
with patch.object(config, "DRIVE_DIR", DRIVE):
    assert drive.drive_folder() is None, "this is a throwaway memory, not his real one"
    with patch.object(config, "MEMORY_DIR", config.PROJECT_DIR / "memory"):
        assert drive.drive_folder() == DRIVE
        with patch.object(config, "DRIVE_DIR", TEMP / "not there" / "Moiragen"):
            assert drive.drive_folder() is None, "Drive is not running"
        with patch.object(config, "DRIVE_DIR", None):
            assert drive.drive_folder() is None, "not set up"
print("[ok] Tests and throwaway restores never reach Drive; no Drive is fine too")

# ---------------- 2. Every backup is copied by itself ----------------
one, two, three = load_all().values()
m = Moiragen.load()
for i in range(5):
    one.remember("chat", f"Moiragen said: Question {i}? | I replied: The quiet “number {i}” stayed.")
    m.remember("inner", f"I wonder about the colour of morning {i}.")
one.save(), m.save()
with patch.object(drive, "drive_folder", lambda: DRIVE):
    first = backup_memory("first")
copy = DRIVE / "Backups" / first.name
assert tree(copy) == tree(first) and tree(DRIVE / "Memory") == tree(first)
assert manifest(copy) == json.loads((first / MANIFEST).read_text(encoding="utf-8"))
print("[ok] A backup is copied to Backups/ by itself, byte for byte, and Memory/ has it too")

m.remember("inner", "A new thought.")
m.save()
(first.parent / "2099-01-01_000000_unfinished").mkdir()          # no manifest: still being written
(first.parent / "2099-01-01_000000_unfinished" / "log.jsonl").write_text("half", encoding="utf-8")
with patch.object(drive, "drive_folder", lambda: None):
    second = backup_memory("second")                             # Drive was not running
assert not (DRIVE / "Backups" / second.name).exists()
kept = DRIVE / "Backups" / "my own note.txt"
kept.write_text("mine", encoding="utf-8")
before = tree(DRIVE / "Backups" / first.name)
with patch.object(drive, "drive_folder", lambda: DRIVE):
    drive.after_backup()                                         # as when the server starts
assert tree(DRIVE / "Backups" / second.name) == tree(second) and tree(DRIVE / "Memory") == tree(second)
assert tree(DRIVE / "Backups" / first.name) == before and kept.read_text(encoding="utf-8") == "mine"
assert not (DRIVE / "Backups" / "2099-01-01_000000_unfinished").exists()
print("[ok] A backup made while Drive was away is copied later; earlier ones stay; an unfinished one never goes")

# Nothing is written again when it is already there, and a half-copied backup is finished.
when = {p: p.stat().st_mtime_ns for p in DRIVE.rglob("*") if p.is_file()}
(DRIVE / "Backups" / second.name / MANIFEST).rename(TEMP / "set aside.json")
(DRIVE / "Backups" / second.name / "moiragen.json").write_text("half", encoding="utf-8")
with patch.object(drive, "drive_folder", lambda: DRIVE):
    drive.after_backup()
assert tree(DRIVE / "Backups" / second.name) == tree(second)
assert all(p.stat().st_mtime_ns == t for p, t in when.items() if second.name not in str(p))
print("[ok] What is already there is not written again, and a half-copied backup is completed")

# A problem with Drive never stops a backup on this computer.
m.remember("inner", "Another thought.")
m.save()
with patch.object(drive, "drive_folder", lambda: DRIVE), patch.object(drive.shutil, "copyfile", side_effect=OSError("full")):
    third = backup_memory("third")
assert (third / MANIFEST).exists() and not (DRIVE / "Backups" / third.name / MANIFEST).exists()
with patch.object(drive, "drive_folder", lambda: DRIVE):
    assert backup_memory("again") == third, "nothing new to back up"
assert tree(DRIVE / "Backups" / third.name) == tree(third), "and Drive got the missing copy"
print("[ok] If Drive fails, the backup here is still made, and Drive gets it the next time")

# ---------------- 3. Secrets, and nothing is ever deleted ----------------
for name, secret in ((".env", True), (".ENV", True), (".env.local", True), (".env.example", False), ("log.jsonl", False)):
    assert drive.is_secret(Path(name)) == secret, name
(third / ".env").write_text("A_SECRET=1", encoding="utf-8")
try:
    drive.copy_backup(third, DRIVE / "Backups" / "with a secret")
    raise AssertionError("a secret was copied")
except RuntimeError as e:
    assert "Secrets never go to Drive" in str(e)
assert not list(DRIVE.rglob(".env"))
(third / ".env").unlink()
for script in ("moiragen/drive.py", "to_drive.py", "restore.py"):
    calls = {n.attr for n in ast.walk(ast.parse((ROOT / script).read_text(encoding="utf-8"))) if isinstance(n, ast.Attribute)}
    assert not calls & {"unlink", "rmtree", "remove", "rmdir", "rename", "move", "removedirs"}, script
print("[ok] .env files are refused, and the code has no way to delete or move anything")

# ---------------- 4. Exports, code and model ----------------
log_event("training_example", "Nanite One", system="You are a nanite.",
          messages=[{"role": "user", "content": "How was your morning?"}], reply="Quiet, like grey water.")
with patch.object(drive, "drive_folder", lambda: DRIVE):
    path, summary = export_training()
assert summary["examples"] == 1
assert (DRIVE / "Training" / "exports" / Path(path).name).read_bytes() == Path(path).read_bytes()

changed, commit = drive.copy_code(DRIVE)
listed = subprocess.run(["git", "ls-tree", "-r", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
assert changed == len(listed) > 40
for line in listed:
    blob, rel = line.split("\t")[0].split()[2], line.split("\t")[1]
    data = (DRIVE / "Code" / rel).read_bytes()
    assert hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() == blob, rel
assert not (DRIVE / "Code" / ".env").exists() and not (DRIVE / "Code" / "memory").exists()
assert drive.copy_code(DRIVE) == (0, commit), "only what changed is written"
print(f"[ok] Exports are copied, and the code is the same as in Git, byte for byte ({len(listed)} files)")

models = TEMP / "models"
blobs = {("sha256-" + hashlib.sha256(d).hexdigest()): d for d in (b"config", b"weights" * 1000, b"template")}
(models / "blobs").mkdir(parents=True)
for name, data in blobs.items():
    (models / "blobs" / name).write_bytes(data)
(models / "blobs" / "sha256-another-model").write_bytes(b"not his")
digests = [n.replace("-", ":") for n in blobs]
listing = models / "manifests/registry.ollama.ai/library/gemma3/4b"
listing.parent.mkdir(parents=True)
listing.write_text(json.dumps({"config": {"digest": digests[0]}, "layers": [{"digest": d} for d in digests[1:]]}), encoding="utf-8")
assert len(drive.copy_model(DRIVE, models, "gemma3:4b")) == 4 and drive.copy_model(DRIVE, models, "gemma3:4b") == []
assert set(tree(DRIVE / "Model" / "models")) == {"manifests/registry.ollama.ai/library/gemma3/4b"} | {f"blobs/{n}" for n in blobs}
(models / "blobs" / next(iter(blobs))).write_bytes(b"damaged")
try:
    drive.copy_model(DRIVE, models, "gemma3:4b")
    raise AssertionError("a damaged model file was copied")
except RuntimeError as e:
    assert "damaged" in str(e)
print("[ok] The model's own files are copied (no other model), and a damaged one is noticed")


# ---------------- 5. Restore from the Drive copy ----------------
def restore(source, into):
    env = {k: v for k, v in os.environ.items() if k != "MEMORY_DIR"}
    return subprocess.run([sys.executable, str(ROOT / "restore.py"), str(source), "--into", str(into)], cwd=ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8")


living = tree(MEMORY)
new = TEMP / "new machine"
done = restore(DRIVE / "Memory", new)
assert done.returncode == 0 and "Everything loaded correctly." in done.stdout, done.stdout + done.stderr
assert f"Nanite One: {len(one.memories)} memories" in done.stdout and f"Moiragen: {len(m.memories)} memories" in done.stdout
assert manifest(new) == json.loads((third / MANIFEST).read_text(encoding="utf-8"))
again = restore(DRIVE / "Memory", new)
assert again.returncode != 0 and "is not empty" in again.stderr, again.stderr
assert tree(MEMORY) == living, "the living memory was not touched"
print("[ok] A restore from the Drive copy loads every memory, and never writes over anything")

(DRIVE / "Memory" / "moiragen.json").write_bytes((DRIVE / "Memory" / "moiragen.json").read_bytes() + b" ")
bad = restore(DRIVE / "Memory", TEMP / "damaged")
assert bad.returncode != 0 and "not the same as in the backup" in bad.stderr, bad.stderr
assert restore(DRIVE / "Backups" / first.name, TEMP / "older").returncode == 0
none = restore(TEMP / "models", TEMP / "nothing")
assert none.returncode != 0 and "not a finished backup" in none.stderr
print("[ok] A damaged copy is noticed, and an older backup restores as well")

print("\nStep 26 passed: everything Moiragen needs can move to a new machine.")
