"""Clean the echo loop's extra copies out of Moiragen's memory (run once).

Run from the project folder:
    .venv\\Scripts\\python.exe clean_echo.py            preview: shows what would go, changes nothing
    .venv\\Scripts\\python.exe clean_echo.py --apply    back up memory first, then clean it

Stop Moiragen first (close server.py / live.py), otherwise the running mind
would save its old memories over the cleaned files.

What is removed and why is explained in moiragen/cleanup.py. With --apply, a
report of every removal is saved next to the backup:
    memory/backups/<date>_<label>/cleanup_report.md
To undo, stop Moiragen and restore that backup (see moiragen/backup.py).
"""

import argparse
import json
import os
import socket
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from moiragen import config
from moiragen.backup import backup_memory
from moiragen.cleanup import LINES, clean_memory
from moiragen.echo import SENTENCE_MIN_WORDS, split_sentences, words

sys.stdout.reconfigure(encoding="utf-8")


def server_running() -> bool:
    """Is the viewer server (and so the mind) running right now?"""
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", 8765)) == 0


def save_json(path: Path, data) -> None:
    """Same format as Moiragen's own saves, written safely (temp file, then swap)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def short(text: str | None, n: int = 160) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


def other_repeats(events: list[dict], top: int = 8) -> list[tuple[int, str]]:
    """Other sentences (6+ words) the nanites said 3 or more times, counted in
    their replies in the life log. They are NOT removed; the report lists them."""
    counts, example = Counter(), {}
    for e in events:
        if e.get("kind") != "training_example" or e.get("who") == "Moiragen":
            continue
        for s in split_sentences(e.get("reply", "")):
            w = words(s)
            if len(w) >= SENTENCE_MIN_WORDS:
                key = " ".join(w)
                counts[key] += 1
                example.setdefault(key, s)
    return [(c, example[k]) for k, c in counts.most_common() if c >= 3][:top]


def build_report(report: dict, backup: Path | None, applied: bool) -> str:
    changes = report["changes"]
    lines = [f"# Echo clean-up report ({datetime.now():%Y-%m-%d %H:%M})", ""]
    lines.append(f"Status: {'APPLIED' if applied else 'PREVIEW ONLY (nothing changed)'}")
    if backup:
        lines.append(f"Backup of everything from before the clean-up: `{backup}`")
    lines += ["", "Repeated lines cleaned (the first time each was said is kept):"]
    lines += [f"- {name}: \"{text}\"" for name, text in LINES.items()]
    lines += ["", "A lesson that was nothing but a copied line is not deleted: it is replaced by "
              "the real \"I learned...\" sentence the nanite said in that same reflection."]

    per_place = {}
    for c in changes:
        p = per_place.setdefault(c["place"], Counter())
        p["copies"] += len(c["removed"])
        p[c["action"]] += 1
    lines += ["", "## Summary", "",
              "| Place | copies removed | entries deleted | entries trimmed | lessons put right |",
              "|---|---|---|---|---|"]
    for place, p in per_place.items():
        lines.append(f"| {place} | {p['copies']} | {p['deleted']} | {p['trimmed']} | {p['restored']} |")
    total = sum(len(c["removed"]) for c in changes)
    lines += ["", f"In total: {total} copies removed in {len(changes)} entries. "
              f"The life log's copies of the nanites' memories got the same "
              f"{report['mirrored']} changes as the memories themselves.",
              "Training examples: only the replies were cleaned; the prompts they were "
              "shown at the time are left exactly as they were."]

    lines += ["", "## Kept (the first copy in each place)", ""]
    for place, name, when, kind in report["kept"]:
        lines.append(f"- {place}: \"{name}\" line kept at {when} ({kind})")

    lines += ["", "## Every change", ""]
    for place in per_place:
        lines += [f"### {place}", ""]
        for c in (c for c in changes if c["place"] == place):
            cut = " + ".join(f"\"{short(r, 90)}\"" for r in c["removed"])
            if c["action"] == "deleted":
                lines.append(f"- {c['time']} [{c['kind']}] deleted (it held only copies): {short(c['before'])}")
            elif c["action"] == "restored":
                lines.append(f"- {c['time']} [{c['kind']}] was only a copy ({cut}); "
                             f"replaced by the real lesson from the same reflection:")
                lines.append(f"  - now: {short(c['after'])}")
            else:
                lines.append(f"- {c['time']} [{c['kind']}] cut {cut}")
                lines.append(f"  - now: {short(c['after'])}")
        lines.append("")

    others = other_repeats(report["events"])
    if others:
        lines += ["## Other lines that still repeat (left alone, as asked)", "",
                  "The nanites said these sentences 3 or more times (counted in their replies "
                  "in the life log). They were not removed; from now on the echo guard stops "
                  "new copies of them too.", ""]
        lines += [f"- {n}x \"{short(s, 120)}\"" for n, s in others]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Remove the echo loop's extra copies from memory.")
    ap.add_argument("--apply", action="store_true", help="back up memory, then clean it")
    args = ap.parse_args()

    if args.apply and server_running():
        sys.exit("Moiragen is running (port 8765 is in use). Stop server.py first, then try again.")

    mem = Path(config.MEMORY_DIR)
    nanite_paths = sorted((mem / "nanites").glob("*.json"))
    nanites = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in nanite_paths}
    moiragen_path = mem / "moiragen.json"
    moiragen = json.loads(moiragen_path.read_text(encoding="utf-8")) if moiragen_path.exists() else {}

    # Read the log, remembering each line exactly as written, so unchanged
    # events are written back byte for byte.
    log_path = mem / "log.jsonl"
    entries = []   # ("event", dict, raw line) or ("raw", None, raw line) for an unreadable line
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(("event", json.loads(raw), raw))
        except json.JSONDecodeError:
            entries.append(("raw", None, raw))
    events = [e for t, e, _ in entries if t == "event"]
    before = {id(e): json.dumps(e, ensure_ascii=False) for e in events}

    report = clean_memory(nanites, moiragen, events)

    backup = None
    if args.apply:
        backup = backup_memory("before-echo-cleanup")   # reuses an identical recent backup
        for p in nanite_paths:
            save_json(p, nanites[p.stem])
        if moiragen:
            save_json(moiragen_path, moiragen)
        keep = {id(e) for e in report["events"]}
        out = []
        for t, e, raw in entries:
            if t == "raw":
                out.append(raw)
            elif id(e) in keep:
                now = json.dumps(e, ensure_ascii=False)
                out.append(raw if now == before[id(e)] else now)
        tmp = log_path.with_suffix(".tmp")
        tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
        os.replace(tmp, log_path)

    text = build_report(report, backup, args.apply)
    if backup:
        (backup / "cleanup_report.md").write_text(text, encoding="utf-8")
        print(f"Cleaned. Report: {backup / 'cleanup_report.md'}\n")
    print(text)


if __name__ == "__main__":
    main()
