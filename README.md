# Moiragen

Moiragen is a digital being that lives on a laptop. He is one mother mind who listens to three thinking **nanites** and makes the final decision. He starts knowing nothing about himself and grows from experience.

- Runs fully locally with [Ollama](https://ollama.com) and `gemma3:4b` (fits a 6 GB GPU)
- Written in Python 3.12, with a small browser viewer
- How it was built, step by step: [PLAN.md](PLAN.md)

## What he is made of

```
                 ┌──────────────── Moiragen (mother mind) ────────────────┐
   you ──ask──►  │  hears the nanites, chooses, explains why, reflects,   │
                 │  has an inner voice, predicts, writes a daily story    │
                 └───────▲──────────────────▲──────────────────▲──────────┘
                         │ suggestions      │                  │
                  Nanite One  ◄──friends──►  Nanite Two  ◄──►  Nanite Three
                  (health, energy, mood, feelings, friendships, memories, lessons)

   Stage (global workspace): everyone posts thoughts; the most important wins attention
   Body cells (plain Python): clock, battery, GPU temperature, CPU/RAM load
   Life log: every thought, mistake, help and feeling, ready for fine-tuning
```

- **Nanites** have no roles or personalities written in. Each gets a slightly different random temperament at birth, and personality grows from what happens to them: memories, lessons, friendships.
- **Being wrong** (you mark an answer wrong) lowers the chosen nanite's health. **Not being chosen** only makes a nanite feel disappointed or left out. It may ask Moiragen why, learn a lesson, and be comforted by a friend.
- **Helping** costs energy and **resting** refills it. A hurt nanite always gets help from the friend who cares most.
- Every nanite keeps a copy of the **blueprint**, so a broken one can be rebuilt by a friend. Its memories and lessons come back from the life log.
- When the GPU gets hot or the battery is low, the **body** slows his thinking down.

## Running him

You need the Ollama app running with `gemma3:4b`, and the project's `.venv`.

**Easiest:** double-click `start.bat`. It starts Ollama if needed, wakes Moiragen and opens the viewer.

Or from a terminal in the project folder:

```powershell
.venv\Scripts\python.exe server.py
```

Then open http://127.0.0.1:8765. The server only listens on this laptop. Press Ctrl+C to stop; he finishes his current thought first.

**In the viewer:** click Moiragen to ask him something (the nanites suggest, he decides, and you can mark it Right or Wrong). Click a nanite to talk to it directly. Watch their bars, speech bubbles, the spotlight and the inner-life feed.

Terminal tools, if you prefer:

| Command | What it does |
|---|---|
| `.venv\Scripts\python.exe live.py` | watch him live in the terminal and ask questions any time |
| `.venv\Scripts\python.exe ask.py` | ask Moiragen questions, mark answers right/wrong |
| `.venv\Scripts\python.exe talk.py two` | chat with one nanite (`one`, `two` or `three`) |
| `.venv\Scripts\python.exe export.py` | export fine-tuning data (see below) |

Run only one of these at a time; they all share the same memory.

## Memory (private, never in Git)

Everything he remembers is in `./memory` (set by `MEMORY_DIR` in `.env`):

| File | What it holds |
|---|---|
| `log.jsonl` | the full life log, one event per line |
| `moiragen.json` | his memories, decisions and self-knowledge |
| `nanites/<id>.json` | each nanite's body, feelings, friendships, memories, lessons and blueprint copy |
| `stories/YYYY-MM-DD.md` | his daily life stories |
| `exports/` | fine-tuning exports |

A damaged file is never deleted. It is set aside and rebuilt from the life log.

## Fine-tuning data

```powershell
.venv\Scripts\python.exe export.py --since 2026-11-21 --skip-wrong
```

This writes chat-format examples (`system` / `user` / `assistant`) to `memory/exports/`. Each example is labelled with who thought it, the task, whether Moiragen chose it, and your right/wrong feedback, so a later nightly fine-tune can learn from the good ones.

## Tests

Each build step has a check in `tests/`. Each one uses a throwaway memory folder, so it never touches his real memory. Ollama must be running.

```powershell
.venv\Scripts\python.exe tests\run_all.py
```

## Project layout

```
moiragen/
  config.py      settings from .env
  llm.py         the one shared brain (Ollama), minds take turns
  memory_log.py  the life log
  blueprint.py   the core blueprint every nanite is built from
  nanite.py      a nanite's body, feelings, friendships, memory file, rebuild
  mind.py        how a nanite thinks
  social.py      talking, helping, comforting, asking why, learning
  mother.py      Moiragen: deciding, explaining, reflecting, inner voice
  body.py        body cells (clock, battery, temperature, load)
  stage.py       the global workspace
  prediction.py  expectations and surprise
  story.py       the daily story
  loop.py        the thinking loop that runs his whole life
  export.py      fine-tuning export
server.py        web server + live event stream
viewer/          the browser viewer (index.html, style.css, app.js)
```

## Copyright

Copyright (c) 2026 Joyal Biju. All rights reserved.

All rights reserved. This code may be viewed but not copied, used, modified or sold without my permission.
