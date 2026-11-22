// Moiragen viewer: listens to the live event stream and draws it.
//
// The server sends events over a WebSocket (see server.py). Each event has a
// "type" ("vitals", "social", "decision", ...). handleEvent() at the bottom
// decides what to draw for each type.
//
// Safety rule used everywhere: text from the minds is put on the page with
// textContent (never innerHTML), so nothing they say can run as code.

"use strict";

// ---------------------------------------------------------------------------
// Where everyone sits in the 800 x 600 drawing
// ---------------------------------------------------------------------------
const POS = {
  moiragen:     { x: 400, y: 300 },
  nanite_one:   { x: 400, y: 95 },
  nanite_two:   { x: 610, y: 425 },
  nanite_three: { x: 190, y: 425 },
};
// Where each one's speech bubble goes, so bubbles do not cover each other.
const BUBBLE_SPOT = {
  moiragen:     { dx: 0,   dy: 128, place: "below" },   // under his name, between the two lower nanites
  nanite_one:   { dx: 62,  dy: 0,   place: "right" },
  nanite_two:   { dx: 0,   dy: -52, place: "above" },
  nanite_three: { dx: 0,   dy: -52, place: "above" },
};
const BUBBLE_SECONDS = 9;
const SVG_NS = "http://www.w3.org/2000/svg";

// ---------------------------------------------------------------------------
// State kept in the page
// ---------------------------------------------------------------------------
let snapshot = null;        // latest "vitals" picture from the server
const nameToId = { Moiragen: "moiragen" };
const nodes = {};           // id -> { group, parts... }
const chats = {};           // id -> [{ who: "me" | "them", text }]
let chatTarget = null;      // id of whoever the chat panel is talking to
let currentDecision = null; // id of the decision shown in the card
let pendingAsk = null;      // the "asking the nanites…" chat message waiting for Moiragen

const $ = (id) => document.getElementById(id);

// Small helpers to build SVG and HTML elements.
function svg(tag, attrs = {}, parent) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (parent) parent.appendChild(el);
  return el;
}
function html(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
const shorten = (t, n = 180) => (t && t.length > n ? t.slice(0, n - 1) + "…" : t || "");
const idOf = (name) => nameToId[name] || null;

// ---------------------------------------------------------------------------
// Drawing the world
// ---------------------------------------------------------------------------
function buildWorld(snap) {
  const nodeLayer = $("nodes");
  nodeLayer.textContent = "";

  // Moiragen in the centre.
  const m = POS.moiragen;
  const mg = svg("g", { class: "node moiragen", tabindex: 0, role: "button",
                        "aria-label": "Talk to Moiragen" }, nodeLayer);
  svg("circle", { cx: m.x, cy: m.y, r: 78, class: "ring" }, mg);
  svg("circle", { cx: m.x, cy: m.y, r: 68, fill: "url(#core)", class: "moiragen-core body-circle" }, mg);
  const mName = svg("text", { x: m.x, y: m.y + 100, class: "name" }, mg);
  mName.textContent = "Moiragen";
  const mFeel = svg("text", { x: m.x, y: m.y + 116, class: "feel" }, mg);
  mFeel.textContent = "listening";
  nodes.moiragen = { group: mg, feel: mFeel };
  wireClick(mg, "moiragen");

  // The nanites around him.
  for (const n of snap.nanites) {
    nameToId[n.name] = n.id;
    const p = POS[n.id];
    if (!p) continue;
    const g = svg("g", { class: "node nanite", tabindex: 0, role: "button",
                         "aria-label": `Talk to ${n.name}` }, nodeLayer);
    svg("circle", { cx: p.x, cy: p.y, r: 50, class: "ring" }, g);
    const body = svg("circle", { cx: p.x, cy: p.y, r: 42, class: "body-circle" }, g);
    const name = svg("text", { x: p.x, y: p.y + 68, class: "name" }, g);
    const feel = svg("text", { x: p.x, y: p.y + 84, class: "feel" }, g);
    const bars = {};
    [["health", "var(--health)"], ["energy", "var(--energy)"], ["mood", "var(--mood)"]]
      .forEach(([stat, colour], i) => {
        const y = p.y + 94 + i * 11;
        svg("rect", { x: p.x - 45, y, width: 100, height: 6, rx: 3, class: "bar-bg" }, g);
        bars[stat] = svg("rect", { x: p.x - 45, y, width: 100, height: 6, rx: 3, fill: colour }, g);
        const label = svg("text", { x: p.x - 50, y: y + 6, class: "bar-label", "text-anchor": "end" }, g);
        label.textContent = stat[0].toUpperCase();   // H, E, M
        const tip = svg("title", {}, bars[stat]);
        bars[stat].tip = tip;
      });
    nodes[n.id] = { group: g, body, name, feel, bars };
    wireClick(g, n.id);
  }
  // Dashed links from Moiragen to each nanite.
  const links = $("links");
  links.textContent = "";
  for (const n of snap.nanites) {
    const p = POS[n.id];
    if (!p) continue;
    nodes[n.id].link = svg("line", { x1: m.x, y1: m.y, x2: p.x, y2: p.y, class: "link-line" }, links);
  }
}

function wireClick(group, id) {
  group.addEventListener("click", () => openChat(id));
  group.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openChat(id); } });
}

