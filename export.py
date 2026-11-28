"""Export Moiragen's life log as fine-tuning data (saved in memory/exports/).

Copies, and anything made-up, corrected or pretend play, are always left out
(see moiragen/training_rules.py).

Run from the project folder:
    .venv\\Scripts\\python.exe export.py                    everything
    .venv\\Scripts\\python.exe export.py --since 2026-11-21 only from that day on
    .venv\\Scripts\\python.exe export.py --skip-wrong       leave out decisions you marked wrong
    .venv\\Scripts\\python.exe export.py --skip-rounds      leave out everything said in Turn Rounds
    .venv\\Scripts\\python.exe export.py --skip-lessons     leave out the questions and answers after lessons
"""

import argparse
import json
import sys

from moiragen.export import export_training

sys.stdout.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--since", help="only examples on or after this date (YYYY-MM-DD)")
parser.add_argument("--skip-wrong", action="store_true", help="leave out decisions you marked wrong")
parser.add_argument("--skip-rounds", action="store_true", help="leave out everything said in Turn Rounds")
parser.add_argument("--skip-lessons", action="store_true", help="leave out the questions and answers after lessons")
args = parser.parse_args()

path, summary = export_training(args.since, args.skip_wrong, args.skip_rounds, args.skip_lessons)
print(f"Saved {summary['examples']} examples to {path}\n")
print(json.dumps(summary, indent=2, ensure_ascii=False))
