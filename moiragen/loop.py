"""The thinking loop: Moiragen's ongoing life, even when nobody talks to him.

The Mind owns everything (nanites, Moiragen, body, stage, predictor) and runs
in a background thread. ALL mind work happens in that one thread, so two
things never change a nanite at the same moment.

Each tick (every ~20 seconds when idle):
  1. SENSE    body cells read the laptop; anything unusual is posted to the stage
  2. PREDICT  readings are compared with expectations; surprises are posted
  3. LIVE     every few ticks the nanites have a social moment (talk, help, rest)
  4. REFLECT  if a decision has not been reflected on yet, Moiragen reflects
  5. ATTEND   thoughts compete on the stage; the winner is broadcast to all,
              and if it matters, Moiragen has a short inner thought about it
  6. STORY    once a day (in the evening) he writes the story of his day

When you ask something, it jumps the queue: the loop handles your question
right away, and the decision goes straight onto the stage.

Everything that happens is sent to `listeners` as event dicts; the viewer
app (step 8/9) will listen to these.
"""

from datetime import date, datetime, timedelta
import queue
import random
import threading
import time
import traceback

from .body import Body
from .llm import BrainError
from .memory_log import log_event
from .mind import nanite_think
from .mother import Moiragen
from .nanite import load_all
from .prediction import Predictor
from .social import after_decision, social_round, needs_help
from .stage import Stage
from .story import story_path, write_daily_story

# --- Tunable numbers ---
TICK_SECONDS = 20          # pause between idle ticks
SOCIAL_EVERY = 3           # nanites have a social moment every N ticks
INNER_THOUGHT_GAP = 60     # at least this many seconds between inner thoughts
INNER_THOUGHT_MIN = 0.5    # only things at least this important get an inner thought
BROADCAST_MIN = 0.6        # nanites remember stage winners at least this important
STORY_HOUR = 22            # write today's story after this hour

# How important each kind of social event is when posted to the stage.
SOCIAL_IMPORTANCE = {"help": 0.65, "ask_why": 0.55, "explain": 0.5, "lesson": 0.55,
                     "support": 0.5, "talk": 0.3, "rest": 0.1}


