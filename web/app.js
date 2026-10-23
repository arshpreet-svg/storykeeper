const SHELF = {
  story:  { name: "Stories",          blurb: "The life, chapter by chapter", color: "var(--story)" },
  recipe: { name: "Kitchen",          blurb: "Dishes nobody wrote down, until now", color: "var(--recipe)" },
  health: { name: "Health",           blurb: "What runs in the family, for the doctors", color: "var(--health)" },
  vault:  { name: "Where things are", blurb: "Papers, keys and lockers: locations only, never numbers", color: "var(--vault)" },
  wisdom: { name: "Wisdom & people",  blurb: "Advice, and the people to trust", color: "var(--wisdom)" },
};
const HISTORY = [[1947, "Partition"], [1971, "'71 war"], [1991, "Liberalisation"], [2020, "Pandemic"]];
const NOW = new Date().getFullYear();

const state = { elders: [], elder: null, shelf: "story", memories: [], selected: null, mode: "interview", fresh: null };
const $ = (s) => document.querySelector(s);
const animate = (el) => { el.dataset.anim = "1"; clearTimeout(el._a); el._a = setTimeout(() => delete el.dataset.anim, 2500); };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) } : {});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

// ------------------------------------------------------------ data

async function refreshStatus() {
  const s = await api("/api/status");
  const el = $("#engine");
  el.className = "engine " + (s.engine === "bedrock" ? "live" : "offline");
  $("#engineText").textContent = s.engine === "bedrock" ? `Amazon Nova on Amazon Bedrock · ${s.region}` : "Offline mode (no Bedrock)";
  el.title = s.last_error || s.model;
}

async function loadFamily(keepElder = true) {
  const { elders } = await api("/api/family");
  state.elders = elders;
  if (!keepElder || !state.elder) state.elder = elders[0]?.name;
  renderElders();
  await loadMemories();
}

async function loadMemories() {
  const { memories } = await api(`/api/memories?elder=${encodeURIComponent(state.elder)}`);
  state.memories = memories;
  animate($("#ribbon"));
  animate($("#entries"));
  renderRibbon();
  renderBookmarks();
  renderEntries();
  renderReader();
  loadGaps();
}

// ------------------------------------------------------------ gap engine

async function loadGaps() {
  const { gaps } = await api(`/api/gaps?elder=${encodeURIComponent(state.elder)}`);
  animate($("#gaps"));
  $("#gaps").innerHTML = gaps.length ? gaps.slice(0, 5).map((g, i) => `
    <li class="gap" style="--c:${SHELF[g.shelf].color};--i:${i}">
      <span class="gap-score" style="--s:${g.score}"><b>${g.score}</b></span>
      <span class="gap-body">
        <span class="gap-kind">${esc(g.kind)} · ${SHELF[g.shelf].name}</span>
        <span class="gap-q">“${esc(g.question)}”</span>
        <span class="gap-why">${esc(g.why)}</span>
      </span>
      <button class="gap-ask" data-gap="${esc(g.key)}">Ask ${esc(state.elder)}</button>
    </li>`).join("")
    : `<li class="gap done">Nothing urgent is missing for ${esc(state.elder)}. Every shelf and chapter has something.</li>`;
}

$("#gaps").addEventListener("click", (ev) => {
  const b = ev.target.closest(".gap-ask");
  if (!b) return;
  if (state.mode !== "interview") document.querySelector('.mode[data-mode="interview"]').click();
  if (!dock.classList.contains("open")) { dock.classList.add("open"); $("#convo").innerHTML = ""; }
  askNextQuestion(b.dataset.gap);
});

// ------------------------------------------------------------ elders

function coverageGradient(shelves) {
  const keys = Object.keys(SHELF);
  const seg = 360 / keys.length;
  return "conic-gradient(" + keys.map((k, i) => {
    const c = shelves[k] ? SHELF[k].color : "var(--rule)";
    return `${c} ${i * seg + 2}deg ${(i + 1) * seg - 2}deg, transparent ${(i + 1) * seg - 2}deg ${(i + 1) * seg + 2}deg`;
  }).join(", ") + ")";
}

function renderElders() {
  $("#elders").innerHTML = state.elders.map((e, i) => `
    <button class="elder ${e.name === state.elder ? "active" : ""}" data-elder="${esc(e.name)}" style="--i:${i}">
      <span class="coverage" data-initial="${esc((e.full_name || e.name)[0])}" style="background:${coverageGradient(e.shelves)}"></span>
      <span>
        <h3>${esc(e.name)}</h3>
        <span class="meta">${esc(e.full_name)} · b. ${e.born_year}, ${esc(e.birthplace)}</span>
        <span class="shelf-pips">${Object.entries(SHELF).map(([k, s], j) =>
          `<span class="pip ${e.shelves[k] ? "" : "missing"}" style="color:${s.color};--j:${j}" title="${e.shelves[k] ? e.shelves[k] + " saved" : "Nothing yet. Storykeeper will ask"}">${s.name.split(" ")[0]} ${e.shelves[k] || "·"}</span>`).join("")}
        </span>
      </span>
    </button>`).join("");
}

