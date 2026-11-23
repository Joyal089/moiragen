"""The inner-life journal: memory/inner_life_journal.md

A readable diary of everything that happens inside Moiragen: his thoughts,
reflections, stories, the nanites' talks and lessons, every question with
each nanite's answer, his choice and reasons, verdicts, corrections and sleep.

It is written from the life log (memory/log.jsonl), never from the live
minds, so it cannot change anything. It only ever appends.

It keeps a bookmark (memory/journal_state.json): how far into the life log
it has written. Every time Moiragen starts, it first catches up on anything
written while it was not running (a restart, a crash, a one-off script),
then follows the log as it grows. So nothing is skipped and nothing is
written twice. Feelings, energy numbers and body readings are left out
(they would drown the story); they are all still in the life log.

Like all of memory, the journal stays on this computer and is never pushed.
"""

import json
import threading
import time
from datetime import datetime

from . import memory_log
from .config import MEMORY_DIR

JOURNAL_FILE = MEMORY_DIR / "inner_life_journal.md"
STATE_FILE = MEMORY_DIR / "journal_state.json"
FOLLOW_SECONDS = 1.0        # how often it looks for new lines in the life log

LABELS = {
    "social_talk": "talks to", "social_help": "helps", "social_support": "comforts",
    "social_ask_why": "asks", "social_explain": "explains to", "social_lesson": "learned",
    "social_disagree": "DISAGREES with", "social_reconsider": "RECONSIDERS, to",
}


def clean(text) -> str:
    """One line, no extra spaces."""
    return " ".join(str(text or "").split())


def render(e: dict) -> str | None:
    """One life-log event -> markdown for the journal (None = leave it out)."""
    k, who, at = e.get("kind", ""), e.get("who", ""), e.get("time", "")[11:19]
    if k in LABELS:
        if k == "social_lesson":
            return f"- {at} **{e.get('from')}** learned: {clean(e.get('text'))}"
        extra = ""
        if k == "social_reconsider":
            extra = f" [{'changed his choice to ' + str(e.get('chosen')) if e.get('changed') else 'kept his choice'}]"
        return f"- {at} **{e.get('from')}** {LABELS[k]} {e.get('to')}{extra}: {clean(e.get('text'))}"
    if k == "inner" and who == "Moiragen":
        return f"- {at} *Moiragen thinks:* {clean(e.get('text'))}"
    if k == "reflection" and who == "Moiragen":
        about = f" — About me: {clean(e.get('about_me'))}" if e.get("about_me") else ""
        return f"- {at} *Moiragen reflects:* {clean(e.get('text'))}{about}"
    if k == "surprise":
        return f"- {at} *Surprise:* {clean(e.get('text'))}"
    if k == "story":
        return f"\n#### {at} Moiragen's story\n\n{e.get('text', '')}\n"
    if k == "decision_full":
        return _render_decision(e, at)
    # (a "pattern" event is written inside its decision above, after the names are revealed)
    if k == "choice_changed":
        return f"- {at} **Moiragen changed his choice** to {e.get('chosen')}: {clean(e.get('why'))}"
    if k in ("feedback", "mistake") and who == "Moiragen":
        return f"- {at} **Verdict:** {clean(e.get('text'))}"
    if k == "fairer_words":
        done = (f"he rewrote it: \"{clean(e.get('rewrite'))}\"" if e.get("outcome") == "rewritten"
                else f"his rewrite was still dismissive (\"{clean(e.get('rewrite'))}\"), so that sentence "
                     f"was removed. What {e.get('to')} heard: \"{clean(e.get('final'))}\"")
        return (f"- {at} **Fairer words:** Moiragen was about to tell {e.get('to')} \"{clean(e.get('original'))}\". "
                f"Gentle note on \"{e.get('phrase')}\": this dismisses a way of seeing. Then {done}")
    if k == "correction":
        return f"- {at} **Correction ({who}):** {clean(e.get('text'))}"
    if k == "lesson" and not str(e.get("source", "")).startswith("decision"):
        # Lessons after a decision are already written as "learned" above.
        return f"- {at} **{who}** learned: {clean(e.get('text'))}"
    if k == "chat" and e.get("from_who") == "user":
        return f"- {at} **{who}** (direct chat): {clean(e.get('text'))}"
    if k == "echo_rejected":
        return f"- {at} _(echo guard: {who} repeated a recent line and was asked for something new)_"
    if k == "echo_quiet":
        return f"- {at} _(echo guard: {who} had nothing new to say, so stayed quiet)_"
    if k in ("presence", "slept", "awake_note") and who == "mind":   # (each one's own sleep note is summed up here)
        return f"- {at} _{clean(e.get('text'))}_"
    return None


