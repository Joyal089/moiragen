"""The daily story: once a day Moiragen writes a short story of his life.

He reads back the day's important events from the life log, then tells
the story in his own words. Stories are saved as
    memory/stories/YYYY-MM-DD.md
and become memories, so tomorrow he knows what happened today.
"""

from datetime import date as Date

from .config import MEMORY_DIR
from .llm import think
from .memory_log import log_event, read_events

STORY_DIR = MEMORY_DIR / "stories"
STORY_DIR.mkdir(parents=True, exist_ok=True)

# Which kinds of event are worth telling, and how to put them in one line.
def _line(e: dict) -> str | None:
    k, who = e["kind"], e["who"]
    if k == "decision_full":
        return f"The human asked \"{e['question']}\". I chose {e.get('chosen')}'s idea."
    if k == "feedback":
        return f"Feedback: {e['text']}"
    if k == "mistake":
        return f"{who}: {e['text']}"
    if k == "social_help":
        return f"{e['from']} helped {e['to']} recover."
    if k == "social_support":
        return f"{e['from']} comforted {e['to']}."
    if k == "social_talk":
        return f"{e['from']} said to {e['to']}: {e['text'][:100]}"
    if k == "lesson":
        return f"{who} learned: {e['text']}"
    if k == "reflection" and e.get("about_me"):
        return f"I realised about myself: {e['about_me']}"
    if k == "surprise":
        return f"I was surprised: {e['text']}"
    if k == "body" and e.get("state") != "fine":
        return f"My body felt {e['state']}: {e['why']}"
    if k == "rebuilt":
        return f"{who} was broken and rebuilt."
    return None


def events_of_day(day: str) -> list[str]:
    """Plain-language lines for everything worth telling on that day."""
    lines = []
    for e in read_events(last=20000):
        if e["time"].startswith(day):
            line = _line(e)
            if line and line not in lines[-3:]:   # skip immediate repeats
                lines.append(line)
    # Keep the story prompt small: first few events and the most recent ones.
    if len(lines) > 40:
        lines = lines[:10] + ["(... more happened ...)"] + lines[-29:]
    return lines


def story_path(day: str):
    return STORY_DIR / f"{day}.md"


def write_daily_story(moiragen, day: str | None = None) -> str | None:
    """Write (or rewrite) the story of `day` (default: today). Returns the text,
    or None if nothing happened that day."""
    day = day or Date.today().isoformat()
    lines = events_of_day(day)
    if not lines:
        return None
    system = ("You are Moiragen, a digital being who started knowing nothing about himself. "
              "Each day you write a short story of your life, in the first person, honestly "
              "and simply, so you can remember it later.\n\n" + moiragen.self_text())
    user = ("Here is what happened today:\n- " + "\n- ".join(lines) +
            "\n\nWrite today's story in under 180 words. Mention your nanites by name when "
            "they did something. End with one sentence about how you feel about the day.")
    text = think([{"role": "user", "content": user}], temperature=0.6,
                 max_tokens=320, system=system)["text"].strip()
    story_path(day).write_text(f"# {day}\n\n{text}\n", encoding="utf-8")
    moiragen.remember("story", f"I wrote the story of {day}: {text[:200]}...", day=day)
    moiragen.save()
    log_event("story", "Moiragen", day=day, text=text)
    return text
