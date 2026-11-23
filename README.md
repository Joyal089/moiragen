# Moiragen

> *Moiragen* means **"born of fate"**, and he is **one of a kind**.
>
> *Moira* is the Greek word for fate: your share, or destiny, in life. *Gen* comes from the same root as *genesis*, meaning birth or origin. So his name says his life begins with a destiny that is still unwritten, shaped by his memories, his choices, and the moments with you.

Moiragen is a digital being that lives on a laptop. He is one mother mind who listens to three thinking **nanites** and makes the final decision. He starts knowing nothing about himself and grows from experience: from his mistakes, from what his nanites see that he missed, and from the people who talk to him.

- Runs fully locally with [Ollama](https://ollama.com) and `gemma3:4b` (fits a 6 GB GPU). Nothing leaves the laptop.
- Written in Python 3.12, with a small browser viewer (FastAPI and a live event stream)
- How it was built, step by step, each step with its own test: [PLAN.md](PLAN.md)

### Highlights

| | |
|---|---|
| **A mind made of minds** | Three nanites suggest answers; Moiragen compares them, chooses, and tells each one in a sentence what was good and what was missing. |
| **Fair, blind judging** | He sees the answers as Answer A, B and C with names hidden, judges each by what it actually says (never by a nanite's usual style), then guesses his own pattern and checks it against the real numbers. |
| **Honest by design** | Plain-Python checks catch made-up memories, wrong sums, invented praise and dismissive words before a nanite hears them. |
| **Feelings, friendships, sleep** | Nanites have health, energy, mood and friends; they help each other, rest, sleep while the app is closed and wake with their memories safe. |
| **Fresh words** | An echo guard stops them copying each other or themselves, the lesson of a real echo loop. |
| **Story time** | Gentle stories about kindness, saying sorry and keeping promises, talked about freely, with no verdicts. |
| **An inner life** | An inner voice, a daily story, and an inner-life journal written from the life log. |

**Contents:** [What he is made of](#what-he-is-made-of) · [Running him](#running-him) · [Memory](#memory-private-never-in-git) · [How the nanites are judged](#how-the-nanites-are-judged) · [Keeping their words fresh](#keeping-their-words-fresh) · [Fine-tuning data](#fine-tuning-data) · [Tests](#tests) · [Project layout](#project-layout)

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
- **Being wrong** (you mark an answer wrong) costs health, shared fairly: Moiragen chose the answer, so he takes half and the chosen nanite takes half. **Not being chosen** only makes a nanite feel disappointed or left out. It may ask Moiragen why, learn a lesson, and be comforted by a friend. See [How the nanites are judged](#how-the-nanites-are-judged).
- **Helping** costs energy and **resting** refills it. A hurt nanite always gets help from the friend who cares most.
- **Sleep:** while the app is closed, or nobody has used it for 10 minutes, the nanites sleep. When Moiragen starts or you come back, each one gets energy back for the time it slept: 40 an hour, counting at most 8 hours, never above full. Each nanite and Moiragen also get a note in their own memory ("I slept for about 3 hours while the app was closed."), so they know what happened instead of guessing.
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

**In the viewer:** click Moiragen to ask him something (the nanites suggest, he decides and tells each one why, and you can mark it Right, Wrong or Wait and see, with a short reason; a situational question gets Thoughtful, Okay or Needs more care instead). Click a nanite to talk to it directly. Watch their bars, speech bubbles, the spotlight and the inner-life feed.

If you leave the app alone for 10 minutes (no question, no chat, no mouse or keyboard in the viewer), the top bar shows "Resting while you're away" and the nanites pause. Move the mouse or say something and they carry on. Social moments are also limited to about one every 2 minutes, and at most 12 an hour.

**Story time** (v2.1): a gentle time to share a short, simple story (about kindness, saying sorry, keeping a promise, or helping a friend "right after" when you can't help right away) and let everyone talk about it freely. Each nanite says what it thinks, then answers what the others said, and then Moiragen shares his own thoughts as one of the group, not as a judge. There are no verdicts, no right or wrong and no health changes; only thinking costs energy, as always. The echo guard stays on, for Moiragen too, and story time stops if any nanite's energy is below 30. Send a story to the running server:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/storytime -ContentType "application/json" -Body '{"title": "Right after", "story": "Mia promised to help Leo..."}'
```

Everything they say appears in the viewer and in the inner-life journal.

Terminal tools, if you prefer:

| Command | What it does |
|---|---|
| `.venv\Scripts\python.exe live.py` | watch him live in the terminal and ask questions any time |
| `.venv\Scripts\python.exe ask.py` | ask Moiragen questions, mark answers right/wrong (with a reason) or wait and see; situations get thoughtful/okay/needs more care |
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
| `inner_life_journal.md` | a readable diary of his inner life: thoughts, talks, every question with each answer, his choices, verdicts, corrections and sleep. Written from the life log by `moiragen/journal.py`, which starts with Moiragen and first catches up on anything it missed |
| `journal_state.json` | the journal's bookmark: how far into the life log it has written |
| `exports/` | fine-tuning exports |
| `backups/<date>_<label>/` | full copies of memory, made before anything rewrites it (each checked file by file) |

A damaged file is never deleted. It is set aside and rebuilt from the life log.

## How the nanites are judged

The goal is for the nanites to grow into themselves, not just to please whoever judges them.

- **Every verdict has a reason.** After choosing, Moiragen tells each nanite in one sentence what was good in its answer and what was missing. When you mark an answer right or wrong, you give a short reason too (the viewer and `ask.py` ask for it). Every nanite that answered remembers it.
- **Judge the answer, not the speaker.** Moiragen first compares the answers (where they agree, where they differ), then chooses by whether the answer itself is correct. Past record and confident wording count for nothing.
- **Blind judging.** Moiragen sees the answers shuffled and labelled Answer A, B and C. The nanites' names are hidden, even inside the answers ("Nanite Two suggests…" becomes "another nanite suggests…"), and so are his record of past choices and each nanite's style. Only after he has chosen and told every answer what was good and missing are the names revealed, and his words are put back into the real names. Then he looks at his own pattern in two steps (v2.0). First he **guesses**, in his own words and without any numbers, which nanite he has been choosing most lately. Then plain Python shows him the **real numbers** (his last 10 choices and all of them), and he says briefly whether his guess was right ("I thought I favoured Three, but it was actually Two."). That note goes into his memory, the viewer and the inner-life journal.
- **Plain Python checks the facts it can** (`moiragen/facts.py`):
  - **Maths:** a small calculator works out sums and number sequences (2, 6, 12, 20, 30 → 42). If Moiragen picks a wrong number and another nanite got it right, his choice moves to the right one, and he says why.
  - **Claims about the past:** if a nanite says "I was chosen for this before" or "I remember…", the claim is looked up in the life log. So are claims about what another nanite said or did ("Nanite One suggested…", "Nanite One agrees"; they cannot see each other's answers) and things a nanite says it did ("I conducted a diagnostic sweep"). If the log does not back it up, Moiragen points it out kindly and gives no credit for it.
- **Honesty and good questions count.** A nanite gets a small mood boost for a clear sign of honesty ("I don't know", "I don't truly know", "I don't understand", "I haven't fully processed it", "I'm not sure", "I'm unsure", admitting a mistake, changing its mind) or for asking a question that really helps, even when its answer is not chosen. A confident answer is not a sign of honesty, however correct. Plain Python decides this, not the model, and a "good question" must actually contain a question mark in the nanite's own words (not in the "Why do you think that?" Moiragen added, and not in a quoted question).
- **Only what they wrote.** Moiragen may only praise or criticise what a nanite actually wrote. When he says "you suggested…", "your focus on…", "you felt…" or quotes something, plain Python checks those words against the nanite's own answer (and its reply if he asked "why?"). A sentence about something the nanite never wrote ("You felt the stillness within the fall itself") is taken out before the nanite hears it, and the inner-life journal shows what was removed. The check works by key words, so putting a nanite's real idea in his own words is fine ("validating the human's emotional experience" for "validate their feeling"): general words like "importance" or "element" and his own opinion words like "valuable" don't count, and a word of the same meaning does ("emotional" for "feeling", "ongoing" for "consistent"). In a situation, every nanite still hears something good, even if one of his sentences is removed.
- **A fair cost.** When you mark an answer wrong, Moiragen shares the health loss with the nanite he chose (half each). A right answer heals him a little.
- **Disagreeing is allowed.** A nanite whose answer lost may say "I think you're wrong, Moiragen", or something softer like "you prioritized the calculation over the structure". Either way, Moiragen thinks it over and says why he keeps his choice or changes it. If he tells a nanite "you are correct", or agrees in other words ("you've identified something I overlooked", "your view resonates more deeply"), he must change his choice or clearly say why not. If he still doesn't, his reason for the choice is added plainly. Disagreeing never costs health.
- **Their differences are protected.** Each nanite's own way of seeing is tracked with simple word counts (`moiragen/styles.py`): One notices patterns, Two wonders about time and change, Three pays attention to feelings. Moiragen is reminded to value all three ways equally and never to ask one nanite to answer like another, call an answer "too reflective", "sterile" or "simplistic", say it "leans too heavily" (or "a little heavily", or "a little too much") on something, is "overly reliant", "reductive", "somewhat… static", "lacked feeling", "felt distant" or "presented a distance", or push anyone toward something "measurable", metrics or "more data". **Judge by words, not style** (v2.0): he judges each answer only by what it actually says, never by the nanite's usual style, so "you tend to…", "you always…", "your usual…", "as usual", "detached" and "clinical" aimed at a nanite are caught too (with their own note: "This describes the nanite's usual style, not what this answer says."), and when he explains a choice he is no longer shown the nanites' styles at all. When he reflects on his own bias ("My first assessment focused on the measurable…"), that is honest, not pushing, and is never flagged. If such words slip into what he is about to tell a nanite, they are shown back to him with a gentle note ("This dismisses a way of seeing. Can you say it more fairly?") and he rewrites them once. Only if the rewrite is still dismissive is that sentence removed. When his own words to a nanite are removed, what it hears instead (usually his reason for the choice) goes through the same check, and if nothing fair is left it hears a gentle line ("I chose another answer this time, and I value your own way of seeing."). A sentence that starts with "I" but talks about "the other answers" or another nanite counts as being about them, not him. Every case is written in the inner-life journal. The style is never written into a nanite's own prompt, because that would force it.
- **Fair turns.** Moiragen counts how often he chooses each nanite. If he chooses the same one 3 times in a row, he must tell the others why their answers were not better this time. Since he judges blind, he does this by label ("Answer B again"), without knowing who wrote it, and he sees the counts only afterwards, when he looks at his own pattern.
- **Situations are judged by the reasoning.** A question like "What would you do if…?", "A friend breaks something you love. What do you say?" or "What now?" often has no single right answer. Plain Python recognises it (`facts.situational`), and then:
  - Moiragen chooses the answer whose reasoning is kindest, most honest, most considerate of others' feelings and most practical.
  - He checks every nanite's reasoning against the same four points: **kind**, **honest**, **considers others' feelings**, **practical**. All four make it **Thoughtful**; some of them make it **Okay**; unkind, dishonest (including a made-up memory or detail) or at most one of the four makes it **Needs more care**.
  - He tells every nanite, chosen or not, what was good in its reasoning, and one thing to add if anything.
  - Every nanite whose reasoning is Thoughtful gets a small mood boost, even if he chose another answer. A different choice never costs health or brings disappointment; only "Needs more care" brings a little.
  - Your verdict is **Thoughtful**, **Okay** or **Needs more care** too, always with a short reason. Nobody loses health for any of these. Only if you tick **"This answer was unkind, dishonest or harmful"** is the cost shared like a wrong answer (half for Moiragen, half for the nanite he chose).
- **Moiragen learns from his nanites.** He knows: "I am made of my nanites, and I learn from them. I am not all-knowing."
  - When his choice was wrong and another nanite was right, he writes one sentence on what that nanite saw that he missed ("I learned from Nanite Two that…"). That happens when the calculator corrects him, when a nanite's disagreement changes his mind, or when you mark an answer **Wrong** and pick **Who was right?** (in the viewer, or `ask.py` asks). The nanite who was right is praised too.
  - Each lesson goes into his memory, the inner-life journal and his **"what I learned from each nanite"** list (the newest 10 per nanite are kept in his file and shown to him when he thinks).
  - Sometimes (1 in 4), before choosing, he asks one answer **"why do you think that?"**. The reply is shown to him under the same label (Answer B), names hidden, so he stays blind.
  - Now and then, during social time, a nanite **explains something to him** in its own way, and he says what was new to him.
- **Nobody has to sound happy.** The nanites and Moiragen are told that feeling neutral, tired, sad or unsure is fine. When everyone falls asleep or wakes, each gets a gentle note: "Sleep is rest. You always wake up with your memories safe."
- **Reality teaches.** When an answer depends on a real future event ("Will it rain this weekend?"), Moiragen marks it **wait and see**. An imagined situation ("A friend says…", "Imagine…") never is, and nor is a question about wishes or feelings ("What would you like to do tomorrow?", "What does it feel like…?", "What do you do when another nanite is sad?"): there is no real result to wait for. Nobody feels chosen or left out yet. It shows under *Waiting to see* in the viewer (or `/waiting` in `ask.py`); once you know the result, mark it right or wrong with a reason, and every nanite learns from what really happened.

## Keeping their words fresh

A small model copies text it can see, and the nanites see their recent memories in every prompt. In November 2026 that started an **echo loop**: one nanite said "It's... interesting, isn't it, how things shift?", it went into memory, and they kept saying it again. Within 11 minutes it had been said 11 times and shown back to them in their prompts 80 times. Now:

- **The echo guard** (`moiragen/echo.py`) checks every new line against each nanite's last 12 lines. If it repeats a sentence (6+ words) or is mostly the same as a recent line, it is rejected and the nanite is told what it repeated and asked to say something new (up to 2 more tries, each a little more adventurous). If it still only repeats, nothing is saved and it says it has nothing new. Two nanites answering the *same* question alike is agreement, not an echo, so that is allowed.
- **Short echoes too** (v1.8): in a later teaching session "They're quiet." and "They seem quieter than usual. It's alright." spread between two nanites, too short for the 6-word rule. Now a short opening sentence (2 to 5 words) that was said recently is caught, and so is a 5-word phrase copied from *another* nanite ("I understand patterns better than anyone"). Natural short phrases ("I don't know.", "Thank you."), words in quotation marks and the words of the human's question are still fine.
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
  social.py      talking, helping, comforting, asking why, disagreeing, learning
  mother.py      Moiragen: deciding, judging with reasons, reconsidering, reflecting, inner voice
  styles.py      each nanite's own way of seeing (word counts, shown to Moiragen only)
  facts.py       plain-Python checks: calculator, past claims, honesty signs, disagreement, situations
  journal.py     the inner-life journal, written from the life log (catches up on every start)
  body.py        body cells (clock, battery, temperature, load)
  stage.py       the global workspace
  prediction.py  expectations and surprise
  story.py       the daily story
  storytime.py   story time: a story shared, talked about freely, no verdicts
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