$("#elders").addEventListener("click", (ev) => {
  const b = ev.target.closest(".elder");
  if (!b) return;
  state.elder = b.dataset.elder;
  state.selected = null;
  renderElders();
  loadMemories();
  if (state.mode === "interview") resetConvo();
});

// ------------------------------------------------------------ life ribbon

function renderRibbon() {
  const elder = state.elders.find((e) => e.name === state.elder);
  const start = Math.floor(Math.min(elder?.born_year ?? 1940, ...state.elders.map((e) => e.born_year)) / 10) * 10;
  const span = NOW + 2 - start;
  const x = (y) => ((y - start) / span) * 100;
  const dated = state.memories.filter((m) => m.year).sort((a, b) => a.year - b.year);
  // stack labels into lanes so neighbouring years don't collide
  const laneEnd = [-99, -99, -99, -99];
  const dots = dated.map((m, i) => {
    const px = x(m.year);
    const anchor = px > 85 ? "end" : "start";
    // a label takes ~15% of the width, to the right of its dot or (near the end) to the left
    const from = anchor === "end" ? px - 15 : px;
    let lane = laneEnd.findIndex((end) => from > end);
    if (lane === -1) lane = laneEnd.indexOf(Math.min(...laneEnd));
    laneEnd[lane] = anchor === "end" ? px : px + 15;
    return `<button class="mem-dot ${m.id === state.selected ? "active" : ""} ${m.conflicts?.length ? "disputed" : ""}" data-id="${m.id}" style="left:${px}%;background:${SHELF[m.shelf].color};--c:${SHELF[m.shelf].color};--i:${i}" title="${m.year} · ${esc(m.title)}${m.conflicts?.length ? " · two versions" : ""}"></button>
      <span class="mem-flag lane${lane} ${anchor}" style="left:${px}%;--c:${SHELF[m.shelf].color};--i:${i}">${esc(shortTitle(m.title))}</span>`;
  }).join("");
  const ticks = [];
  for (let y = start; y <= NOW; y += 10) ticks.push(`<span class="tick" style="left:${x(y)}%;--i:${ticks.length}">${y}</span>`);
  const hist = HISTORY.filter(([y]) => y >= start).map(([y, t]) => `<span class="history" style="left:${x(y)}%">${t}</span>`).join("");
  const life = elder ? `<span class="ribbon-life" style="left:${x(elder.born_year)}%;right:${100 - x(NOW)}%"></span>` : "";
  $("#ribbon").innerHTML = `<div class="ribbon-inner"><span class="ribbon-line"></span>${life}${ticks.join("")}${hist}${dots}</div>`;
}
const shortTitle = (t) => (t.length > 21 ? t.slice(0, 19) + "…" : t);

$("#ribbon").addEventListener("click", (ev) => {
  const d = ev.target.closest(".mem-dot");
  if (d) openMemory(+d.dataset.id);
});

// ------------------------------------------------------------ book

function renderBookmarks() {
  $("#bookmarks").innerHTML = Object.entries(SHELF).map(([k, s]) => {
    const n = state.memories.filter((m) => m.shelf === k).length;
    return `<button class="bookmark ${k === state.shelf ? "active" : ""}" data-shelf="${k}" style="--c:${s.color}"><span class="n">${n}</span>${s.name.split(" ")[0]}</button>`;
  }).join("");
}

$("#bookmarks").addEventListener("click", (ev) => {
  const b = ev.target.closest(".bookmark");
  if (!b) return;
  state.shelf = b.dataset.shelf;
  state.selected = null;
  animate($("#entries"));
  renderBookmarks();
  renderEntries();
  renderReader();
});

function renderEntries() {
  const s = SHELF[state.shelf];
  $("#shelfTitle").textContent = s.name;
  $("#shelfTitle").style.color = s.color;
  $("#shelfBlurb").textContent = s.blurb;
  const list = state.memories.filter((m) => m.shelf === state.shelf);
  if (!state.selected && list.length) state.selected = list[0].id;
  $("#entries").innerHTML = list.length ? list.map((m, i) => `
    <li><button class="entry ${m.id === state.selected ? "active" : ""} ${m.id === state.fresh ? "fresh" : ""}" data-id="${m.id}" style="--c:${s.color};--i:${i}">
      <span class="yr">${m.year ?? "·"}</span>
      <span><span class="t">${esc(m.title)}</span><span class="who">${esc(m.place || "")}</span></span>
    </button></li>`).join("")
    : `<li class="empty-shelf">Nothing on this shelf yet. Storykeeper will ask ${esc(state.elder)} about it soon.</li>`;
}

