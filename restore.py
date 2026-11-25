"""Bring Moiragen's memory back from a backup, and check that he is all there.

It only writes into an empty folder, so it can never overwrite a living memory.

Run from the project folder (stop Moiragen first):
    .venv\\Scripts\\python.exe restore.py "G:\\My Drive\\Moiragen\\Memory"
        into this project's own memory folder (a new machine)
    .venv\\Scripts\\python.exe restore.py "G:\\My Drive\\Moiragen\\Memory" --into C:\\Temp\\try
        into another empty folder, only to check the backup
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("backup", help="the backup folder (it has a manifest.json)")
parser.add_argument("--into", help="an empty folder (default: this project's memory folder)")
args = parser.parse_args()

if args.into:
    os.environ["MEMORY_DIR"] = str(Path(args.into).resolve())     # before the settings are read

from moiragen import config
from moiragen.backup import MANIFEST, manifest, restore_memory

backup = Path(args.backup)
if not (backup / MANIFEST).exists():
    sys.exit(f"{backup} is not a finished backup (no {MANIFEST}).")
if any(config.MEMORY_DIR.iterdir()):
    sys.exit(f"{config.MEMORY_DIR} is not empty. Nothing was changed.")

# 1. Copy, and compare every file's fingerprint with the backup's list.
restore_memory(backup)
saved = json.loads((backup / MANIFEST).read_text(encoding="utf-8"))
if manifest(config.MEMORY_DIR) != saved:
    sys.exit("Some files are not the same as in the backup. Try again, or use an older backup.")
print(f"{len(saved)} files restored into {config.MEMORY_DIR}, every one the same as in the backup")

# 2. Wake each mind from its file, and compare its memories with what the file says.
from moiragen.memory_log import read_events
from moiragen.mother import MOIRAGEN_FILE, Moiragen
from moiragen.nanite import Nanite

minds = [("Moiragen", MOIRAGEN_FILE, Moiragen.load())]
for path in sorted((config.MEMORY_DIR / "nanites").glob("nanite_*.json")):
    n = Nanite.load(path.stem)
    minds.append((n.name, path, n))
for name, path, mind in minds:
    if mind.memories != json.loads(path.read_text(encoding="utf-8"))["memories"]:
        sys.exit(f"{name}'s memories did not load correctly.")
    print(f"{name}: {len(mind.memories)} memories since {mind.memories[0]['time'][:10] if mind.memories else 'birth'}, "
          f"health {mind.health:.0f}")
print(f"Life log: {len(read_events(last=10**9))} events")
if manifest(config.MEMORY_DIR) != saved:
    sys.exit("Loading changed a file, so this was not a clean restore.")
print("Everything loaded correctly.")
