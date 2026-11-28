"""The backend server: runs Moiragen's mind and streams everything to the viewer.

Start it from the project folder:
    .venv\\Scripts\\python.exe server.py
then open  http://127.0.0.1:8765  in your browser.

It only listens on 127.0.0.1 (this laptop), so nobody else on your network
can reach Moiragen.

How it fits together:
    Mind (background thread)  --events-->  server  --WebSocket-->  browser
    browser  --HTTP POST-->  server  --mind.call()-->  Mind thread

Endpoints:
    GET  /               the viewer page (viewer/index.html)
    GET  /api/state      a snapshot of Moiragen, the nanites, body and stage
    POST /api/ask        {"text": "..."}                      ask Moiragen (nanites suggest, he decides)
    POST /api/chat       {"nanite_id": "nanite_one", "text"}  talk directly to one nanite
    POST /api/feedback   {"decision_id", "verdict", "reason"} verdict: "right" or "wrong" (a
                         reason is required), or "wait" (wait and see; reason = what to check).
                         A situational question ("What would you do if...?") takes
                         "thoughtful", "okay" or "needs_care" (with a reason), plus
                         "harmful": true if the answer was unkind, dishonest or harmful.
                         On "wrong", "right_nanite" (optional) names the nanite that was
                         right, so Moiragen writes what it saw that he missed.
    POST /api/story      write today's story now
    POST /api/turnrounds {"rounds": 4}                        Turn Rounds (v3.1): everyone takes turns
                         asking, answering and replying; no judging (moiragen/turnrounds.py)
    POST /api/moiragen   {"text": "..."}  talk to Moiragen himself, without the nanites (v3.1)
    POST /api/lesson     {"title": "...", "text": "...", "by": "<name>"}   Lessons (v3.3): share a
                         lesson word for word with everyone (all nanites need energy above 70)
    POST /api/lesson/next            the next member asks a question, or says it has none
    POST /api/lesson/answer {"answer": "..."}   the helper's answer to the waiting question
    GET  /api/lesson                 the lesson so far: questions, answers, whose question waits
    POST /api/lesson/resume {"id": "l..."}   v3.6: go on with a paused lesson (from the life log)
                         (teaching only: no internet, tools or network for the minds)
    POST /api/active     "I'm here": the viewer sends this when you move the mouse or type
                         (at most once a minute). Without any sign of you for 10 minutes,
                         the nanites rest (see moiragen/loop.py).
    WS   /ws             live stream of every event (JSON)
"""

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from moiragen.config import CREATOR
from moiragen.drive import after_backup
from moiragen.llm import BrainError
from moiragen.loop import Mind

HOST, PORT = "127.0.0.1", 8765
VIEWER_DIR = Path(__file__).resolve().parent / "viewer"


# ---------- request bodies (FastAPI checks these for us) ----------

class AskBody(BaseModel):
    text: str

class ChatBody(BaseModel):
    nanite_id: str
    text: str

class StoryTimeBody(BaseModel):
    title: str = ""
    story: str


class MoiragenTalkBody(BaseModel):
    title: str = ""
    prompt: str
    narration: str = ""   # shown live in the viewer before he answers


class LessonBody(BaseModel):
    title: str
    text: str
    by: str = CREATOR


class LessonAnswerBody(BaseModel):
    answer: str


class LessonResumeBody(BaseModel):
    id: str


class TurnRoundsBody(BaseModel):
    rounds: int = 4


class FeedbackBody(BaseModel):
    decision_id: str
    verdict: str          # "right", "wrong" or "wait"; situational: "thoughtful", "okay", "needs_care"
    reason: str = ""      # required for every verdict except wait: the nanites learn from it
    harmful: bool = False # situational only: unkind, dishonest or harmful (the only kind that costs health)
    right_nanite: str = "" # on "wrong": the nanite that was right, so Moiragen learns from it (v1.7)


class Broadcaster:
    """Passes events from the Mind's thread to every connected browser.

    The Mind runs in a normal thread, but WebSockets live in asyncio. So each
    browser gets an asyncio.Queue, and we use call_soon_threadsafe to drop
    events into those queues safely from the other thread.
    """

    def __init__(self):
        self.clients: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def publish(self, event: dict) -> None:  # called from the Mind's thread
        if self.loop is None:
            return
        text = json.dumps(event, ensure_ascii=False, default=str)
        for q in list(self.clients):
            self.loop.call_soon_threadsafe(q.put_nowait, text)