def _render_decision(e: dict, at: str) -> str:
    """A question: each nanite's answer, Moiragen's note to it, his choice and answer."""
    situation = " (a situation: judged by the reasoning)" if e.get("situational") else ""
    lines = [f"\n### {at} Question: \"{clean(e.get('question'))}\"{situation}\n"]
    for s in e.get("suggestions", []):
        v = (e.get("verdicts") or {}).get(s["nanite"], {})
        star = " (chosen)" if s["nanite"] == e.get("chosen") else ""
        lines.append(f"- **{s['nanite']}**{star}: {clean(s['text'])}")
        if v.get("why"):
            valued = f" _(+ {', '.join(v['rewards'])})_" if v.get("rewards") else ""
            label = f"**{v['label']}**: " if v.get("label") else ""
            lines.append(f"  - Moiragen to {s['nanite']}: {label}{clean(v['why'])}{valued}")
    if e.get("compare"):
        lines.append(f"- Moiragen compared: {clean(e['compare'])}")
    calc = (e.get("checks") or {}).get("calculator")
    if calc:
        lines.append(f"- Calculator check: {calc.get('text')} ({clean(calc.get('how'))})")
    first = f" (first he picked {e['first_choice']})" if e.get("first_choice") else ""
    lines.append(f"- **Moiragen chose {e.get('chosen')}**{first}: {clean(e.get('reason'))}")
    if e.get("wait_and_see"):
        lines.append(f"- Wait and see: {clean(e.get('check'))}")
    lines.append(f"- **Moiragen's answer:** {clean(e.get('answer'))}")
    if e.get("blind"):           # v1.6: he judged blind; the names came back afterwards
        seen = ", ".join(f"{label} was {name}" for label, name in sorted(e["blind"].items()))
        lines.append(f"- Judged blind, names revealed afterwards: {seen}")
    if e.get("pattern"):
        lines.append(f"- *Moiragen looks at his own pattern:* {clean(e['pattern'])}")
    return "\n".join(lines) + "\n"


class Journal:
    """Writes the journal from the life log, catching up first, then following it."""

    def __init__(self, log_file=None, journal_file=None, state_file=None):
        self.log_file = log_file or memory_log.LOG_FILE
        self.journal_file = journal_file or JOURNAL_FILE
        self.state_file = state_file or STATE_FILE
        self._stop = threading.Event()
        self._thread = None

    # ---------- the bookmark ----------

    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {"offset": 0, "day": ""}   # first time: write the whole life log

    def _save_state(self, state: dict) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(self.state_file)

    # ---------- writing ----------

    def write_new(self, note: str = "") -> int:
        """Write every life-log line after the bookmark. Returns how many entries were written.
        note: an optional line written first (e.g. "Moiragen started")."""
        state = self._load_state()
        if not self.log_file.exists():
            return 0
        size = self.log_file.stat().st_size
        if size < state["offset"]:
            state["offset"] = 0                 # the log was replaced (e.g. restored): start again
        if not self.journal_file.exists():
            self.journal_file.write_text(
                "# Moiragen's inner life journal\n\nEvery thought, talk, question, answer and "
                "verdict, written as it happens (from the life log).\n", encoding="utf-8")
        written = 0
        with open(self.log_file, "rb") as f, open(self.journal_file, "a", encoding="utf-8") as j:
            if note:
                j.write(f"\n---\n_{note}_\n")
            f.seek(state["offset"])
            while True:
                raw = f.readline()
                if not raw or not raw.endswith(b"\n"):
                    break                       # nothing more, or a line still being written
                state["offset"] = f.tell()
                try:
                    e = json.loads(raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                text = render(e)
                if not text:
                    continue
                day = e.get("time", "")[:10]
                if day != state.get("day"):
                    state["day"] = day
                    j.write(f"\n## {day}\n\n")
                j.write(text + "\n")
                written += 1
        self._save_state(state)
        return written

    # ---------- running alongside Moiragen ----------

    def start(self) -> None:
        """Catch up on anything missed, then keep following the life log (background thread)."""
        caught = self.write_new(note=f"Moiragen started {datetime.now():%Y-%m-%d %H:%M}")
        if caught:
            with open(self.journal_file, "a", encoding="utf-8") as j:
                j.write(f"_(caught up on {caught} entries written while the journal was not running)_\n")
        self._thread = threading.Thread(target=self._follow, name="journal", daemon=True)
        self._thread.start()

    def _follow(self) -> None:
        while not self._stop.wait(FOLLOW_SECONDS):
            try:
                self.write_new()
            except OSError:
                time.sleep(5)                   # e.g. the file is busy for a moment: try again

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(5)
        self.write_new()                        # the last few lines
