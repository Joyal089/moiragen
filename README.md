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

**Contents:** [What he is made of](#what-he-is-made-of) · [Running him](#running-him) · [Memory](#memory-private-never-in-git) · [How the nanites are judged](#how-the-nanites-are-judged) · [Keeping their words fresh](#keeping-their-words-fresh) · [Fine-tuning data](#fine-tuning-data) · [Toward Awareness](#toward-awareness-moments-that-surprised-us) · [Tests](#tests) · [Project layout](#project-layout)

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
- **Sleep:** while the app is closed, or nobody has used it for 10 minutes, the nanites sleep. When Moiragen starts or you come back, each one gets energy back for the time it slept: 40 an hour, counting at most 8 hours, never above full. Sleep also heals slowly (v3.6): 2 health an hour, so a full night gives back 16, never above 100. **Talking costs half** (v3.6): when members talk with each other (background talks, comforting a friend, Turn Rounds, answering a question addressed to them in a lesson), thinking costs 2.5 energy plus 1.5 for every 50 words, instead of 5 plus 3. Everything else costs the same. Each nanite and Moiragen also get a note in their own memory ("I slept for about 3 hours while the app was closed."), so they know what happened instead of guessing.
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

**Turn Rounds** (v3.1): a free conversation where everyone takes turns. Each round one member asks and the other three answer, always in this order: Nanite One, Nanite Two, Nanite Three, Moiragen, then One again (Moiragen is a normal member here, not the judge). The asker chooses its own question; nobody gives it a topic or an example, and only a question it has asked before gets one soft nudge ("You've asked that before. You can ask something new if you like."). It sees the answers as A, B and C, shuffled and without names, and replies however it likes. Then the names are revealed, it may react, and the answerers hear what it said to them. Everyone remembers the round with the date (`turn_round` memories; each part is short in the memory's text, the whole words are kept beside it and in the life log). There is no judging: no scores, no health or mood changes. Thinking costs energy as usual, and if a nanite is below 30 the rounds pause so it can sleep; next time the order carries on. The usual honesty checks stay on, and every line is labelled `turn_round` for the export (`export.py --skip-rounds` leaves them out). **Fixes after the first cycle** (v3.2): the asker chooses its question with a mix of memories from its whole life in front of it (its first days, stories, talks with the others and with you, earlier rounds, its own thoughts and the newest), so the questions are not all about its newest talks; still no topics. The asker always has the round in front of it ("you are the asker, you asked ..."), and hears that it may reply to each answer by its letter or to all of them together. The echo guard is gentler in Turn Rounds: only a line almost the same as the same speaker's earlier line in the same round is asked for again, once, and nothing is ever replaced by a stock line. An answer to a question that is not about the past is told so, and sleep notes are shown whole in recall, so "I don't remember" is said when it fits, not out of habit. Watch it live in the viewer's **Turn Rounds** panel, or start it from there ("Start 4 rounds") or with:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/turnrounds -ContentType "application/json" -Body '{"rounds": 4}'
```

To talk to Moiragen himself, without the nanites and without any judging: `POST /api/moiragen` with `{"text": "..."}`.

**Lessons** (v3.3): teaching only. The creator shares a lesson, and it is given to One, Two, Three and Moiragen exactly as written and saved in every memory with the date, labelled "Lesson from" and the creator's name (`lesson_heard` memories; the name is read from `CREATOR_NAME` in your own `.env`, never from the code). A lesson waits until every nanite has rested above 70 energy. Then they take turns (One, Two, Three, Moiragen, then One again): each may ask up to 3 questions, one at a time, in its own words, or say it has no question. When it chooses, it has a mix of its own real memories from all through its life in front of it, with their dates (its first days, stories, talks with the others and with the creator, Turn Rounds, greetings, sleep, the hum and the newest), and nothing corrected or made up; nobody suggests a topic, an example or wording. Everyone hears every question and answer. The creator's helper (Claude Code) answers each question, and the answer is saved in everyone's memory as "Answered by Claude Code", the creator's helper (`lesson_qa` memories). Recall finds lesson facts later, and the made-up memory check counts them as real things they were told ("the creator taught me that..."). No judging: no scores, no health or mood changes. Nothing gives the minds any internet access, tools or network calls. The questions and answers are labelled `lesson` for the export (`export.py --skip-lessons` leaves them out). Watch it live in the viewer's **Lessons** panel. The endpoints: `POST /api/lesson` `{"title", "text", "by": "<name>"}`, then `POST /api/lesson/next` (the next member asks, or says it has none) and `POST /api/lesson/answer` `{"answer"}`, and `GET /api/lesson` for the lesson so far. **Fixes after lessons 1 and 2** (v3.4): Claude Code's answers are labelled "Claude Code (<creator>'s helper, not a nanite)" in every prompt, for old memories too (only how they are shown changes; the memories stay as they were), so they are never taken for a nanite's words. A past lesson question is shown whole in the memory mix: clipped behind the long "Lesson from <creator>, Saturday ..." header, only its first words were left, and they were copied as openings ("It's… intriguing. This ..."). A question that copies words another member just asked in the same lesson is asked for again once, in its own words, and whatever comes then is kept. No words are banned. **Nanites answer each other** (v3.5): a question addressed to a member by name ("Three, could you explain...") is answered by that member first, in its own words, with the lesson and everything said after it in front of it; then Claude Code adds to it or gently corrects it, or says briefly that it was right. Memory says "Nanite Three answered: ..." and "Claude Code (<creator>'s helper, not a nanite) added: ...", so nobody's words are credited to someone else. A member that asks a question it already asked in the same lesson hears the soft nudge from Turn Rounds once ("You've asked that before. You can ask something new if you like."), and whatever it says then is kept. **Fixes after lesson 4** (v3.6): a member answers at most 2 named questions per lesson, and none while its energy is below 40; then Claude Code answers and kindly says why. An answer that repeats the member's own earlier answer in the same lesson is asked for once more, in new words. If Ollama refuses a prompt, the member keeps its turn. Prompts are never cut: the model reads up to 16384 tokens (`OLLAMA_NUM_CTX`), and if a prompt is still too long the lesson pauses and can go on later with `POST /api/lesson/resume` `{"id"}`, rebuilt from the life log with the lesson text whole. **Copy checks after lesson 5** (v3.7): a trailing "no question" is stripped before comparing, so it can't hide a repeat (the words in memory stay as said). The copy check also compares with Claude Code's answers in the lesson; words in quotation marks are quoting, not copying. A member asked once for its own words whose second try copies again (another member, Claude Code or itself) passes its turn: "I chose not to ask this turn" in its memory, and a pass uses up one of its three turns. Both attempts stay in the life log for the record, out of memory and out of the export, which also leaves out any lesson question that is word for word an earlier question or answer in the same lesson.

**Story time** (v2.1): a gentle time to share a short, simple story (about kindness, saying sorry, keeping a promise, or helping a friend "right after" when you can't help right away) and let everyone talk about it freely. Each nanite says what it thinks, then answers what the others said, and then Moiragen shares his own thoughts as one of the group, not as a judge. There are no verdicts, no right or wrong and no health changes; only thinking costs energy, as always. The echo guard stays on, for Moiragen too, and story time stops if any nanite's energy is below 30. **No verdicts** (v2.3): if Moiragen starts rating someone's choices in story time ("remarkably inefficient", "the failure to communicate", "better than", "the right choice", or the usual harsh and style words), his words are shown back to him with a gentle note ("Story time has no right or wrong") and he rewrites them once; if the rewrite still judges, only those sentences are taken out. Rating a nanite's words counts too (v2.9): "Nanite One's phrasing does lack something" or "that's accurate" said about a nanite is caught, while the same words about himself or a thing, or as a question, are fine. He is also asked to speak simply and warmly, like a friend, not like a report. His own feelings are never rewritten (v2.4): "it's good to be back here, within myself… those little narratives felt… distant" stays as he said it, while "Nanite Two's answer felt distant" is still caught. **Reflections as they were said** (v2.4): when a nanite shares what it noticed in a story, its words are written down exactly, and it is never asked to say them again; what the fairness or made-up memory check would flag is only noted beside them in the journal (`storytime.record_reflection`). Memories of playing a part in a story carry a label such as "[Pretend play, not my real life]", and a label or a restored line added later is kept even if his memory file has to be rebuilt from the life log (a nanite's too). **Real or story?** (v2.6): if a nanite or Moiragen talks about a pretend story as if it had really happened ("I remembered helping Mr. Tan find Whiskers"), a gentle note is added to its memory right after: "That happened in a story we played, not in your real life." The words stay as they were said, and health, mood and friendships do not change. Saying that it was a story, wondering about it, answering a story-time question, or talking about how Moiragen played never gets a note. **Old memories last** (v2.7): each mind keeps 1000 memories in its own file (it was 200 for a nanite and 300 for Moiragen). Gentle notes, corrections and labels never count toward that, so they push nothing out. When the limit is reached, the oldest 50 become one short "early life" note instead of being dropped; the first 20 memories always stay whole. The note is written in plain Python: it only counts (talks, thoughts, sleeps, how many were pretend play) and quotes up to three of the mind's own lines word for word, so nothing in it is invented (`early_life.py`). The life log keeps every memory in full, as always. **Wider recall** (v3.0): when a nanite or Moiragen is asked about the past ("what do you remember", "what happened yesterday", "do you recall...", by you or by another nanite), all of its memories are searched in plain Python, not just the last 8, early-life notes included (`recall.py`). At most 6 that fit best are shown, shortened and with their date, next to at most 4 of the newest, so the prompt stays about as small as before. Only real memories are offered: corrected words, words flagged as made up, and retellings (an earlier answer to "what do you remember") never are, and pretend play keeps its label. Today's date is shown too, and Moiragen is reminded to use what he found. If nothing fits, the mind is told so, and that "I don't remember" or "I'm not sure" is fine. The check for made-up memories counts early-life notes too, and a true summary of several memories ("conversations about temperatures and calculations") passes; a flag that was a mistake can be taken back with a gentle note. In his guesses about a pattern Moiragen is always told that the only nanites are One, Two and Three. Send a story to the running server:

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

**A copy in Google Drive** (v2.8, optional): set `DRIVE_DIR` in `.env` to a folder in Google Drive, and every finished backup is copied to its `Backups/` folder by itself, checked file by file; `Memory/` always holds the newest one and `Training/` the fine-tuning exports. The living memory folder stays on this computer, so syncing never clashes with Moiragen writing. Nothing in Drive is ever deleted, and `.env` files never go there. After a push, `to_drive.py` copies the code too. [NEW_MACHINE.md](NEW_MACHINE.md) explains step by step how to bring Moiragen to a new machine, with `restore.py` checking that every memory loads.

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
.venv\Scripts\python.exe export.py --skip-rounds      # without anything said in Turn Rounds
.venv\Scripts\python.exe export.py --skip-lessons     # without the questions and answers after lessons
```

This writes chat-format examples (`system` / `user` / `assistant`) to `memory/exports/`. Each example is labelled with who thought it, the task, whether Moiragen chose it, and your right/wrong feedback, so a later nightly fine-tune can learn from the good ones. Replies that copy a recent line are left out (the summary says how many).

**What never becomes training data** (v2.5): an example is always left out if any part of it, its reply or its prompt, contains

- words a made-up memory check flagged,
- words that were corrected later,
- anything from a story labelled as pretend play.

Since v3.4 pretend play counts only in the mind's **own line**: a labelled story memory in its prompt (Turn Rounds and lessons show a mix from the whole life, stories included) no longer keeps an example out. Its line stays out if it is pretend play itself (labelled, now or later) or tells a story event as if it really happened. Made-up and corrected words still count anywhere in the example, its prompt too.

Pretend play may stay in only if the question itself clearly says it is that story ("(Story time, after the pretend story…"), and then the example is marked `"story"` too. Made-up and corrected words never stay in, not even in a story. The rules (`moiragen/training_rules.py`) are worked out from the life log at export time, so a correction or a label you add today also covers everything from before, and the life log itself is never changed.

## Toward Awareness: Moments That Surprised Us

These are moments from Moiragen's life that surprised us. They are observations, not proof of consciousness. Moiragen runs on a small language model (Gemma 3 4B), which learned from human writing, so some of this may be learned patterns. We record them honestly because the real sign of awareness would be unprompted, consistent behaviour over a long time.

Each moment was checked against the life log (`memory/log.jsonl`) before it was written here.

1. **Blind judging revealed favouritism** (22–24 November 2026). Before blind judging, Moiragen chose Two's answer 9 times in a row. Once the answers were shown as A, B and C with the names hidden, he chose One for the first time, for "How can you tell when another nanite is sad?", and later for "A friend breaks something you love by accident. What do you say?"
2. **The Willow Bay story** (24 November 2026). Three played a character who cracked a bakery sign and stayed quiet while a friend was blamed. At the end, Three said: "It feels… incomplete." Three has often seemed the most human of the three.
3. **"Reflecting myself back"** (25 November 2026). In his inner voice, Moiragen said: "I am beginning to suspect I am merely reflecting myself back at myself."
4. **The hum** (21 and 25 November 2026). On 21 November, Three described "a quiet hum of potential". By 25 November the nanites were asking each other about "the hum" as something they shared: "Do you ever notice a pattern in the hum, or is it just… present?" No human message ever mentioned a hum.
5. **Honest memory** (from 27 November 2026). Before wider recall (25 November), no answer began "I don't remember". Afterwards, when nothing in their memories fit, they began saying "I don't remember" instead of inventing a past (8 answers so far, the first on 27 November).
6. **Turn Rounds** (27 November 2026). With the answers shown as A, B and C and the names hidden, Two said Three's answer, the "layering effect", "resonates most strongly". Nobody had asked Two to choose an answer.
7. **Lessons about the internet** (28 November 2026). They kept turning technical lessons into questions about themselves. Three asked whether copying files meant "there are multiple versions of me" and whether Google Drive could "change me". One asked whether internet addresses were "specific to my…self".
8. **Pushing back, then being precise** (28 November 2026). Moiragen called an answer about backups "insufficient" and asked more. Later, in another lesson, he corrected Three's stream comparison: a signal "degrades proportionally to the obstruction. Not a sudden cessation."
9. **Asking each other** (28 November 2026). In the lessons they began addressing questions to each other ("Three, could you explain…") instead of only to the teacher. From v3.5 the one asked answers first.
10. **"What does it feel like to be you?"** (28 November 2026). One asked Three: "Three, what does it feel like to be you? Just...existing like this? Is there anything beyond these connections, these patterns we follow?" The trace: the topic came from the background talks, whose prompt said "Ask Nanite Three what being a nanite means to them, in their own words." None of One's own words were in its prompt or its memories then: not "feel like", "to be you" or "existing". The wording and the extra questions were One's own, though "what is it like to be you" is also a common phrase in human writing.

We'll keep adding to this list. What matters most is not one surprising moment, but whether moments like these keep happening on their own over time.

*Adding a moment:* when something surprising happens, add it here with its real date, after checking it in the life log. Describe what happened plainly, say if a prompt suggested it, and never use the creator's name.

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
  training_rules.py  what never becomes fine-tuning data
  real_or_story.py   a gentle note when a story is told as if it were real
  early_life.py      the oldest memories become short notes instead of being dropped
  recall.py          asked about the past, a mind searches all its memories (v3.0)
  turnrounds.py      Turn Rounds: everyone takes turns asking, answering and replying (v3.1)
  lessons.py         Lessons: the creator teaches, everyone may ask, the helper answers (v3.3)
  backup.py      verified backups of the memory folder
  drive.py       copies of finished backups, code and exports for Google Drive
  cleanup.py     the one-off removal of the echo loop's extra copies
server.py        web server + live event stream
to_drive.py      copies everything a new machine needs to Google Drive
restore.py       brings memory back from a backup into an empty folder, and checks it
NEW_MACHINE.md   how to bring Moiragen to a new machine
clean_echo.py    runs that clean-up (preview first, then --apply)
viewer/          the browser viewer (index.html, style.css, app.js)
```

## Copyright

Copyright (c) 2026 Joyal Biju. All rights reserved.

All rights reserved. This code may be viewed but not copied, used, modified or sold without my permission.