class Mind:
    def __init__(self, tick_seconds: float = TICK_SECONDS, rng=None):
        self.nanites = load_all()
        self.moiragen = Moiragen.load()
        self.body = Body(self.nanites)
        self.stage = Stage()
        self.predictor = Predictor()
        self.tick_seconds = tick_seconds
        self.rng = rng or random.Random()
        self.listeners = []
        self.inbox = queue.Queue()
        self.tick_count = 0
        self.last_inner = 0.0
        self._stop = threading.Event()
        self._thread = None
        self.last_body = self.body.sense()
        self.stage.subscribe(self._on_spotlight)
        self.last_snapshot = self.snapshot()

    # ---------- a picture of the whole being (for the viewer) ----------

    def snapshot(self) -> dict:
        """Everything the viewer needs to draw Moiragen and the nanites right now.
        Built inside the mind's thread and cached, so the web server can read it
        any time without touching the live objects."""
        m = self.moiragen
        nanites = []
        for n in self.nanites.values():
            nanites.append({
                "id": n.id, "name": n.name, "health": n.health, "energy": n.energy, "mood": n.mood,
                "emotions": {e: s for e, s in n.emotions.items() if s > 0},
                "feeling": (n.strongest_emotion() or ("calm", 0))[0],
                "friendships": dict(n.friendships),
                "temperament": dict(n.temperament),
                "lessons": [l["lesson"] for l in n.lessons[-5:]],
                "memories": [f"[{x['kind']}] {x['text']}" for x in n.memories[-5:]],
            })
        recent = list(m.decisions.values())[-5:]
        return {
            "moiragen": {
                "name": m.name, "self_knowledge": [k["text"] for k in m.self_knowledge[-6:]],
                "body_note": m.body_note,
                "memories": [f"[{x['kind']}] {x['text']}" for x in m.memories[-5:]],
            },
            "nanites": nanites,
            "body": self.last_body,
            "spotlight": self.stage.spotlight.as_dict() if self.stage.spotlight else None,
            "stage_history": [t.as_dict() for t in self.stage.history[-10:]],
            "decisions": recent,
        }

    def _vitals(self) -> None:
        """Refresh the cached snapshot and tell listeners (the viewer redraws its bars)."""
        self.last_snapshot = self.snapshot()
        self.emit("vitals", **self.last_snapshot)

    # ---------- events out ----------

    def subscribe(self, fn) -> None:
        """fn(event_dict) is called for everything that happens."""
        self.listeners.append(fn)

    def emit(self, type_: str, **data) -> dict:
        event = {"type": type_, "time": datetime.now().isoformat(timespec="seconds"), **data}
        for fn in list(self.listeners):
            try:
                fn(event)
            except Exception:
                traceback.print_exc()  # a broken listener must never stop the mind
        return event

    def _social(self, e: dict) -> None:
        """Send a social event out and offer it to the stage.
        (The social event's own "type", e.g. "talk", is renamed to "action".)"""
        data = {k: v for k, v in e.items() if k != "type"}
        self.emit("social", action=e["type"], **data)
        self.stage.post(e["from"], e["type"], e.get("text", ""), SOCIAL_IMPORTANCE.get(e["type"], 0.3))

    # ---------- questions in ----------

    def call(self, fn, *args, timeout: float = 300):
        """Run fn(*args) inside the mind's own thread and wait for the result.

        Other threads (the terminal, the web server) never touch the nanites
        directly; they hand jobs to the loop through this inbox instead.
        """
        reply = queue.Queue(maxsize=1)
        self.inbox.put((fn, args, reply))
        result = reply.get(timeout=timeout)
        if isinstance(result, Exception):
            raise result
        return result

    # Friendly shortcuts for other threads:
    def ask(self, text: str, timeout: float = 300) -> dict:
        """Ask Moiragen (he listens to the nanites and decides)."""
        return self.call(self.handle_question, text, timeout=timeout)

    def chat(self, nanite_id: str, text: str, timeout: float = 300) -> dict:
        """Talk directly to one nanite."""
        return self.call(self.handle_chat, nanite_id, text, timeout=timeout)

    def give_feedback(self, decision_id: str, correct: bool, note: str = "") -> str:
        """Tell Moiragen whether a decision was right."""
        return self.call(self.handle_feedback, decision_id, correct, note)

    def request_story(self, timeout: float = 300) -> str | None:
        """Write today's story now."""
        return self.call(self.handle_story, timeout=timeout)

    # The jobs themselves (always run in the mind's thread):
    def handle_chat(self, nanite_id: str, text: str) -> dict:
        n = self.nanites[nanite_id]
        self.emit("chat", **{"from": "user", "to": n.name, "text": text})
        self.emit("thinking", who=n.name, about=text)
        out = nanite_think(n, text)
        self.emit("chat", **{"from": n.name, "to": "user", "text": out["reply"]})
        self.stage.post(n.name, "chat", f"The human said to {n.name}: \"{text}\"", 0.6)
        self._attend()
        self._vitals()
        return out

    def handle_feedback(self, decision_id: str, correct: bool, note: str = "") -> str:
        msg = self.moiragen.feedback(decision_id, correct, self.nanites, note)
        self.emit("feedback", decision_id=decision_id, correct=correct, note=note, reply=msg)
        if not correct:
            self.stage.post("user", "mistake", f"The human said a decision was wrong. {note}", 0.9)
            self._attend()
        self._vitals()
        return msg

    def handle_story(self) -> str | None:
        day = date.today().isoformat()
        text = write_daily_story(self.moiragen, day)
        if text:
            self.emit("story", day=day, text=text)
        return text

    def handle_question(self, text: str) -> dict:
        self.emit("question", text=text)
        self.stage.post("user", "question", text, 1.0)
        d = self.moiragen.decide(text, self.nanites, notify=self.emit)
        self.emit("decision", **d)
        self.stage.post("Moiragen", "decision",
                        f"I chose {d['chosen']}'s idea for \"{text}\": {d['reason']}", 0.9,
                        decision_id=d["id"])
        for e in after_decision(d, self.nanites, self.moiragen, self.rng):
            self._social(e)
        self._attend()
        self._vitals()
        return d

    # ---------- one tick of life ----------

    def tick(self) -> None:
        self.tick_count += 1

        # 1. SENSE
        s = self.body.sense()
        self.last_body = s
        self.moiragen.body_note = self.body.describe(s)
        self.emit("body", **s)
        if s["state"] != "fine":
            self.stage.post("body", s["state"], s["why"], 0.85 if s["state"] == "hot" else 0.6)
        for name in s["energy"]["tired_nanites"]:
            self.stage.post("body", "tired", f"{name} is tired.", 0.35)
        for n in self.nanites.values():
            if needs_help(n):
                self.stage.post(n.name, "hurt", f"{n.name} is hurt (health {n.health:.0f}).", 0.75)

        # 2. PREDICT
        for sur in self.predictor.check_body(s):
            text = f"{sur['what']} was {sur['got']}, I expected about {sur['expected']}."
            self.moiragen.remember("surprise", text, **sur)
            self.emit("surprise", text=text, **sur)
            self.stage.post("predictor", "surprise", text, sur["surprise"])

        # 3. LIVE
        if self.tick_count % SOCIAL_EVERY == 0:
            for e in social_round(self.nanites, self.rng):
                self._social(e)

        # 4. REFLECT (on the newest decision from the last day not yet reflected on)
        day_ago = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
        unreflected = [d for d in self.moiragen.decisions.values()
                       if not d.get("reflected") and d["time"] >= day_ago]
        if unreflected:
            r = self.moiragen.reflect(unreflected[-1])
            self.emit("reflection", **r)
            if r["about_me"]:
                self.stage.post("Moiragen", "reflection", f"About me: {r['about_me']}", 0.5)

        # 5. ATTEND
        self._attend()

        # 6. STORY
        self._maybe_write_story()

        self.moiragen.save()
        for n in self.nanites.values():
            n.save()
        self._vitals()

    def _attend(self) -> None:
        """Let thoughts compete, and react to the winner."""
        winner = self.stage.compete(self.rng)
        if winner is None:
            return
        surprise = self.predictor.events.observe(winner.kind)
        if surprise is not None and surprise >= 0.85 and winner.kind != "surprise":
            expected = self.predictor.events.predict()
            log_event("event_surprise", "Moiragen", event_kind=winner.kind, surprise=surprise)
            self.emit("surprise", text=f"I did not expect '{winner.kind}' now.", surprise=surprise,
                      what="event", got=winner.kind, expected=expected)

        if (winner.importance >= INNER_THOUGHT_MIN and winner.source != "user"
                and time.time() - self.last_inner >= INNER_THOUGHT_GAP):
            self.last_inner = time.time()
            thought = self.moiragen.inner_thought(f"{winner.source}: {winner.text}")
            self.emit("inner", text=thought, about=winner.as_dict())

    def _on_spotlight(self, winner) -> None:
        """Broadcast: everyone learns what won attention; important things are remembered."""
        self.emit("stage", **winner.as_dict())
        if winner.importance >= BROADCAST_MIN:
            for n in self.nanites.values():
                if n.name != winner.source:
                    n.remember("noticed", f"Everyone's attention went to: {winner.source}: {winner.text[:150]}")

    def _maybe_write_story(self) -> None:
        """Yesterday's story if it was missed; today's after STORY_HOUR."""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        today = date.today().isoformat()
        for day, due in ((yesterday, True), (today, datetime.now().hour >= STORY_HOUR)):
            if due and not story_path(day).exists():
                text = write_daily_story(self.moiragen, day)
                if text:
                    self.emit("story", day=day, text=text)
                    return  # one story per tick is enough work

    # ---------- running ----------

    def step(self, wait: float | None = None) -> None:
        """Handle one question if one is waiting (up to `wait` seconds), else tick."""
        try:
            fn, args, reply = self.inbox.get(timeout=wait if wait is not None else self.tick_seconds)
        except queue.Empty:
            self.tick()
            return
        try:
            reply.put(fn(*args))
        except Exception as e:
            reply.put(e)
            raise

    def run(self) -> None:
        """The endless loop (until stop()). Errors are logged, never fatal."""
        self.emit("awake", text="Moiragen is awake.")
        failures = 0  # errors in a row
        while not self._stop.is_set():
            try:
                self.step()
                if failures:
                    self.emit("awake", text="Moiragen's brain is working again.")
                failures = 0
            except Exception as e:
                failures += 1
                if isinstance(e, BrainError):
                    text = "I can't reach my brain (is the Ollama app running?). I'll keep trying."
                else:
                    text = f"Something went wrong: {e!r}"
                # Report the first error, then only every 10th, so the log is not flooded.
                if failures == 1 or failures % 10 == 0:
                    log_event("error", "mind", text=repr(e), failures=failures)
                    self.emit("error", text=text)
                # Wait longer after each failure in a row (2s, 4s, 8s ... up to 60s).
                self._stop.wait(min(60, 2 ** failures))
        self.emit("asleep", text="Moiragen's loop stopped.")

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name="moiragen-mind", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 120) -> None:
        self._stop.set()
        self.inbox.put((lambda: None, (), queue.Queue(maxsize=1)))  # wake the loop if it is waiting
        if self._thread:
            self._thread.join(timeout)
