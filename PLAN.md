# Moiragen – Build Plan

Each step is small, has its own test, and must pass before the next starts.

| # | Step | What gets built | How we test it |
|---|------|-----------------|----------------|
| 1 | **Foundation** | `config.py` (reads `.env`), `llm.py` (talks to Ollama, one-at-a-time lock), `memory_log.py` (append-only JSONL log in `./memory`) | Ask gemma3:4b a question, see the reply, see it logged |
| 2 | **Nanite body** | `Nanite` class: health, energy, mood, emotions, friendships, random temperament; own memory file; blueprint copy; save / load / rebuild | Create 3 nanites, save, reload, break one and rebuild it |
| 3 | **Nanite thinking** | A nanite answers a question using its temperament + recent memories; thinking costs energy, resting refills it | Ask each nanite the same question, compare answers and energy |
| 4 | **Moiragen decides** | Moiragen hears all three suggestions, picks one, says why; you can mark it right/wrong → health changes | CLI chat: ask a question, see 3 suggestions + choice + reason |
| 5 | **Friendship & care** | Nanites choose who to talk to, friendships rise/fall, healthy ones help hurt ones, emotions (tired, happy, sad, grateful) shape next behaviour. A nanite whose suggestion was not chosen feels mildly disappointed or left out (no health loss), can ask why another answer won and learn from it, and the others can notice and support it | Hurt a nanite, watch another help it and friendship change; lose a vote, watch it ask why and get comforted |
| 6 | **Body cells** | Plain-Python code nanites: clock, energy monitor, GPU temperature (`nvidia-smi`); they slow thinking when the laptop is hot | Print body status; fake a high temperature and see the slowdown |
| 7 | **Consciousness layer** | Global workspace "stage", background thinking loop, prediction + surprise, reflection on choices, daily life story | Leave it running a few minutes, read his thoughts and story |
| 8 | **Backend server** | FastAPI + WebSocket that runs the mind and streams every event | Open the event stream, see live events |
| 9 | **Viewer app** | Local web page: Moiragen centre, 3 nanites around him, bars, live speech bubbles/lines, suggestions + final choice, click to chat | Use it in the browser |
| 10 | **Polish** | Fine-tuning-ready log export, error handling, README | Full run-through |

Later (not now): nightly fine-tuning, nanites choosing names (the hooks will be there). No Telegram.

## Git routine
- Commit and push after every working change; tag milestones `v0.1`, `v0.2`, ...
- Before every push, check that no `.env`, `.venv`, `memory/`, model files, secrets or tokens are staged.

## Decisions taken by default (tell me to change any)
- **"Being wrong"** = you mark an answer wrong in the chat/viewer. Not being chosen by Moiragen is *not* being wrong: it only causes a mild emotion, never health loss.
- **Taking turns**: one shared model, a lock makes sure only one mind uses the GPU at a time.
- **Memory layout**: `memory/log.jsonl` (everything, for fine-tuning), `memory/nanites/<id>.json` (each nanite's state + memories), `memory/moiragen.json`, `memory/stories/<date>.md`.
- **Libraries**: `requests`, `python-dotenv` now; `fastapi` + `uvicorn` at step 8. No heavy frameworks.