// Colour a nanite by mood: low mood = blue, neutral = teal, high mood = warm gold.
const moodColour = (mood) => `hsl(${Math.round(215 - mood * 1.75)}, 45%, 40%)`;

function updateWorld(snap) {
  if (!nodes.moiragen || snap.nanites.some((n) => !nodes[n.id])) buildWorld(snap);

  for (const n of snap.nanites) {
    const node = nodes[n.id];
    if (!node) continue;
    nameToId[n.name] = n.id;
    node.name.textContent = n.name;
    node.feel.textContent = n.feeling;
    node.body.setAttribute("fill", moodColour(n.mood));
    for (const stat of ["health", "energy", "mood"]) {
      node.bars[stat].setAttribute("width", Math.max(0, Math.min(100, n[stat])));
      node.bars[stat].tip.textContent = `${stat} ${Math.round(n[stat])}/100`;
    }
    node.group.classList.toggle("hurt", n.health < 60);
    node.group.classList.remove("thinking");
  }
  nodes.moiragen.group.classList.remove("thinking");

  // Friendship lines: thicker = closer friends (average of both directions).
  const layer = $("friend-lines");
  layer.textContent = "";
  const list = snap.nanites;
  for (let i = 0; i < list.length; i++) {
    for (let j = i + 1; j < list.length; j++) {
      const a = list[i], b = list[j];
      const score = ((a.friendships[b.id] ?? 50) + (b.friendships[a.id] ?? 50)) / 2;
      const pa = POS[a.id], pb = POS[b.id];
      const line = svg("line", { x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y, class: "friend-line",
                                 "stroke-width": (1 + (score / 100) * 6).toFixed(1),
                                 "stroke-opacity": (0.25 + score / 160).toFixed(2) }, layer);
      svg("title", {}, line).textContent = `${a.name} & ${b.name}: friendship ${Math.round(score)}/100`;
    }
  }
}

function setThinking(name, on = true) {
  const id = idOf(name);
  if (id && nodes[id]) nodes[id].group.classList.toggle("thinking", on);
}

function attend(name) {
  const id = idOf(name);
  Object.values(nodes).forEach((n) => n.group.classList.remove("attended"));
  if (id && nodes[id]) {
    nodes[id].group.classList.add("attended");
    clearTimeout(attend.timer);
    attend.timer = setTimeout(() => nodes[id].group.classList.remove("attended"), 6000);
  }
}