$("#entries").addEventListener("click", (ev) => {
  const b = ev.target.closest(".entry");
  if (b) openMemory(+b.dataset.id);
});

async function openMemory(id) {
  let m = state.memories.find((x) => x.id === id);
  if (!m) {
    // a source from another elder: switch to them first
    const { memories } = await api("/api/memories");
    m = memories.find((x) => x.id === id);
    if (!m) return;
    state.elder = m.elder;
    renderElders();
    await loadMemories();
  }
  state.shelf = m.shelf;
  state.selected = id;
  renderBookmarks();
  renderEntries();
  renderReader();
  renderRibbon();
  if (innerWidth < 760) $("#reader").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderReader() {
  const m = state.memories.find((x) => x.id === state.selected && x.shelf === state.shelf);
  if (!m) {
    $("#reader").innerHTML = `<div class="empty-reader"><p class="script">Pick a memory from the left page.</p></div>`;
    return;
  }
  const s = SHELF[m.shelf];
  const d = m.details || {};
  const facts = [];
  if (d.ingredients?.length) facts.push(["Ingredients", `<ul>${d.ingredients.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`]);
  if (d.steps?.length) facts.push(["Method", `<ol>${d.steps.map((i) => `<li>${esc(i)}</li>`).join("")}</ol>`]);
  if (d.condition) facts.push(["Condition", esc(d.condition) + (d.onset_age ? ` · since age ${d.onset_age}` : "")]);
  if (d.medicines?.length) facts.push(["Medicines", d.medicines.map(esc).join("<br>")]);
  if (d.item) facts.push(["What", esc(d.item)]);
  if (d.location) facts.push(["Where", esc(d.location)]);
  if (d.contact) facts.push(["Who to call", esc(d.contact)]);
  if (m.people?.length) facts.push(["People", m.people.map(esc).join(", ")]);
  if (d.quantities) facts.push(["Quantities", esc(d.quantities)]);
  const prov = m.provenance?.fields || {};
  const FIELD = { Ingredients: "ingredients", Method: "steps", Condition: "condition", Medicines: "medicines", What: "item", Where: "location", "Who to call": "contact" };
  const tag = (k) => {
    const f = prov[FIELD[k]];
    return f ? `<span class="prov ${f}" title="${f === "said" ? "In their own words" : "Worked out by the AI from what they said. Worth double-checking"}">${f === "said" ? "in their words" : "inferred"}</span>` : "";
  };
  const when = new Date(m.created_at * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  const via = { alexa: "via Alexa", web: "via the family app", seed: "demo recording" }[m.provenance?.source] || "";
  const yearTag = prov.year ? ` <span class="prov ${prov.year}" title="${prov.year === "said" ? "They said the year" : "Dated from age clues"}">${prov.year === "said" ? "said" : "inferred"}</span>` : "";
  const versions = (m.conflicts || []).map((c) => {
    const other = c.versions.find((v) => v.id !== m.id);
    const mine = c.versions.find((v) => v.id === m.id);
    return `<div class="versions"><b>Two versions</b>
      <span>${esc(mine.elder)} remembers <strong>${mine.value}</strong>.</span>
      <span>${esc(other.elder)} remembers <strong>${other.value}</strong>. <a href="#" data-open="${other.id}">Read ${esc(other.elder)}'s version →</a></span>
      <small>Storykeeper keeps both until the family settles it. It never picks one.</small></div>`;
  }).join("");
  const original = m.translation
    ? `<blockquote class="own-words" lang="pa">"${esc(m.transcript)}"<cite>— ${esc(m.elder)}, in ${esc(m.language)}</cite></blockquote>
       <p class="translation"><span>English</span>${esc(m.translation)}</p>`
    : `<blockquote class="own-words">"${esc(m.transcript)}"<cite>— ${esc(m.elder)}, told to Alexa</cite></blockquote>`;
  const words = m.summary.split(/(\s+)/).map((w, i) => (w.trim() ? `<span class="w">${esc(w)}</span>` : w)).join("");
  $("#reader").innerHTML = `<div class="reader turning" style="--c:${s.color}">
    <div class="reader-kicker">${s.name} · ${esc(m.elder)}${m.year ? " · " + m.year : ""}${m.place ? " · " + esc(m.place) : ""}</div>
    <h3>${esc(m.title)}</h3>
    <p class="provenance">Told by <b>${esc(m.elder)}</b> · recorded ${when}${via ? " · " + via : ""}${m.year ? ` · year${yearTag}` : ""}</p>
    ${versions}
    <p class="summary">${words}</p>
    ${original}
    ${facts.length ? `<dl class="facts">${facts.map(([k, v]) => `<div class="fact"><dt>${k} ${tag(k)}</dt><dd>${v}</dd></div>`).join("")}</dl>` : ""}
    ${m.redacted ? `<p class="redacted-note">🔒 Numbers and passwords were removed before saving.</p>` : ""}
    ${mediaHtml(m)}
    <div class="reader-actions">
      <button class="listen" data-say="${esc(m.summary)}" title="Text-to-speech narrator, not their voice">▶ Listen (narrator)</button>
      <button class="ghost" data-act="photo">＋ Photo</button>
      <button class="ghost" data-act="voice">🎙 Record their voice</button>
      <button class="ghost" data-act="suggest">✎ Suggest a correction</button>
    </div>
    ${suggestionsHtml(m)}
  </div>`;
}

$("#reader").addEventListener("click", (ev) => {
  const a = ev.target.closest("[data-open]");
  if (a) { ev.preventDefault(); openMemory(+a.dataset.open); return; }
  const act = ev.target.closest("[data-act]");
  if (act) { readerAction(act); return; }
  const b = ev.target.closest(".listen");
  if (!b) return;
  const spans = [...$("#reader").querySelectorAll(".summary .w")];
  const starts = [];
  let pos = 0;
  for (const sp of spans) { pos = b.dataset.say.indexOf(sp.textContent, pos); starts.push(pos); pos += sp.textContent.length; }
  b.classList.add("playing");
  b.innerHTML = `<span class="eq"><i></i><i></i><i></i></span>Reading…`;
  speak(b.dataset.say, (ci) => {
    let k = starts.findLastIndex((st) => st <= ci);
    spans.forEach((sp, n) => sp.classList.toggle("word-on", n === k));
  }).then(() => {
    spans.forEach((sp) => sp.classList.remove("word-on"));
    b.classList.remove("playing");
    b.textContent = "▶ Listen";
  });
});

// ------------------------------------------------------------ handbook

$(".hb-grid").addEventListener("click", async (ev) => {
  const b = ev.target.closest(".hb");
  if (!b) return;
  b.classList.add("loading");
  const section = b.dataset.section;
  const elder = section === "memoir" ? state.elder : "";
  try {
    const r = await api(`/api/handbook?section=${section}&elder=${encodeURIComponent(elder)}`);
    $("#hbBody").innerHTML = markdown(r.markdown) +
      `<p class="stamp">Compiled by Storykeeper from ${r.memory_count} recorded memories · ${new Date().toLocaleDateString()}</p>`;
    $("#hbDialog").showModal();
  } catch (e) {
    alertBubble(e.message);
  } finally {
    b.classList.remove("loading");
    refreshStatus();
  }
});
$("#hbClose").onclick = () => $("#hbDialog").close();
$("#hbPrint").onclick = () => window.print();

function markdown(md) {
  const out = [];
  let list = null;
  const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\*(.+?)\*/g, "<i>$1</i>");
  const close = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const raw of md.split("\n")) {
    const line = raw.trimEnd();
    let m;
    if ((m = line.match(/^(#{1,3})\s+(.*)/))) { close(); out.push(`<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`); }
    else if ((m = line.match(/^\s*[-*]\s+(.*)/))) { if (list !== "ul") { close(); out.push("<ul>"); list = "ul"; } out.push(`<li>${inline(m[1])}</li>`); }
    else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== "ol") { close(); out.push("<ol>"); list = "ol"; } out.push(`<li>${inline(m[1])}</li>`); }
    else if (!line.trim()) close();
    else { close(); out.push(`<p>${inline(line)}</p>`); }
  }
  close();
  return out.join("");
}

// ------------------------------------------------------------ Alexa simulator

const dock = $("#alexa");
const setRing = (s) => (dock.dataset.state = s);

function bubble(cls, html) {
  const div = document.createElement("div");
  div.className = "bubble " + cls;
  div.innerHTML = html;
  $("#convo").appendChild(div);
  $("#convo").scrollTop = $("#convo").scrollHeight;
  return div;
}
const alertBubble = (msg) => bubble("sys", esc(msg));

// Novelty macOS voices that would ruin the mood
const NOVELTY = /^(Albert|Bad News|Bahh|Bells|Boing|Bubbles|Cellos|Fred|Good News|Jester|Junior|Kathy|Organ|Ralph|Superstar|Trinoids|Whisper|Wobble|Zarvox)/;
const PREFERRED = ["Google US English", "Google UK English Female", "Google UK English Male", "Samantha", "Daniel", "Moira"];
let narrator = null;
try { narrator = localStorage.getItem("sk-voice"); } catch {}

function englishVoices() {
  const vs = speechSynthesis.getVoices().filter((v) => v.lang.startsWith("en") && !NOVELTY.test(v.name));
  const rank = (v) => { const i = PREFERRED.indexOf(v.name); return i === -1 ? 99 : i; };
  return vs.sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
}

function currentVoice() {
  const vs = englishVoices();
  return vs.find((v) => v.name === narrator) || vs[0] || null;
}

function fillVoices() {
  const sel = $("#voiceSelect");
  if (!sel || !("speechSynthesis" in window)) return;
  const cur = currentVoice();
  sel.innerHTML = englishVoices().map((v) =>
    `<option value="${esc(v.name)}" ${v === cur ? "selected" : ""}>${esc(v.name.replace(/ \(English \((.+)\)\)/, " · $1"))}${v.localService ? "" : " ✦"}</option>`).join("");
}

function speak(text, onWord) {
  if (!("speechSynthesis" in window)) return Promise.resolve();
  speechSynthesis.cancel();
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    u.voice = currentVoice();
    u.rate = /Grandma|Grandpa/.test(u.voice?.name || "") ? 0.9 : 0.96;
    u.pitch = 1;
    u.onstart = () => setRing("speaking");
    if (onWord) u.onboundary = (e) => e.name === "word" && onWord(e.charIndex);
    u.onend = u.onerror = () => { setRing("idle"); resolve(); };
    speechSynthesis.speak(u);
  });
}

