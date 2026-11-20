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
- Every new line is checked against what the nanites said recently. A nanite that **repeats** itself or a friend is asked to say something new (see [Keeping their words fresh](#keeping-their-words-fresh)).
- When nobody has used the app for 10 minutes, the nanites **rest** and only the body keeps watch, so nothing piles up overnight.

## Running him

You need the Ollama app running with `gemma3:4b`, and the project's `.venv`.

**Easiest:** double-click `start.bat`. It starts Ollama if needed, wakes Moiragen and opens the viewer.

Or from a terminal in the project folder:

```powershell
.venv\Scripts\python.exe server.py
```

Then open http://127.0.0.1:8765. The server only listens on this laptop. Press Ctrl+C to stop; he finishes his current thought first.

**In the viewer:** click Moiragen to ask him something (the nanites suggest, he decides, and you can mark it Right or Wrong). Click a nanite to talk to it directly. Watch their bars, speech bubbles, the spotlight and the inner-life feed.

If you leave the app alone for 10 minutes (no question, no chat, no mouse or keyboard in the viewer), the top bar shows "Resting while you're away" and the nanites pause. Move the mouse or say something and they carry on. Social moments are also limited to about one every 2 minutes, and at most 12 an hour.

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
| `backups/<date>_<label>/` | full copies of memory, made before anything rewrites it (each checked file by file) |

A damaged file is never deleted. It is set aside and rebuilt from the life log.

## Keeping their words fresh

A small model copies text it can see, and the nanites see their recent memories in every prompt. In November 2026 that started an **echo loop**: one nanite said "It's... interesting, isn't it, how things shift?", it went into memory, and they kept saying it again. Within 11 minutes it had been said 11 times and shown back to them in their prompts 80 times. Now:

- **The echo guard** (`moiragen/echo.py`) checks every new line against each nanite's last 12 lines. If it repeats a sentence (6+ words) or is mostly the same as a recent line, it is rejected and the nanite is told what it repeated and asked to say something new (up to 2 more tries, each a little more adventurous). If it still only repeats, nothing is saved and it says it has nothing new. Two nanites answering the *same* question alike is agreement, not an echo, so that is allowed.
- **The fine-tuning log has one door**: a training example is only written if the line passes that check. The export also leaves out copies from before the guard existed.
- **Fresh topics** (`moiragen/topics.py`): every talk starts from one specific prompt, taking turns between a question with a set shape ("one word for how you feel, then why"), one of the speaker's older memories, and something that recently had everyone's attention.
- **Ollama settings**: the nanites think a little warmer, and a repeat penalty over the whole prompt makes the model avoid words it has already seen. Change them in `.env`:

  | Setting | Default | What it does |
  |---|---|---|
  | `NANITE_TEMPERATURE_BOOST` | `0.1` | added to each nanite's own temperature |
  | `OLLAMA_REPEAT_PENALTY` | `1.15` | above 1.0 avoids repeating words (1.0 = off) |
  | `OLLAMA_REPEAT_LAST_N` | `-1` | how far back it looks (-1 = the whole prompt) |

The extra copies that were already in memory were removed once with `clean_echo.py` (stop Moiragen first). It backs up memory, keeps the first time each repeated line was said, removes only the later copies, and writes a report of every removal next to the backup:

```powershell
.venv\Scripts\python.exe clean_echo.py
.venv\Scripts\python.exe clean_echo.py --apply
```

The first command only previews; `--apply` makes the change.

## Fine-tuning data

```powershell
.venv\Scripts\python.exe export.py --since 2026-11-21 --skip-wrong
```

This writes chat-format examples (`system` / `user` / `assistant`) to `memory/exports/`. Each example is labelled with who thought it, the task, whether Moiragen chose it, and your right/wrong feedback, so a later nightly fine-tune can learn from the good ones. Replies that copy a recent line are left out (the summary says how many).

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
  mind.py        how a nanite thinks (every line passes the echo guard)
  echo.py        the echo guard, and the one door into the fine-tuning log
  topics.py      fresh, specific prompts for every talk
  social.py      talking, helping, comforting, asking why, learning
  mother.py      Moiragen: deciding, explaining, reflecting, inner voice
  body.py        body cells (clock, battery, temperature, load)
  stage.py       the global workspace
  prediction.py  expectations and surprise
  story.py       the daily story
  loop.py        the thinking loop that runs his whole life (rests while you are away)
  export.py      fine-tuning export
  backup.py      verified backups of the memory folder
  cleanup.py     the one-off removal of the echo loop's extra copies
server.py        web server + live event stream
clean_echo.py    runs that clean-up (preview first, then --apply)
viewer/          the browser viewer (index.html, style.css, app.js)
```

## Copyright

Copyright (c) 2026 Joyal Biju. All rights reserved.

All rights reserved. This code may be viewed but not copied, used, modified or sold without my permission.