// A line that flows from one mind to another for a few seconds.
function pulse(fromName, toName, kind = "talk") {
  const a = POS[idOf(fromName)], b = POS[idOf(toName)];
  if (!a || !b || a === b) return;
  const line = svg("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: `pulse ${kind}` }, $("pulses"));
  setTimeout(() => line.remove(), 3500);
}

// A speech bubble next to whoever spoke. One bubble per speaker at a time.
const bubbleEls = {};
function bubble(name, text, kind = "") {
  const id = idOf(name);
  const p = POS[id], spot = BUBBLE_SPOT[id];
  if (!p || !text) return;
  bubbleEls[id]?.remove();
  const b = html("div", `bubble ${kind} ${id === "moiragen" ? "narrow" : ""}`);
  b.append(html("span", "who", name), document.createTextNode(shorten(text)));
  b.style.left = `${((p.x + spot.dx) / 800) * 100}%`;
  b.style.top = `${((p.y + spot.dy) / 600) * 100}%`;
  if (spot.place === "below") b.style.transform = "translate(-50%, 0)";
  if (spot.place === "right") b.style.transform = "translate(0, -50%)";
  $("bubbles").appendChild(b);
  bubbleEls[id] = b;
  setTimeout(() => b.classList.add("fade"), BUBBLE_SECONDS * 1000);
  setTimeout(() => { b.remove(); if (bubbleEls[id] === b) delete bubbleEls[id]; }, BUBBLE_SECONDS * 1000 + 700);
}

// ---------------------------------------------------------------------------
// Top bar and spotlight
// ---------------------------------------------------------------------------
function updateBody(b) {
  if (!b || !b.clock) return;
  const bar = $("bodybar");
  bar.textContent = "";
  const parts = [`${b.clock.time} · ${b.clock.part_of_day}`];
  if (b.temperature.gpu_c != null) parts.push(`GPU ${Math.round(b.temperature.gpu_c)}°C`);
  if (b.energy.battery_percent != null)
    parts.push(`battery ${b.energy.battery_percent}%${b.energy.plugged_in ? " ⚡" : ""}`);
  bar.append(document.createTextNode(parts.join(" · ") + " · "));
  const state = html("span", b.state === "fine" ? "" : b.state === "hot" ? "hot" : "warm",
                     b.state === "fine" ? "feeling fine" : b.why);
  bar.append(state);
}

function updateSpotlight(t) {
  if (!t) return;
  $("spotlight-text").textContent = `${t.source}: ${t.text}`;
  $("spotlight-text").title = `importance ${t.importance}, salience ${t.salience}`;
}

// ---------------------------------------------------------------------------
// Inner life feed
// ---------------------------------------------------------------------------
function feed(tag, text, time, extraClass = "") {
  const li = html("li");
  li.append(html("span", "time", (time || "").slice(11, 16)), html("span", `tag ${tag}`, tag));
  const body = html("span", extraClass, text);
  li.append(body);
  const list = $("feed");
  list.prepend(li);
  while (list.children.length > 150) list.lastChild.remove();
}

// ---------------------------------------------------------------------------
// Decision card
// ---------------------------------------------------------------------------
function startDecision(question) {
  currentDecision = null;
  $("decision-empty").hidden = true;
  $("decision-body").hidden = false;
  $("d-question").textContent = `“${question}”`;
  $("d-verdict").hidden = true;
  $("d-feedback-result").textContent = "";
  const box = $("d-suggestions");
  box.textContent = "";
  for (const n of (snapshot?.nanites || [])) {
    const s = html("div", "sugg waiting");
    s.dataset.nanite = n.name;
    s.append(html("div", "who", n.name), html("div", "text", "thinking…"));
    box.appendChild(s);
  }
  Object.values(nodes).forEach((n) => n.link?.classList.remove("chosen"));
}

function showSuggestion(e) {
  const card = [...$("d-suggestions").children].find((c) => c.dataset.nanite === e.nanite);
  if (!card) return;
  card.classList.remove("waiting");
  card.querySelector(".text").textContent =
    e.rested ? "(too tired, resting)" : e.quiet ? "(had nothing new to add)" : e.text;
}

// Under each suggestion: Moiragen's short reason for that nanite, and what he valued.
function showVerdict(card, v) {
  card.querySelector(".why")?.remove();
  if (!v) return;
  const box = html("div", "why");
  box.append(html("b", "", "Moiragen: "), document.createTextNode(v.why || ""));
  const badges = [];
  if (v.honest) badges.push(v.dont_know ? "honest: “I don't know”" : "honest");
  if (v.false_claims?.length) badges.push("made-up memory, corrected");
  if (v.good_question) badges.push("good question");
  if (badges.length) {
    const row = html("div");
    badges.forEach((b) => row.append(html("span", "badge", `+ ${b}`)));
    box.append(row);
  }
  card.append(box);
}

function showDecision(d) {
  if (!currentDecision && $("decision-body").hidden) startDecision(d.question);
  currentDecision = d.id;
  for (const s of d.suggestions) showSuggestion(s);
  for (const card of $("d-suggestions").children) {
    card.classList.toggle("chosen", card.dataset.nanite === d.chosen);
    if (card.classList.contains("waiting")) card.querySelector(".text").textContent = "(sat this one out)";
    showVerdict(card, (d.verdicts || {})[card.dataset.nanite]);
  }
  $("d-chosen").textContent = d.chosen || "nobody";
  $("d-reason").textContent = d.wait_and_see
    ? `${d.reason} He will wait and see if it is right (${d.check}).` : d.reason;
  $("d-answer").textContent = d.answer;
  const ch = d.changed_after;
  $("d-changed").hidden = !ch;
  if (ch) $("d-changed").textContent = `${ch.by} disagreed, and Moiragen changed his choice from ${ch.from}: ${ch.why}`;
  $("d-verdict").hidden = false;
  $("d-feedback").querySelectorAll("button").forEach((b) => (b.disabled = false));
  Object.values(nodes).forEach((n) => n.link?.classList.remove("chosen"));
  const id = idOf(d.chosen);
  if (id && nodes[id]?.link) nodes[id].link.classList.add("chosen");
}

// Send your verdict. Right and wrong need a reason the nanites can learn from;
// "wait and see" may say what to check later.
async function sendVerdict(decisionId, verdict, reasonInput, resultEl, buttons) {
  const reason = reasonInput.value.trim();
  if (verdict !== "wait" && !reason) {
    resultEl.textContent = "Please add a short reason first, so the nanites can learn from it.";
    reasonInput.focus();
    return;
  }
  buttons.forEach((b) => (b.disabled = true));
  try {
    const r = await post("/api/feedback", { decision_id: decisionId, verdict, reason });
    resultEl.textContent = `Moiragen: ${r.reply}`;
    reasonInput.value = "";
  } catch (err) {
    resultEl.textContent = `Could not send: ${err.message}`;
    buttons.forEach((b) => (b.disabled = false));
  }
}

$("d-feedback").addEventListener("click", (ev) => {
  const btn = ev.target.closest("button");
  if (!btn || !currentDecision) return;
  sendVerdict(currentDecision, btn.dataset.verdict, $("d-why"), $("d-feedback-result"),
              [...$("d-feedback").querySelectorAll("button")]);
});

// "Waiting to see": answers that can only be judged once the result is known.
function updateWaiting(list) {
  const items = list || [];
  $("waiting").hidden = !items.length;
  const box = $("waiting-list");
  const typing = box.contains(document.activeElement);   // don't wipe a reason being typed
  if (typing && box.dataset.ids === items.map((w) => w.id).join()) return;
  box.dataset.ids = items.map((w) => w.id).join();
  box.textContent = "";
  for (const w of items) {
    const item = html("div", "wait-item");
    item.append(html("div", "q", `“${w.question}”`),
                html("div", "", `${w.chosen || "Moiragen"}: ${w.answer}`),
                html("div", "check", `What to check: ${w.check || "the result"} · since ${w.time.slice(0, 10)}`));
    const row = html("div", "feedback");
    const input = html("input");
    input.placeholder = "What happened? (your reason)";
    input.maxLength = 300;
    const right = html("button", "", "Right");
    const wrong = html("button", "", "Wrong");
    const result = html("p", "muted");
    row.append(input, right, wrong);
    item.append(row, result);
    right.onclick = () => sendVerdict(w.id, "right", input, result, [right, wrong]);
    wrong.onclick = () => sendVerdict(w.id, "wrong", input, result, [right, wrong]);
    box.append(item);
  }
}

// ---------------------------------------------------------------------------
// Chat panel
// ---------------------------------------------------------------------------
function openChat(id) {
  chatTarget = id;
  $("chat").hidden = false;
  chats[id] = chats[id] || [];
  renderChat();
  $("chat-input").focus();
}

function renderChat() {
  if (!chatTarget) return;
  const isM = chatTarget === "moiragen";
  const n = snapshot?.nanites.find((x) => x.id === chatTarget);
  $("chat-title").textContent = isM ? "Moiragen" : (n?.name || chatTarget);
  $("chat-sub").textContent = isM
    ? `He asks the nanites, then decides · health ${Math.round(snapshot?.moiragen.health ?? 100)}`
    : n ? `Feeling ${n.feeling} · health ${Math.round(n.health)} · energy ${Math.round(n.energy)} · mood ${Math.round(n.mood)}` : "";
  $("chat-input").placeholder = isM ? "Ask Moiragen something…" : `Say something to ${n?.name || "them"}…`;

  // "About" section: what we know about who you are talking to.
  const about = $("chat-about-body");
  about.textContent = "";
  const addList = (title, items) => {
    if (!items || !items.length) return;
    about.append(html("b", "", title));
    const ul = html("ul");
    items.forEach((t) => ul.append(html("li", "", t)));
    about.append(ul);
  };
  if (isM && snapshot) {
    addList("What he knows about himself", snapshot.moiragen.self_knowledge.length
      ? snapshot.moiragen.self_knowledge : ["Nothing yet."]);
    addList("Recent memories", snapshot.moiragen.memories);
  } else if (n) {
    if (n.style) addList("Way of seeing", [n.style]);
    addList("Temperament", Object.entries(n.temperament).map(([k, v]) => `${k}: ${v}`));
    addList("Friendships", Object.entries(n.friendships).map(
      ([k, v]) => `${snapshot.nanites.find((x) => x.id === k)?.name || k}: ${Math.round(v)}/100`));
    addList("Lessons", n.lessons.length ? n.lessons : ["None yet."]);
    addList("Recent memories", n.memories);
  }

  const log = $("chat-log");
  log.textContent = "";
  for (const m of chats[chatTarget]) log.append(html("div", `msg ${m.who}`, m.text));
  log.scrollTop = log.scrollHeight;
}

$("chat-close").addEventListener("click", () => { $("chat").hidden = true; chatTarget = null; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("chat-close").click(); });

$("chat-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text || !chatTarget) return;
  const target = chatTarget;
  input.value = "";
  chats[target].push({ who: "me", text });
  const waiting = { who: "them wait", text: target === "moiragen" ? "asking the nanites…" : "thinking…" };
  chats[target].push(waiting);
  renderChat();
  $("chat-send").disabled = true;
  try {
    if (target === "moiragen") {
      // The answer usually arrives earlier through the live "decision" event
      // (see handleEvent); the HTTP reply comes after the nanites have reacted.
      pendingAsk = waiting;
      const d = await post("/api/ask", { text });
      fillAnswer(waiting, d);
    } else {
      const r = await post("/api/chat", { nanite_id: target, text });
      waiting.who = "them";
      waiting.text = r.reply;
    }
  } catch (err) {
    waiting.who = "them";
    waiting.text = `(could not answer: ${err.message})`;
  }
  $("chat-send").disabled = false;
  if (chatTarget === target) renderChat();
});