let typingEl = null;
function showTyping() { hideTyping(); typingEl = bubble("alexa-says", `<span class="typing"><i></i><i></i><i></i></span>`); }
function hideTyping() { typingEl?.remove(); typingEl = null; }

async function alexaSays(text, extra = "") {
  hideTyping();
  bubble("alexa-says", `<span class="tag">STORYKEEPER</span>${esc(text)}${extra}`);
  await speak(text);
}

async function askNextQuestion(gap) {
  setRing("thinking");
  showTyping();
  try {
    const q = await api("/api/next", { elder: state.elder, gap });
    hideTyping();
    bubble("sys", `gap${q.score != null ? ` · score ${q.score}` : ""}: ${esc(q.gap)}`);
    await alexaSays(q.say, `<button class="skip" type="button">Skip this one</button>`);
    loadGaps();
  } catch (e) { hideTyping(); alertBubble(e.message); setRing("idle"); }
}

function resetConvo() {
  $("#convo").innerHTML = "";
  if (state.mode === "interview") {
    bubble("sys", `Interviewing ${esc(state.elder)}. Answer in any language mix (English, Punjabi, Hindi); Storykeeper files it on the right shelf. Skip anything.`);
    if (dock.classList.contains("open")) askNextQuestion();
  } else {
    bubble("sys", `Ask anything: "How does Nani make mango pickle?" · "Does diabetes run in our family?" · "Where are the house papers?"`);
  }
}