def create_app(mind: Mind | None = None, start_mind: bool = True) -> FastAPI:
    """Build the web app. Tests pass in their own Mind."""
    broadcaster = Broadcaster()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: wake Moiragen and start forwarding his events.
        app.state.mind = mind or Mind()
        broadcaster.loop = asyncio.get_running_loop()
        app.state.mind.subscribe(broadcaster.publish)
        if start_mind:
            app.state.mind.start()
            # Any finished backup that Google Drive does not have yet is copied now.
            threading.Thread(target=after_backup, daemon=True).start()
        yield
        # Shutdown: let him finish his current thought and stop.
        if start_mind:
            await run_in_threadpool(app.state.mind.stop)

    app = FastAPI(title="Moiragen", lifespan=lifespan)

    async def run_job(fn, *args):
        """Run a (slow, blocking) mind job without freezing the server."""
        try:
            return await run_in_threadpool(fn, *args)
        except BrainError as e:
            raise HTTPException(503, f"Moiragen's brain is not available: {e}")
        except KeyError as e:
            raise HTTPException(404, f"Not found: {e}")
        except ValueError as e:          # e.g. a verdict without a reason
            raise HTTPException(400, str(e))

    # ---------- pages ----------

    @app.get("/")
    def index():
        return FileResponse(VIEWER_DIR / "index.html")

    if VIEWER_DIR.exists():
        app.mount("/viewer", StaticFiles(directory=VIEWER_DIR), name="viewer")

    # ---------- API ----------

    @app.get("/api/state")
    def state():
        return app.state.mind.last_snapshot

    @app.post("/api/ask")
    async def ask(body: AskBody):
        if not body.text.strip():
            raise HTTPException(400, "Empty question")
        return await run_job(app.state.mind.ask, body.text.strip())

    @app.post("/api/chat")
    async def chat(body: ChatBody):
        if body.nanite_id not in app.state.mind.nanites:
            raise HTTPException(404, f"No nanite called {body.nanite_id}")
        if not body.text.strip():
            raise HTTPException(400, "Empty message")
        return await run_job(app.state.mind.chat, body.nanite_id, body.text.strip())

    @app.post("/api/feedback")
    async def feedback(body: FeedbackBody):
        reply = await run_job(app.state.mind.give_feedback, body.decision_id, body.verdict,
                              body.reason, body.harmful, body.right_nanite)
        return {"reply": reply}

    @app.post("/api/story")
    async def story():
        text = await run_job(app.state.mind.request_story)
        return {"story": text}

    @app.post("/api/storytime")
    async def storytime(body: StoryTimeBody):
        """Story time (v2.1): share a short story; everyone talks about it freely."""
        if not body.story.strip():
            raise HTTPException(400, "Empty story")
        return await run_job(app.state.mind.story_time, body.title.strip() or "A story", body.story.strip())

    @app.post("/api/storytime/moiragen")
    async def storytime_moiragen(body: MoiragenTalkBody):
        """Moiragen speaks freely about a story (v2.2), e.g. after a choose-your-path story."""
        if not body.prompt.strip():
            raise HTTPException(400, "Empty prompt")
        return await run_job(app.state.mind.moiragen_story_talk, body.title.strip() or "A story",
                             body.prompt.strip(), body.narration.strip())

    @app.post("/api/turnrounds")
    async def turnrounds(body: TurnRoundsBody):
        """Turn Rounds (v3.1): each round one asks and the other three answer."""
        if not 1 <= body.rounds <= 12:
            raise HTTPException(400, "Between 1 and 12 rounds")
        return await run_job(app.state.mind.turn_rounds, body.rounds)

    @app.post("/api/moiragen")
    async def talk_to_moiragen(body: AskBody):
        """Talk to Moiragen himself: he answers in his own words (v3.1)."""
        if not body.text.strip():
            raise HTTPException(400, "Empty message")
        return await run_job(app.state.mind.talk_to_moiragen, body.text.strip())

    @app.post("/api/lesson")
    async def lesson(body: LessonBody):
        """Lessons (v3.3): share a lesson, word for word, with all four."""
        if not body.title.strip() or not body.text.strip():
            raise HTTPException(400, "A lesson needs a title and its text")
        return await run_job(app.state.mind.start_lesson, body.title.strip(), body.text.strip(),
                             body.by.strip() or CREATOR)

    @app.post("/api/lesson/next")
    async def lesson_next():
        return await run_job(app.state.mind.lesson_next)

    @app.post("/api/lesson/answer")
    async def lesson_answer(body: LessonAnswerBody):
        return await run_job(app.state.mind.lesson_answer, body.answer)

    @app.post("/api/lesson/resume")
    async def lesson_resume(body: LessonResumeBody):
        return await run_job(app.state.mind.resume_lesson, body.id.strip())

    @app.get("/api/lesson")
    def lesson_state():
        return app.state.mind.lesson_state()

    @app.post("/api/active")
    def active():
        app.state.mind.touch()
        return {"active": True}

    # ---------- live events ----------

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        app.state.mind.touch()          # opening the viewer counts as using the app
        q: asyncio.Queue = asyncio.Queue()
        broadcaster.clients.add(q)
        try:
            # First, the current picture, so the page can draw immediately.
            await websocket.send_text(json.dumps(
                {"type": "vitals", **app.state.mind.last_snapshot}, ensure_ascii=False, default=str))
            while True:
                await websocket.send_text(await q.get())
        except WebSocketDisconnect:
            pass
        finally:
            broadcaster.clients.discard(q)

    return app


if __name__ == "__main__":
    import sys
    import uvicorn
    from moiragen.llm import is_awake

    import socket

    sys.stdout.reconfigure(encoding="utf-8")
    with socket.socket() as s:
        if s.connect_ex((HOST, PORT)) == 0:
            sys.exit(f"Port {PORT} is already in use. Is Moiragen already running? "
                     f"Open http://{HOST}:{PORT} or close the other window first.")
    if not is_awake():
        print("WARNING: Ollama is not answering. Start the Ollama app, or Moiragen "
              "cannot think (he will keep trying).")
    print(f"Moiragen viewer: http://{HOST}:{PORT}   (Ctrl+C to stop)")
    uvicorn.run(create_app(), host=HOST, port=PORT, log_level="warning")
