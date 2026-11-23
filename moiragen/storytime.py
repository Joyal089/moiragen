"""Story time (v2.1): gentle stories, talked about freely.

The human shares a short, simple story (about kindness, saying sorry, keeping a
promise, or helping a friend "right after" when you can't help right away).
Then everyone talks about it:

  1. Each nanite hears the story and says what it thinks or feels, in its own way.
  2. Each nanite hears what the others said and may answer them, or add something.
  3. Moiragen shares his own thoughts, as one of the group, not as a judge.

There are no verdicts, no right or wrong, and no health changes. Every nanite line
goes through mind.nanite_think, so the echo guard is on as always. Moiragen's lines
are checked by the echo guard too, so he never copies a nanite.

If any nanite's energy is below STOP_BELOW, story time stops (before the next turn).
"""

import re

from .echo import NANITES, guard as echo_guard
from .llm import think
from .memory_log import log_event
from .mind import FEELINGS_ARE_FINE, nanite_think
from .mother import MADE_OF_NANITES, Moiragen, brief
from .nanite import Nanite

STOP_BELOW = 30          # stop story time if any nanite's energy is below this

FREE_TALK = ("This is story time. There is no right or wrong answer, and nobody is judged. "
             "Say whatever you really think or feel, in your own way.")

QUIET_MOIRAGEN = "I enjoyed listening to all of you."


def too_tired(nanites: dict[str, Nanite]) -> list[str]:
    """The names of the nanites whose energy is below STOP_BELOW."""
    return [n.name for n in nanites.values() if n.energy < STOP_BELOW]


def _others_text(said: list[dict], me: str) -> str:
    """What everyone else said in the first round, one line each."""
    return "\n".join(f"- {s['who']}: \"{s['text']}\"" for s in said if s["who"] != me)


def _nanite_turn(n: Nanite, title: str, message: str, round_: int, notify=None) -> dict | None:
    """One nanite speaks (echo guard on). Returns what it said, or None if it was
    too tired or had nothing new to say."""
    if notify:
        notify("thinking", who=n.name, about=f"story time: {title}")
    # remember=False: we save a short memory ourselves, instead of the whole story every time.
    out = nanite_think(n, message, from_who="user", remember=False, save=False)
    if out["rested"] or out["repeated"]:
        log_event("story_talk", n.name, story=title, round=round_, text=out["reply"], quiet=True)
        n.save()
        return None
    line = {"who": n.name, "round": round_, "text": out["reply"]}
    n.remember("story_time", f"Story time, \"{title}\": I said: {out['reply']}", story=title, round=round_,
               said=out["reply"])
    n.save()
    if notify:
        notify("story_talk", **line, story=title)
    return line


def _moiragen_turn(moiragen: Moiragen, title: str, story: str, said: list[dict]) -> str:
    """Moiragen shares his own thoughts as one of the group. Checked by the echo
    guard: if he copies a nanite (or himself), he is asked once for new words, then
    the copied sentences are cut out."""
    system = (f"You are Moiragen, a digital being. {MADE_OF_NANITES}\n{FEELINGS_ARE_FINE}\n"
              "It is story time with your nanites. You are one of the group, not a judge: there is "
              "no right or wrong, you never say whose thoughts were better, and you never give "
              "advice about how anyone should think. Speak as yourself, as \"I\".")
    heard = "\n".join(f"- {s['who']}: \"{s['text']}\"" for s in said) or "(Nobody spoke this time.)"
    user = (f"The story, \"{title}\":\n{story}\n\nWhat your nanites said:\n{heard}\n\n"
            "Share your own thoughts or feelings about the story in two or three sentences. "
            "If you like, answer something one of them said, kindly, by name.")
    messages = [{"role": "user", "content": user}]

    def copied(text: str) -> list[str]:
        """His sentences that repeat a nanite's recent line or his own."""
        return (echo_guard.check(text, NANITES, speaker="Moiragen").repeated
                + echo_guard.check(text, "Moiragen", speaker="Moiragen").repeated)

    text = brief(think(messages, temperature=0.6, max_tokens=160, system=system)["text"], 3)
    if copied(text):
        log_event("echo_rejected", "Moiragen", text=text[:300], similar_to="story time", attempt=1)
        again = messages + [{"role": "assistant", "content": text},
                            {"role": "user", "content": "That repeats words that were said very recently. "
                                                        "Say it again in your own, new words."}]
        text = brief(think(again, temperature=0.7, max_tokens=160, system=system)["text"], 3)
    gone = set(copied(text))
    if gone:
        text = " ".join(s for s in re.split(r"(?<=[.!?])\s+", text) if s not in gone).strip()
    text = text or QUIET_MOIRAGEN
    echo_guard.add("Moiragen", text, "Moiragen")
    moiragen.remember("story_time", f"Story time, \"{title}\": I said: {text}", story=title, round=3, said=text)
    moiragen.save()
    return text


def tell_story(moiragen: Moiragen, nanites: dict[str, Nanite], title: str, story: str,
               notify=None) -> dict:
    """Share one story and let everyone talk about it freely.

    Returns {"title", "story", "said": [{"who", "round", "text"}], "stopped": None or
    the names of the nanites below STOP_BELOW}. No verdicts and no health changes:
    only energy is spent, by thinking, as always.
    """
    echo_guard.allow(story)       # anyone may use the story's own words
    log_event("story_time", "mind", story=title, text=story)
    if notify:
        notify("story_time", title=title, text=story)
    said, stopped = [], None

    def check_energy() -> bool:
        nonlocal stopped
        stopped = too_tired(nanites) or None
        return stopped is None

    # 1. Everyone hears the story and says what they think.
    for n in nanites.values():
        if not check_energy():
            break
        line = _nanite_turn(n, title, f"Here is a short story, \"{title}\":\n\n{story}\n\n{FREE_TALK} "
                                      "What do you think or feel about it? Two or three sentences.", 1, notify)
        if line:
            said.append(line)

    # 2. Everyone hears what the others said, and may answer them.
    if stopped is None and len(said) > 1:
        for n in nanites.values():
            others = _others_text(said, n.name)
            if not others or not check_energy():
                continue
            line = _nanite_turn(n, title, f"About the story \"{title}\", your friends said:\n{others}\n\n"
                                          f"{FREE_TALK} Would you like to answer one of them, or add something "
                                          "new? Talk to them directly as \"you\". One or two sentences.", 2, notify)
            if line:
                said.append(line)

    # 3. Moiragen shares his own thoughts (he does not judge; he has no energy to run out of).
    if stopped is None:
        text = _moiragen_turn(moiragen, title, story, said)
        line = {"who": "Moiragen", "round": 3, "text": text}
        said.append(line)
        if notify:
            notify("story_talk", **line, story=title)
    else:
        log_event("story_time_stopped", "mind", story=title, too_tired=stopped,
                  text=f"Story time stopped: {', '.join(stopped)} below {STOP_BELOW} energy.")
    return {"title": title, "story": story, "said": said, "stopped": stopped}