async function handleUtterance(text) {
  text = text.trim();
  if (!text) return;
  document.querySelectorAll("#convo .skip").forEach((b) => b.remove());
  bubble("user-says", esc(text));
  setRing("thinking");
  showTyping();
  try {
    if (state.mode === "interview") {
      const r = await api("/api/save", { elder: state.elder, text });
      state.fresh = r.memory.id;
      const kept = await attachPending(r.memory.id);
      if (kept.length) r.say += ` I've kept ${kept.join(" and ")} with it.`;
      await loadFamily();
      loadGraph();
      openMemory(r.memory.id);
      refreshStatus();
      await alexaSays(r.say, `<span class="src">Saved to ${SHELF[r.memory.shelf].name}: “${esc(r.memory.title)}”</span>`);
      await askNextQuestion();
    } else {
      const r = await api("/api/ask", { question: text });
      refreshStatus();
      const src = r.sources.map((s) => `<a href="#" data-open="${s.id}">${esc(s.elder)} · ${esc(s.title)}</a>`).join(" · ");
      await alexaSays(r.say, src ? `<span class="src">From: ${src}</span>` : "");
    }
  } catch (e) { hideTyping(); alertBubble(e.message); setRing("idle"); }
}

$("#convo").addEventListener("click", (ev) => {
  const sk = ev.target.closest(".skip");
  if (sk) {
    sk.remove();
    speechSynthesis?.cancel();
    bubble("user-says", "Skip");
    askNextQuestion();
    return;
  }
  const a = ev.target.closest("[data-open]");
  if (a) { ev.preventDefault(); openMemory(+a.dataset.open); }
});

$("#sayForm").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const v = $("#sayInput").value;
  $("#sayInput").value = "";
  handleUtterance(v);
});

document.querySelectorAll(".mode").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".mode").forEach((x) => x.classList.toggle("active", x === b));
  state.mode = b.dataset.mode;
  resetConvo();
}));

$("#alexaClose").onclick = () => { dock.classList.remove("open"); speechSynthesis?.cancel(); setRing("idle"); };

$("#ring").addEventListener("click", () => {
  if (!dock.classList.contains("open")) {
    dock.classList.add("open");
    resetConvo();
  }
  $("#sayInput").focus();
});

// ------------------------------------------------------------ boot

