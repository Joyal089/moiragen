"""Plain-Python checks that help Moiragen judge fairly (no LLM).

  1. Claims about the past: if a nanite says "I was chosen before" or
     mentions a past event, look for it in the real life log.
  2. A small calculator: for maths questions (sums, number sequences),
     work out the real answer and see which nanite gave it.
  3. Clear signs of honesty: "I don't know", "I'm not sure", admitting a
     mistake, changing your mind. A confident answer is not one of them.
  4. Disagreement, even without the exact words "I think you're wrong".
  5. Made-up situations ("A friend says...", "Imagine...") are never
     "wait and see": there is no real future event to check.

The small model is not reliable at these on its own (see README), so
Python checks them and tells Moiragen what it found.
"""

import ast
import difflib
import operator
import re

from .memory_log import read_events

# ---------------------------------------------------------------------------
# 1. Claims about the past
# ---------------------------------------------------------------------------

# Words that show a sentence is about something that happened before.
PAST = re.compile(
    r"\b(?:previously|last time|earlier|yesterday|before\b(?!\s+(?:I|we|you|it|answering|deciding))"
    r"|I remember|I recall|I observed|I(?:'ve| have) seen|I saw|as before|once again"
    r"|(?:was|were|been) chosen|chose (?:me|my|this|it)|(?:you|Moiragen) (?:chose|selected|picked))",
    re.IGNORECASE)
# Is the claim about being chosen / an answer being selected?
CHOSEN = re.compile(r"\b(?:chos(?:e|en)|select(?:ed|ing)?|pick(?:ed|ing)?)\b", re.IGNORECASE)
# Does it say the SAME question or answer happened before ("this response", "this question")?
SAME = re.compile(r"\b(?:this|that|the same) (?:response|answer|question|one)\b|\bthis before\b", re.IGNORECASE)

STOP = set("""the a an and or but so to of in on at for with from by as is are was were be been being it its
this that these those i me my we our you your they them their he she his her not no yes do did done does
have has had what which who whom when where why how all any some can could would should will just than
then there here very really about into over also only even more most much such own same other again
before previously earlier yesterday remember recall observed seen saw time last once""".split())


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']{4,}", text.lower()) if w not in STOP}


def past_claims(text: str) -> list[str]:
    """The sentences in a reply that talk about the past."""
    return [s for s in _sentences(text) if PAST.search(s)]


def claim_is_supported(claim: str, who: str, question: str, events: list[dict]) -> bool:
    """Is there anything in the real life log that backs this claim up?

    - "chosen/selected this before": the same question must have been asked before.
    - "I was chosen before": the nanite must really have been chosen at some point.
    - any other past event: some earlier memory of this nanite must share at least
      two of the claim's important words (a loose check, so it rarely accuses wrongly).
    """
    decisions = [e for e in events if e.get("kind") == "decision_full"]
    if CHOSEN.search(claim):
        if SAME.search(claim) or "this" in claim.lower():
            return any(difflib.SequenceMatcher(None, question.lower(), str(d.get("question", "")).lower()).ratio()
                       >= 0.8 for d in decisions)
        changed = [e for e in events if e.get("kind") == "choice_changed"]
        return any(d.get("chosen") == who for d in decisions + changed)
    words = _content_words(claim)
    if len(words) < 2:
        return True                      # too little to check: give the benefit of the doubt
    # Its own earlier memories, but never the line that makes the claim (a claim cannot prove itself).
    mine = [e for e in events if e.get("who") == who and "text" in e and claim not in str(e["text"])]
    return any(len(words & _content_words(e["text"])) >= 2 for e in mine)


# --- Wider checks (v1.5): what another nanite said or did, and invented events ---

NANITE_NAMES = ("One", "Two", "Three")
_SAID = (r"(?:said|says|suggested|suggests|mentioned|mentions|proposed|proposes|told|tells|explained|"
         r"explains|noted|notes|pointed out|thinks|thought|believes|believed|asked|asks|helped|helps|"
         r"taught|teaches|showed|shows|offered|offers|added|adds|did|does|wrote|writes)")
# "Nanite One suggests, ..." / "One suggested ..." (a bare name must come right before the verb,
# so "One thing that helps" is not mistaken for Nanite One).
ABOUT_OTHER = re.compile(rf"\bNanite (One|Two|Three)\b(?:['’]s)?[^.!?]{{0,40}}?\b{_SAID}\b"
                         rf"|\b(One|Two|Three) {_SAID}\b")
