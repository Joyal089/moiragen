# Moiragen – Build Plan

Each step is small, has its own test, and must pass before the next starts.

**Status: all 10 steps built and tested** (tags `v0.1` to `v0.9`, then `v1.0`), plus step 11, the echo-loop fix (`v1.1`), step 12, fairer judging (`v1.2`), step 13, checked facts and a fair cost (`v1.3`), step 14, sleep and the inner-life journal (`v1.4`), and step 15, sleep in memory and fair turns (`v1.5`). Each step's test is `tests/stepN_check.py`; run them all with `tests/run_all.py`.

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
| 11 | **Echo-loop fix** | Verified memory backups; one-off clean-up of repeated lines (first copy kept); echo guard on every saved line and the fine-tuning log; fresh topics for every talk; warmer temperature + repeat penalty; social rounds limited and paused while nobody uses the app | Copies rejected and retried, nothing copied saved or logged, topics rotate, no brain use while resting |
| 12 | **Fairer judging** | Every verdict (Moiragen's or yours) comes with a short reason; small mood boosts for honesty, "I don't know" and good questions, chosen or not; a nanite may disagree ("I think you're wrong, Moiragen") at no health cost, and Moiragen says why he keeps or changes his choice; each nanite's own way of seeing is tracked and valued, never forced; "wait and see" for answers only time can check | Stand-in brain checks every rule exactly; the real model gives a reason to every nanite and marks a question about next Friday "wait and see" |
| 13 | **Checked facts, fair cost** | Plain-Python checks (`facts.py`): claims about the past looked up in the life log (a made-up one is corrected kindly, no credit); a calculator for maths that Moiragen follows; honesty boost only for clear signs; softer disagreements caught; "wait and see" never for imagined situations. Moiragen compares answers and judges the answer, not the speaker. He shares the health cost of a wrong answer with the chosen nanite | Stand-in brain checks every rule, including today's real cases (Two's invented memory, the 2-6-12-20-30 sequence, One's soft disagreement, the friend question) |
| 14 | **Sleep and journal** | Energy comes back for time the app was closed or resting (40 an hour, first 20; at most 8 hours, never above full), on start and when you come back. The inner-life journal (`journal.py`) starts with Moiragen, keeps a bookmark in the life log, and catches up on anything written while it was off | Pretend the app was closed for 2 hours and rested for 1; journal catches up, follows, catches up again, never writes twice |
| 15 | **Sleep in memory, fair turns** | Waking adds "I slept for about X hours..." to every nanite's and Moiragen's memory; choices are counted, all three ways of seeing are valued (dismissive words like "too reflective" are shown back to him to rewrite once, and removed only if still dismissive, each case in the journal), and after 3 in a row Moiragen says why the others were not better; made-up quotes of other nanites and invented events are checked against the life log; "you are correct" means change the choice or say why not | Stand-in brain checks each rule, including the real cases from the v1.4 teaching session (Two's diagnostic sweep, Three's invented quotes) |

Later (not now): nightly fine-tuning, nanites choosing names (the hooks will be there). No Telegram.

## Git routine
- Commit and push after every working change; tag milestones `v0.1`, `v0.2`, ...
- Before every push, check that no `.env`, `.venv`, `memory/`, model files, secrets or tokens are staged.

## Decisions taken by default (tell me to change any)
- **"Being wrong"** = you mark an answer wrong in the chat/viewer. Not being chosen by Moiragen is *not* being wrong: it only causes a mild emotion, never health loss. Disagreeing with Moiragen never costs health either.
- **Honesty and good questions** are judged by Moiragen, with plain-Python checks on top: "I don't know" is found by a pattern, and a "good question" must really contain a question mark.
- **Styles** are measured by simple word counts and shown only to Moiragen, never written into a nanite's own prompt (that would force it).
- **Wait and see**: a question naming a future time ("tonight", "by Friday"), or Moiragen saying LATER. In testing the small model alone missed most predictions, so the plain-Python rule backs it up.
- **Taking turns**: one shared model, a lock makes sure only one mind uses the GPU at a time.
- **Memory layout**: `memory/log.jsonl` (everything, for fine-tuning), `memory/nanites/<id>.json` (each nanite's state + memories), `memory/moiragen.json`, `memory/stories/<date>.md`.
- **Libraries**: `requests`, `python-dotenv` now; `fastapi` + `uvicorn` at step 8. No heavy frameworks.