refreshStatus();
animate($("#elders"));
loadFamily(false);
if ("speechSynthesis" in window) { speechSynthesis.onvoiceschanged = fillVoices; fillVoices(); }
$("#voiceSelect")?.addEventListener("change", (e) => {
  narrator = e.target.value;
  try { localStorage.setItem("sk-voice", narrator); } catch {}
  speak("Hello, I'm Storykeeper. I'll keep your family's stories safe.");
});
$("#voiceTry")?.addEventListener("click", () => speak("Nanaji, what was the street like where you grew up in Lyallpur?"));

$("#heroStart").addEventListener("click", () => $("#ring").click());


// ------------------------------------------------------------ photos and their real voice

function mediaHtml(m) {
  if (!m.media?.length) return "";
  return `<div class="media">${m.media.map((x) => x.kind === "photo"
    ? `<figure class="photo"><img src="/media/${esc(x.file)}" alt="${esc(x.caption || "Family photo")}" loading="lazy"><figcaption>${esc(x.caption || "")}${x.added_by ? ` · added by ${esc(x.added_by)}` : ""}</figcaption></figure>`
    : `<div class="voice"><span class="voice-label">🎙 ${esc(m.elder)}'s own voice</span><audio controls preload="none" src="/media/${esc(x.file)}"></audio></div>`).join("")}</div>`;
}

const fileToB64 = (blob) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(blob); });

async function uploadMedia(memoryId, blob, caption = "", addedBy = "") {
  return api("/api/media", { memory_id: memoryId, data: await fileToB64(blob), caption, added_by: addedBy });
}

function pickFile(accept) {
  return new Promise((resolve) => {
    const inp = Object.assign(document.createElement("input"), { type: "file", accept });
    inp.onchange = () => resolve(inp.files[0] || null);
    inp.click();
  });
}

// One shared recorder for the reader button and the Alexa dock.
const recorder = { rec: null, chunks: [], blob: null };
async function startRecording(onStop) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  recorder.chunks = [];
  recorder.rec = new MediaRecorder(stream);
  recorder.rec.ondataavailable = (e) => e.data.size && recorder.chunks.push(e.data);
  recorder.rec.onstop = () => {
    stream.getTracks().forEach((t) => t.stop());
    recorder.blob = new Blob(recorder.chunks, { type: recorder.rec.mimeType || "audio/webm" });
    recorder.rec = null;
    onStop(recorder.blob);
  };
  recorder.rec.start();
}
const stopRecording = () => recorder.rec?.stop();

async function refreshCurrent(id) {
  await loadMemories();
  loadGraph();
  state.selected = id;
  renderReader();
}

// ------------------------------------------------------------ relatives suggest, the elder approves

const FIELDS = { year: "Year", place: "Place", title: "Title", people: "People", summary: "Summary" };

function suggestionsHtml(m) {
  const list = m.suggestions || [];
  if (!list.length) return "";
  return `<div class="suggestions"><b>Suggested corrections</b>${list.map((s) => `
    <div class="sug ${s.status}">
      <span><strong>${esc(s.author)}</strong> suggests ${FIELDS[s.field]?.toLowerCase() || esc(s.field)}
        <del>${esc(s.old_value ?? "—")}</del> → <ins>${esc(s.new_value)}</ins>${s.reason ? `<small>“${esc(s.reason)}”</small>` : ""}</span>
      ${s.status === "pending"
        ? `<span class="sug-btns"><button data-decide="${s.id}" data-ok="1">Approve as ${esc(m.elder)}</button><button data-decide="${s.id}" data-ok="0">Decline</button></span>`
        : `<span class="sug-status">${s.status === "approved" ? "✓ approved" : "✕ declined"} by ${esc(s.decided_by)}</span>`}
    </div>`).join("")}<small class="sug-note">${esc(m.elder)}'s original words above are never edited. Every change is kept here.</small></div>`;
}

function suggestForm(m) {
  const box = document.createElement("form");
  box.className = "sug-form";
  box.innerHTML = `<b>Suggest a correction</b>
    <label>Your name <input name="author" required placeholder="e.g. Simran (granddaughter)"></label>
    <label>What <select name="field">${Object.entries(FIELDS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
    <label>Should be <input name="value" required></label>
    <label>Why <input name="reason" placeholder="e.g. the wedding card says 1970"></label>
    <span class="sug-btns"><button type="submit">Send to ${esc(m.elder)}</button><button type="button" data-cancel>Cancel</button></span>`;
  box.querySelector("[data-cancel]").onclick = () => box.remove();
  box.onsubmit = async (ev) => {
    ev.preventDefault();
    const f = new FormData(box);
    try {
      await api("/api/suggest", { memory_id: m.id, author: f.get("author"), field: f.get("field"), value: f.get("value"), reason: f.get("reason") });
      await refreshCurrent(m.id);
    } catch (e) { toast(e.message); }
  };
  return box;
}