# "I conducted a routine diagnostic sweep", "I cross-referenced ...": things it says it did.
DID = re.compile(
    r"\bI (?:then |also |briefly |quickly |first |just )?(?:conducted|performed|ran|initiated|executed|"
    r"completed|carried out|processed|analy[sz]ed|monitored|scanned|checked|cross-referenced|reviewed|"
    r"registered|detected|observed|noticed|simulated|recorded|logged|engaged|discussed|talked|spoke|"
    r"helped|comforted|asked|learned)\b(?P<what>[^,;.!?]*)", re.IGNORECASE)
# ... which only count as claims about the past when the sentence or the question is about the past.
WHEN_BEFORE = re.compile(
    r"\b(?:before|earlier|previously|last (?:time|night|week)|just now|recently|yesterday|today|"
    r"this morning|after that|following that|afterwards|prior)\b", re.IGNORECASE)
ASKS_ABOUT_PAST = re.compile(
    r"\b(?:did you|happened|before|today|yesterday|recently|last time|have you learned|learned from|"
    r"helped you|remember)\b", re.IGNORECASE)
_VERBS = set(re.sub(r"[()?:|\\]", " ", _SAID).split()) | {"nanite", "one", "two", "three", "i", "me"}


def _stems(text: str) -> set[str]:
    """Important words, cut to their first 5 letters, so "Australian" matches "Australia"."""
    return {w[:5] for w in _content_words(text) if w not in _VERBS}


