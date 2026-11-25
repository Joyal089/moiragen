"""Copy everything Moiragen needs to the "Moiragen" folder in Google Drive.

Memory backups are copied by themselves after every backup. Run this after pushing new
code, so that Drive has the same code as GitHub. It never deletes anything.

Run from the project folder:
    .venv\\Scripts\\python.exe to_drive.py            code, guide, backups, exports
    .venv\\Scripts\\python.exe to_drive.py --backup   make a memory backup first (stop Moiragen first)
    .venv\\Scripts\\python.exe to_drive.py --model    the model files too (3.4 GB, needed once)
"""

import argparse
import os
import sys
from pathlib import Path

from moiragen import config, drive
from moiragen.backup import backup_memory

sys.stdout.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--backup", action="store_true", help="make a memory backup first")
parser.add_argument("--model", action="store_true", help="copy the model files too")
args = parser.parse_args()

folder = drive.drive_folder()
if folder is None:
    sys.exit("Google Drive is not set up or not running (DRIVE_DIR in .env).")

if args.backup:
    print(f"Backup: {backup_memory('backup')}")
for name in drive.copy_backups(folder):
    print(f"Backup copied: {name}")
for name in drive.copy_training(folder):
    print(f"Export copied: {name}")

changed, commit = drive.copy_code(folder)
(folder / "Code version.txt").write_text(f"Code/ is the same as Git commit {commit}\n", encoding="utf-8")
drive.copy_file(config.PROJECT_DIR / "NEW_MACHINE.md", folder / "README.md")
print(f"Code: {changed} files changed, now at commit {commit[:7]}")

if args.model:
    models = Path(os.getenv("OLLAMA_MODELS") or Path.home() / ".ollama" / "models")
    copied = drive.copy_model(folder, models, config.OLLAMA_MODEL)
    print(f"Model: {len(copied)} files copied")
print(f"Done. Nothing was deleted. Drive folder: {folder}")