async function readerAction(btn) {
  const m = state.memories.find((x) => x.id === state.selected);
  if (!m) return;
  if (btn.dataset.act === "photo") {
    const f = await pickFile("image/jpeg,image/png,image/webp");
    if (!f) return;
    try { await uploadMedia(m.id, f, f.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ")); await refreshCurrent(m.id); } catch (e) { toast(e.message); }
  } else if (btn.dataset.act === "voice") {
    if (recorder.rec) { stopRecording(); return; }
    try {
      await startRecording(async (blob) => {
        try { await uploadMedia(m.id, blob, "", m.elder); await refreshCurrent(m.id); } catch (e) { toast(e.message); }
      });
      btn.classList.add("recording");
      btn.textContent = "■ Stop recording";
    } catch { toast("Microphone permission is needed to record their voice."); }
  } else if (btn.dataset.act === "suggest") {
    if (!$("#reader .sug-form")) btn.closest(".reader-actions").after(suggestForm(m));
  }
}

$("#reader").addEventListener("click", async (ev) => {
  const d = ev.target.closest("[data-decide]");
  if (!d) return;
  const m = state.memories.find((x) => x.id === state.selected);
  try {
    await api("/api/decide", { id: +d.dataset.decide, approve: d.dataset.ok === "1", by: m.elder });
    await refreshCurrent(m.id);
  } catch (e) { toast(e.message); }
});

// ------------------------------------------------------------ Alexa dock: their voice + photo questions

const pending = { voice: null, photo: null };
function renderAttach() {
  const parts = [];
  if (pending.photo) parts.push(`<span class="chip"><img src="${pending.photo.url}" alt=""> photo will be kept with the answer <button data-drop="photo" aria-label="Remove">×</button></span>`);
  if (pending.voice) parts.push(`<span class="chip">🎙 their voice recorded <button data-drop="voice" aria-label="Remove">×</button></span>`);
  $("#attach").innerHTML = parts.join("");
  $("#attach").hidden = !parts.length;
}
$("#attach").addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-drop]");
  if (b) { pending[b.dataset.drop] = null; renderAttach(); }
});

$("#recBtn").addEventListener("click", async () => {
  const b = $("#recBtn");
  if (recorder.rec) { stopRecording(); return; }
  try {
    await startRecording((blob) => { pending.voice = blob; b.classList.remove("recording"); renderAttach(); });
    b.classList.add("recording");
    bubble("sys", "Recording their voice… type what they say, then tap 🎙 again to stop.");
  } catch { alertBubble("Microphone permission is needed to record their voice."); }
});

$("#photoBtn").addEventListener("click", () => $("#photoInput").click());
$("#photoInput").addEventListener("change", async () => {
  const f = $("#photoInput").files[0];
  $("#photoInput").value = "";
  if (!f) return;
  if (state.mode !== "interview") document.querySelector('.mode[data-mode="interview"]').click();
  pending.photo = { file: f, url: URL.createObjectURL(f) };
  renderAttach();
  bubble("user-says", `<img class="bubble-photo" src="${pending.photo.url}" alt="Photo shown to ${esc(state.elder)}">`);
  await alexaSays(`${state.elder}, tell me about this photo. Who is in it, and when was it taken?`);
});

// called after an interview answer is saved; returns what was kept, e.g. ["the photo", "their voice"]
async function attachPending(memoryId) {
  const jobs = [], kept = [];
  if (pending.photo) { jobs.push(uploadMedia(memoryId, pending.photo.file, "Shown during an interview", "")); kept.push("the photo"); }
  if (pending.voice) { jobs.push(uploadMedia(memoryId, pending.voice, "", state.elder)); kept.push("their voice"); }
  pending.photo = pending.voice = null;
  renderAttach();
  await Promise.all(jobs);
  return kept;
}

function toast(msg) {
  const t = Object.assign(document.createElement("div"), { className: "toast", textContent: msg, role: "status" });
  document.body.append(t);
  setTimeout(() => t.remove(), 4000);
}

// ------------------------------------------------------------ family graph

const KIND = { elder: { r: 30, c: "var(--story)" }, person: { r: 17, c: "var(--wisdom)" }, place: { r: 17, c: "var(--health)" }, event: { r: 17, c: "var(--recipe)" } };
let graphData = null;

async function loadGraph() {
  graphData = await api("/api/graph");
  renderGraph();
}

