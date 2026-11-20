"""Run every step's check, one after another, and report which passed.

Each check uses its own throwaway memory folder (except step 1, which only
writes one small "test" line to the real log). Needs Ollama running.
Takes roughly 15-25 minutes, because the minds really think.

Run from the project folder:
    .venv\\Scripts\\python.exe tests\\run_all.py
"""

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
checks = sorted(HERE.glob("step*_check.py"), key=lambda p: int(p.stem[4:].split("_")[0]))

results = []
for check in checks:
    print(f"\n=== {check.name} ===", flush=True)
    start = time.time()
    code = subprocess.call([sys.executable, str(check)], cwd=HERE.parent)
    results.append((check.name, code == 0, time.time() - start))

print("\n=== Summary ===")
for name, ok, secs in results:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}  ({secs:.0f}s)")
failed = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed.")
sys.exit(1 if failed else 0)