// Put Moiragen's decision into his chat bubble.
function fillAnswer(msg, d) {
  msg.who = "them";
  msg.text = `${d.answer}\n\n(I chose ${d.chosen}: ${d.reason})`;
  if (pendingAsk === msg) pendingAsk = null;
  $("chat-send").disabled = false;
  if (chatTarget === "moiragen") renderChat();
}

async function post(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
                               body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}

// ---------------------------------------------------------------------------
// What to do with each kind of event
// ---------------------------------------------------------------------------
const SOCIAL = {
  talk:    { pulse: "talk",    feed: null },
  help:    { pulse: "help",    feed: "help" },
  support: { pulse: "support", feed: "support" },
  ask_why: { pulse: "ask",     feed: "ask why" },
  explain: { pulse: "ask",     feed: "explains" },
  lesson:  { pulse: null,      feed: "lesson" },
  disagree:   { pulse: "ask",  feed: "disagrees" },
  reconsider: { pulse: "ask",  feed: "reconsiders" },
  rest:    { pulse: null,      feed: null },
};

function handleEvent(e) {
  switch (e.type) {
    case "vitals":
      snapshot = e;
      updateWorld(e);
      updateBody(e.body);
      updateSpotlight(e.spotlight);
      setPresence(e.active);
      updateWaiting(e.waiting);
      if (chatTarget) renderChatHeaderOnly();
      break;

    case "presence":
      setPresence(e.active);
      feed("life", e.text, e.time);
      break;

    case "body":
      updateBody(e);
      break;

    case "stage":
      updateSpotlight(e);
      attend(e.source);
      break;

    case "thinking":
      setThinking(e.who, true);
      break;

    case "question":
      startDecision(e.text);
      setThinking("Moiragen", true);
      break;

    case "suggestion":
      setThinking(e.nanite, false);
      showSuggestion(e);
      if (!e.rested && !e.quiet) { bubble(e.nanite, e.text, "suggest"); pulse(e.nanite, "Moiragen", "ask"); }
      break;

    case "decision":
      setThinking("Moiragen", false);
      showDecision(e);
      if (pendingAsk) fillAnswer(pendingAsk, e);
      bubble("Moiragen", `I chose ${e.chosen}. ${e.reason}`, "chosen");
      feed("decision", `Chose ${e.chosen} for “${e.question}”: ${e.reason}`, e.time);
      break;

    case "choice_changed":       // a nanite disagreed and Moiragen changed his mind
      if (e.id === currentDecision) showDecision(e);
      feed("decision", `Changed his choice to ${e.chosen} for “${e.question}”: ${e.reason}`, e.time);
      break;

    case "feedback":
      feed(e.verdict, e.verdict === "wait"
        ? `You will wait and see. ${e.reason ? "What to check: " + e.reason : ""}`
        : `You said the answer was ${e.verdict}. Why: ${e.reason}`, e.time);
      break;

    case "chat":
      if (e.from === "user") setThinking(e.to, true);
      else { setThinking(e.from, false); bubble(e.from, e.text); }
      break;

    case "social": {
      const s = SOCIAL[e.action] || {};
      if (e.action === "rest") break;
      if (s.pulse) pulse(e.from, e.to, s.pulse);
      const kind = e.action === "help" ? "help" : e.action === "support" ? "support" : "";
      bubble(e.from, e.action === "lesson" ? `I learned: ${e.text}` : e.text, kind);
      const toWhom = e.to && e.to !== e.from ? ` → ${e.to}` : "";
      feed(s.feed || e.action, `${e.from}${toWhom}: ${e.text}`, e.time);
      break;
    }

    case "inner":
      bubble("Moiragen", e.text, "inner");
      feed("inner", e.text, e.time);
      break;

    case "reflection":
      feed("reflection", e.reflection + (e.about_me ? `  — About me: ${e.about_me}` : ""), e.time);
      break;

    case "surprise":
      feed("surprise", e.text, e.time);
      break;

    case "story":
      feed("story", `Story of ${e.day}:\n${e.text}`, e.time, "story");
      break;

    case "error":
      feed("error", e.text, e.time);
      break;

    case "awake":
    case "asleep":
      feed("life", e.text, e.time);
      break;
  }
}