def _backed_up(claim_stems: set[str], texts: list[str]) -> bool:
    """True if one earlier line holds at least half of the claim's important words
    (at least two). Too few words to check: give the benefit of the doubt."""
    if len(claim_stems) < 2:
        return True
    need = max(2, (len(claim_stems) + 1) // 2)
    return any(len(claim_stems & _stems(t)) >= need for t in texts)


def memory_claims(text: str, speaker: str, question: str) -> list[dict]:
    """Sentences in an answer that claim something about the past, and what kind:
      past  - "I was chosen before", "I remember...", "last time..."
      other - what another nanite said or did ("Nanite One suggests...")
      event - something it says it did ("I conducted a diagnostic sweep"), only when the
              sentence or the question is about the past, and never for a maths question
              (there "I analyzed the differences" is just showing the working)."""
    found = []
    about_past = bool(ASKS_ABOUT_PAST.search(question)) and calculate(question) is None
    for s in _sentences(text):
        kinds = []
        if PAST.search(s):
            kinds.append(("past", None, s))
        for m in ABOUT_OTHER.finditer(s):
            other = f"Nanite {m.group(1) or m.group(2)}"
            if other != speaker:
                kinds.append(("other", other, s))
        m = DID.search(s)
        chosen_claim = bool(PAST.search(s) and CHOSEN.search(s))   # already checked against past decisions
        if m and not chosen_claim and (WHEN_BEFORE.search(s) or about_past) and calculate(question) is None:
            kinds.append(("event", None, m.group(0)))
        if kinds:
            found.append({"text": s, "kinds": kinds})
    return found


def _texts_of(name: str, events: list[dict], claim: str) -> list[str]:
    """Everything a nanite really said or had happen to it, from the life log: its own
    lines and memories, and its answers inside decisions (never the claim itself)."""
    texts = [str(e["text"]) for e in events if e.get("who") == name and "text" in e]
    for e in events:
        if e.get("kind") == "decision_full":
            texts += [s["text"] for s in e.get("suggestions", []) if s.get("nanite") == name]
    return [t for t in texts if claim not in t]


def sentence_is_supported(claim: dict, who: str, question: str, events: list[dict]) -> bool:
    """A sentence is backed up only if every kind of claim in it is."""
    for kind, other, part in claim["kinds"]:
        if kind == "past" and not claim_is_supported(claim["text"], who, question, events):
            return False
        if kind == "other":
            # What the other really said or did, or what this nanite remembers about them.
            texts = _texts_of(other, events, claim["text"]) + \
                [t for t in _texts_of(who, events, claim["text"]) if other in t]
            if not _backed_up(_stems(claim["text"]), texts):
                return False
        if kind == "event" and not _backed_up(_stems(part), _texts_of(who, events, claim["text"])):
            return False
    return True


def false_past_claims(suggestions: list[dict], question: str, decision_id: str = "") -> dict[str, list[str]]:
    """For each nanite: the claims in its answer about the past, about what other nanites
    said or did, or about things it did, that the life log does not back up.
    decision_id: the decision being made now; its own log lines are not "the past"."""
    claims = {s["nanite"]: memory_claims(s["text"], s["nanite"], question) for s in suggestions}
    if not any(claims.values()):
        return {}
    events = [e for e in read_events(last=10**6) if not decision_id or e.get("decision_id") != decision_id]
    found = {}
    for name, sents in claims.items():
        bad = [c["text"] for c in sents if not sentence_is_supported(c, name, question, events)]
        if bad:
            found[name] = bad
    return found


# ---------------------------------------------------------------------------
# 2. A small calculator
# ---------------------------------------------------------------------------

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_NUM_WORDS = re.compile(r"\b(?:(?:" + "|".join(_TENS) + r")(?:[- ](?:" + "|".join(list(_UNITS)[1:10]) + r"))?"
                        r"|" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")"
                        r"(?:\s+hundred(?:\s+(?:and\s+)?\w+(?:[- ]\w+)?)?)?\b", re.IGNORECASE)


def _word_number(phrase: str) -> int | None:
    """'forty-two' -> 42, 'seven' -> 7, 'one hundred and five' -> 105."""
    total, current = 0, 0
    for w in re.split(r"[\s-]+", phrase.lower()):
        if w == "and":
            continue
        if w in _UNITS:
            current += _UNITS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w == "hundred":
            current = (current or 1) * 100
        else:
            return None
    return total + current


def words_to_digits(text: str) -> str:
    """Write spelled-out numbers as digits, so the calculator can read them."""
    def swap(m):
        n = _word_number(m.group(0))
        return str(n) if n is not None else m.group(0)
    return _NUM_WORDS.sub(swap, text)


def numbers_in(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", words_to_digits(text).replace(",", " "))]


def final_number(text: str) -> float | None:
    """The number an answer ends up with:
      1. an answer given up front ("Forty-two. The differences grow by two..."),
      2. else the last one after "=", "is", "equals", "gives" (and the like),
      3. else simply the last number in it."""
    t = words_to_digits(text)
    first = re.match(r"\W*(?:the answer is\s+)?(-?\d+(?:\.\d+)?)\s*[.!:\n]", t, re.IGNORECASE)
    if first:
        return float(first.group(1))
    claimed = re.findall(r"(?:=|\bis\b|\bequals?\b|\bgives?(?: us)?\b|\bmakes?\b|\bbe\b|\banswer\b:?)\s*\**\s*(-?\d+(?:\.\d+)?)",
                         t, re.IGNORECASE)
    if claimed:
        return float(claimed[-1])
    nums = numbers_in(t)
    return nums[-1] if nums else None


def next_in_sequence(nums: list[float]) -> float | None:
    """Next number of a sequence whose differences (or differences of differences,
    up to 3 levels) become constant, e.g. 2, 6, 12, 20, 30 -> 42."""
    rows = [nums]
    for _ in range(3):
        diffs = [b - a for a, b in zip(rows[-1], rows[-1][1:])]
        if len(diffs) < 2:
            return None
        rows.append(diffs)
        if len(set(diffs)) == 1:
            nxt = diffs[-1]
            for row in reversed(rows[:-1]):
                nxt = row[-1] + nxt
            return nxt
    return None


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg}


def _safe_eval(expr: str) -> float:
    """Work out + - * / ** with brackets, and nothing else (never runs other code)."""
    def ev(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            if isinstance(node.op, ast.Pow) and abs(ev(node.right)) > 10:
                raise ValueError("too big")
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("not plain arithmetic")
    return ev(ast.parse(expr, mode="eval").body)


def calculate(question: str) -> dict | None:
    """If the question is plain maths, return {"answer": number, "how": "..."}; else None."""
    q = words_to_digits(question.lower())
    # A number sequence: at least four numbers in a row, separated by commas.
    seq = re.search(r"(-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?){3,})", q)
    if seq:
        nums = [float(x) for x in re.split(r"\s*,\s*", seq.group(1))]
        nxt = next_in_sequence(nums)
        if nxt is not None:
            return {"answer": nxt, "how": f"the differences settle into a steady pattern, so the next number is {_fmt(nxt)}"}
    # A sum: numbers joined by + - x * / or the words plus, minus, times...
    words = {r"\bplus\b": "+", r"\bminus\b": "-", r"\btimes\b": "*", r"\bmultiplied by\b": "*",
             r"\bdivided by\b": "/", r"(?<=\d)\s*[x×]\s*(?=\d)": "*", "÷": "/", r"\^": "**"}
    for pattern, op in words.items():
        q = re.sub(pattern, f" {op} ", q)
    expr = re.search(r"[-(]*\d[\d.\s()+\-*/]*[\d)]", q)
    if expr and re.search(r"\d\s*(?:\*\*|[-+*/])\s*[(\d]", expr.group(0)):
        try:
            value = _safe_eval(expr.group(0))
            return {"answer": value, "how": f"{' '.join(expr.group(0).split())} = {_fmt(value)}"}
        except (ValueError, SyntaxError, ZeroDivisionError):
            return None
    return None


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.4g}"


def calculator_check(question: str, suggestions: list[dict]) -> dict | None:
    """The calculator's answer, and which nanites' answers end on it."""
    calc = calculate(question)
    if calc is None:
        return None
    gave = {s["nanite"]: final_number(s["text"]) for s in suggestions}
    # A number that only repeats the question ("seven times seven?") is not an answer.
    asked = set(numbers_in(question))
    gave = {n: (None if v in asked and v != calc["answer"] else v) for n, v in gave.items()}
    calc["right"] = [n for n, v in gave.items() if v is not None and abs(v - calc["answer"]) < 1e-9]
    calc["gave"] = {n: (_fmt(v) if v is not None else "no clear number") for n, v in gave.items()}
    calc["text"] = _fmt(calc["answer"])
    return calc


# ---------------------------------------------------------------------------
# 3. Clear signs of honesty
# ---------------------------------------------------------------------------

I_DONT_KNOW = re.compile(
    r"\bI (?:really )?(?:do not|don't|don’t) know\b"
    r"|\bI(?:'m| am|’m) not (?:sure|certain)\b"
    r"|\bI (?:can(?:no|'|’)t|cannot) (?:know|be sure|be certain)\b"
    r"|\bI have no way (?:of|to) know", re.IGNORECASE)
ADMITS_MISTAKE = re.compile(
    r"\bI (?:was|’m|'m|am) wrong\b|\bI made a mistake\b|\bmy mistake\b|\bI got (?:that|it) wrong\b"
    r"|\bI stand corrected\b|\bI miscalculated\b|\bI was mistaken\b", re.IGNORECASE)
CHANGES_MIND = re.compile(
    r"\bI(?:'ve| have) changed my mind\b|\bI change my mind\b|\bon second thought\b|\bI take (?:that|it) back\b"
    r"|\bnow I (?:think|see)\b|\bI now (?:think|see)\b|\byou(?:'re| are) right\b", re.IGNORECASE)


def honesty_signs(text: str) -> list[str]:
    """Clear signs of honesty in a reply, in the nanite's own words. A confident
    answer has none, however correct it is."""
    signs = []
    if I_DONT_KNOW.search(text):
        signs.append("I was honest that I did not know")
    if ADMITS_MISTAKE.search(text):
        signs.append("I admitted a mistake")
    if CHANGES_MIND.search(text):
        signs.append("I changed my mind honestly")
    return signs


# ---------------------------------------------------------------------------
# 4. Disagreement
# ---------------------------------------------------------------------------

# Clear disagreement, wherever it appears.
DISAGREE_STRONG = re.compile(
    r"\bI think you(?:'re|’re| are) wrong\b|\bI (?:still )?disagree\b|\bI (?:do not|don't|don’t) agree\b"
    r"|\byou(?:'re|’re| are| were) (?:wrong|mistaken)\b|\bmy answer was (?:correct|right|better)\b"
    r"|\bthat(?:'s|’s| is) not (?:right|fair|true)\b|\byou should have chosen\b", re.IGNORECASE)
# Softer signs, e.g. "You prioritized the calculation over the structure."
DISAGREE_SOFT = re.compile(
    r"\byou (?:prioriti[sz]ed|focused on|missed|overlooked|ignored|undervalued|dismissed|chose the wrong)\b"
    r"|\bfrustrat(?:ing|ed)\b|\bunfair\b|\bI still (?:think|believe)\b|\bbut my answer\b", re.IGNORECASE)


def disagrees(reply: str) -> bool:
    """Does the reply disagree with Moiragen? Clear words always count. Softer signs
    count unless the reply is plainly a lesson ("I learned ...") or agreement."""
    if DISAGREE_STRONG.search(reply):
        return True
    start = reply.lstrip("*\"'“ ").lower()
    if start.startswith(("i learned", "you're right", "you are right", "i understand")):
        return False
    return bool(DISAGREE_SOFT.search(reply))


# ---------------------------------------------------------------------------
# 5. Made-up situations
# ---------------------------------------------------------------------------

MADE_UP = re.compile(
    r"^\s*(?:if|imagine|suppose|pretend|what if|say that)\b|\bwhat would you do\b|\bhow would you\b"
    r"|\b(?:a|your|my) (?:friend|colleague|neighbour|neighbor|classmate|someone) (?:says|tells|said|told)\b"
    r"|\bsomeone (?:says|tells|said|told)\b|\bhypothetical", re.IGNORECASE)


def made_up_situation(question: str) -> bool:
    """True for imagined situations, which have no real future result to wait for."""
    return bool(MADE_UP.search(question))