function renderGraph(focus) {
  const { nodes, edges } = graphData;
  const W = 800, H = 420, cx = W / 2, cy = H / 2;
  const elders = nodes.filter((n) => n.kind === "elder");
  const others = nodes.filter((n) => n.kind !== "elder");
  const pos = {};
  elders.forEach((n, i) => (pos[n.id] = { x: cx + (i - (elders.length - 1) / 2) * 170, y: cy }));
  // each node sits on the side of the elder(s) who mention it: left arc, right arc, or top/bottom if shared
  const order = ["person", "place", "event"];
  others.sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind) || a.label.localeCompare(b.label));
  const side = (n) => {
    const xs = edges.filter((e) => e.source === n.id || e.target === n.id)
      .map((e) => pos[e.source === n.id ? e.target : e.source]?.x).filter((x) => x != null);
    const avg = xs.reduce((a, b) => a + b, 0) / (xs.length || 1);
    return Math.abs(avg - cx) < 1 ? "mid" : avg < cx ? "left" : "right";
  };
  const groups = { left: [], right: [], mid: [] };
  others.forEach((n) => groups[side(n)].push(n));
  const place = (list, from, to) => list.forEach((n, i) => {
    const t = from + ((i + 0.5) / list.length) * (to - from);
    pos[n.id] = { x: cx + Math.cos(t) * 330, y: cy - 8 + Math.sin(t) * 150 };
  });
  const deg = Math.PI / 180;
  place(groups.left, 112 * deg, 248 * deg);
  place(groups.right, -68 * deg, 68 * deg);
  groups.mid.forEach((n, i) => {
    const up = i % 2 === 0, k = Math.floor(i / 2), m = Math.ceil(groups.mid.length / 2);
    pos[n.id] = { x: cx + (k - (m - 1) / 2) * 110, y: up ? 52 : H - 64 };
  });
  const near = focus ? new Set(edges.filter((e) => e.source === focus || e.target === focus).flatMap((e) => [e.source, e.target])) : null;
  const lines = edges.map((e, i) => {
    const a = pos[e.source], b = pos[e.target];
    const on = !focus || e.source === focus || e.target === focus;
    return `<line class="edge ${e.kind} ${on ? "" : "dim"}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" style="--i:${i};stroke-width:${1 + Math.min(e.memories.length, 4)}"><title>${e.memories.length} memor${e.memories.length === 1 ? "y" : "ies"}${e.kind === "context" ? " · historical context for that year" : ""}</title></line>`;
  }).join("");
  const circles = nodes.map((n, i) => {
    const p = pos[n.id], k = KIND[n.kind];
    const dim = near && !near.has(n.id);
    const words = n.kind === "event" ? n.label.replace(/ \(.+\)/, "") : n.label;
    return `<g class="gnode ${n.kind} ${n.id === focus ? "focus" : ""} ${dim ? "dim" : ""}" data-node="${esc(n.id)}" tabindex="0" role="button" aria-label="${esc(n.label)}" style="--i:${i}">
      <circle cx="${p.x}" cy="${p.y}" r="${k.r}" fill="${k.c}"></circle>
      <text x="${p.x}" y="${p.y + (n.kind === "elder" ? 5 : k.r + 15)}" class="${n.kind === "elder" ? "in" : ""}">${esc(words)}</text>
    </g>`;
  }).join("");
  const legend = Object.entries({ elder: "Elder", person: "Person", place: "Place", event: "Historical event" }).map(([k, v], i) =>
    `<g transform="translate(${16 + i * 100},18)"><circle r="6" fill="${KIND[k].c}"></circle><text x="12" y="4" class="legend">${v}</text></g>`).join("");
  $("#graph").innerHTML = `<g>${lines}</g><g>${circles}</g>${legend}`;
}

async function focusNode(id) {
  renderGraph(id);
  const n = graphData.nodes.find((x) => x.id === id);
  const { memories } = await api("/api/memories");
  const ids = [...new Set(n.memories)];
  const ms = memories.filter((m) => ids.includes(m.id)).sort((a, b) => (a.year || 9999) - (b.year || 9999));
  $("#graphSide").innerHTML = `<h4>${esc(n.label)}</h4>
    <p class="graph-kind">${n.kind === "event" ? "Historical context. Not something they said, just what was happening that year." : `${ms.length} connected memor${ms.length === 1 ? "y" : "ies"}`}</p>
    <ul>${ms.map((m) => `<li><a href="#" data-open="${m.id}"><span>${m.year ?? "·"}</span>${esc(m.title)}<small>${esc(m.elder)}</small></a></li>`).join("")}</ul>`;
}

$("#graph").addEventListener("click", (ev) => {
  const g = ev.target.closest(".gnode");
  if (g) focusNode(g.dataset.node);
});
$("#graph").addEventListener("keydown", (ev) => {
  const g = ev.target.closest(".gnode");
  if (g && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); focusNode(g.dataset.node); }
});
$("#graphSide").addEventListener("click", (ev) => {
  const a = ev.target.closest("[data-open]");
  if (a) { ev.preventDefault(); openMemory(+a.dataset.open); $(".book").scrollIntoView({ behavior: "smooth" }); }
});

loadGraph();