// When new vitals arrive, refresh the chat header/about without wiping a reply in progress.
function renderChatHeaderOnly() {
  const log = $("chat-log");
  const scroll = log.scrollTop;
  renderChat();
  log.scrollTop = scroll;
}

// ---------------------------------------------------------------------------
// "I'm here": while you move the mouse or type, tell Moiragen (at most once a
// minute). After 10 minutes without any sign of you the nanites rest, so
// nothing piles up while you are away; the next ping wakes them.
// ---------------------------------------------------------------------------
let lastPing = 0;
function imHere() {
  if (document.hidden) return;
  const now = Date.now();
  if (now - lastPing < 60000) return;
  lastPing = now;
  fetch("/api/active", { method: "POST" }).catch(() => {});
}
for (const kind of ["pointermove", "pointerdown", "keydown", "wheel", "touchstart"]) {
  document.addEventListener(kind, imHere, { passive: true });
}
document.addEventListener("visibilitychange", imHere);

// Show or hide the "resting while you're away" note.
function setPresence(active) {
  $("presence").hidden = active !== false;
}

// ---------------------------------------------------------------------------
// Connect to the live stream (and reconnect if the server restarts)
// ---------------------------------------------------------------------------
function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => { $("conn").classList.add("on"); $("conn").title = "connected"; };
  ws.onclose = () => {
    $("conn").classList.remove("on");
    $("conn").title = "disconnected, retrying…";
    setTimeout(connect, 2000);
  };
  ws.onmessage = (msg) => {
    try { handleEvent(JSON.parse(msg.data)); }
    catch (err) { console.error("Could not draw event", err, msg.data); }
  };
}
connect();
