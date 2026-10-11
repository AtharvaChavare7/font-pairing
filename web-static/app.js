const API_BASE =
  window.location.port === "8000" || window.location.pathname.startsWith("/ui")
    ? ""
    : window.location.hostname === "localhost"
      ? "http://localhost:8000"
      : "";

const $ = (sel, root = document) => root.querySelector(sel);
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

const CATEGORIES = [
  ["serif", "Serif"],
  ["sans", "Sans"],
  ["display", "Display"],
  ["handwriting", "Script"],
  ["mono", "Mono"],
];
const FALLBACK = { serif: "serif", sans: "sans-serif", mono: "monospace", handwriting: "cursive", display: "sans-serif" };
const DNA_LABELS = {
  xh_ratio: "x-height",
  width: "Width",
  weight: "Weight",
  contrast: "Stroke contrast",
  aperture: "Aperture",
  serif: "Serifs",
};
const DEFAULT_HEAD = "Words set in the right company carry further";
const DEFAULT_BODY = [
  "Type pairing is a conversation between two voices. The heading sets the tone and <em>earns the glance</em>; the body does the slow, patient work of <strong>being read</strong>.",
  "When their proportions agree and their personalities differ, the page feels settled — as if it could not have been set any other way. Figures like 1,234.56 should sit comfortably too.",
];

const state = {
  anchor: null, // {id, name, category}
  role: "either",
  headingCats: new Set(),
  bodyCats: new Set(),
  results: [],
  saved: loadSaved(),
  request: null, // AbortController of the in-flight request
};

/* ---------------- Font loading ---------------- */

const loadedCss = new Set();

function uprightWeights(font) {
  return font.styles.filter((s) => /^\d+$/.test(s)).map(Number);
}

function closest(list, target) {
  return list.reduce((a, b) => (Math.abs(b - target) < Math.abs(a - target) ? b : a));
}

function headingWeight(font) {
  const ups = uprightWeights(font);
  if (!ups.length) return 400;
  const target = { sans: 600, mono: 600, serif: 500 }[font.category] ?? 400;
  return closest(ups, target);
}

function bodyStyles(font) {
  const ups = uprightWeights(font);
  const regular = ups.length ? closest(ups, 400) : 400;
  const bolds = ups.filter((w) => w >= 600);
  const bold = bolds.length ? closest(bolds, 700) : null;
  const italic = font.styles.includes(`${regular}i`);
  return { regular, bold, italic, uprightMissing: !ups.length };
}

function familyParam(font, axes) {
  // axes: array of [ital, wght]
  const uniq = [...new Map(axes.map((a) => [a.join(","), a])).values()].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const name = font.name.replace(/ /g, "+");
  if (uniq.some((a) => a[0] === 1)) return `${name}:ital,wght@${uniq.map((a) => a.join(",")).join(";")}`;
  return `${name}:wght@${uniq.map((a) => a[1]).join(";")}`;
}

function fontAxes(font, role) {
  const ital = uprightWeights(font).length ? 0 : 1;
  if (role === "heading") return [[ital, headingWeight(font)]];
  const s = bodyStyles(font);
  const axes = [[ital, s.regular]];
  if (s.bold) axes.push([0, s.bold]);
  if (s.italic) axes.push([1, s.regular]);
  return axes;
}

function cssUrl(pair) {
  const h = familyParam(pair.heading, fontAxes(pair.heading, "heading"));
  const b = familyParam(pair.body, fontAxes(pair.body, "body"));
  const fams = h === b ? [h] : [h, b];
  return `https://fonts.googleapis.com/css2?${fams.map((f) => `family=${f}`).join("&")}&display=swap`;
}

function injectCss(href) {
  if (loadedCss.has(href)) return;
  loadedCss.add(href);
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}

function nameOnlyCss(font) {
  return `https://fonts.googleapis.com/css2?family=${font.name.replace(/ /g, "+")}&text=${encodeURIComponent(font.name)}&display=swap`;
}

function loadPairFonts(pair) {
  injectCss(cssUrl(pair));
  const loads = [pair.heading.name, pair.body.name].map((n) => document.fonts.load(`32px "${n}"`).catch(() => null));
  // stylesheet must arrive before document.fonts knows the faces
  return new Promise((r) => setTimeout(r, 60)).then(() =>
    Promise.race([Promise.all(loads), new Promise((r) => setTimeout(r, 2500))]),
  );
}

/* ---------------- Helpers ---------------- */

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function stack(font) {
  return `"${font.name}", ${FALLBACK[font.category] || "sans-serif"}`;
}

function specimenUrl(font) {
  return `https://fonts.google.com/specimen/${font.name.replace(/ /g, "+")}`;
}

function bodySize(font) {
  // every body sample is set to the same x-height so comparisons are fair
  const px = (17 * 0.5) / Math.max(font.x_height, 0.3);
  return Math.min(20, Math.max(15, px));
}

function catLabel(c) {
  return (CATEGORIES.find(([k]) => k === c) || [c, c])[1];
}

const contrastWords = (v) =>
  v < 0.25 ? "Close relatives" : v < 0.42 ? "Subtle" : v < 0.58 ? "Balanced" : v < 0.75 ? "Distinct" : "Opposites";
const discoveryWords = (v) =>
  v < 0.2 ? "Well known" : v < 0.45 ? "Mostly familiar" : v < 0.7 ? "Some surprises" : "Hidden gems";

let toastTimer;
function toast(msg, action) {
  const t = $("#toast");
  const btn = $("#toast-action");
  $("#toast-text").textContent = msg;
  btn.hidden = !action;
  btn.onclick = action
    ? () => {
        action();
        t.classList.remove("show");
      }
    : null;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), action ? 5000 : 1800);
}

function cssSnippet(pair) {
  return `/* ${pair.heading.name} + ${pair.body.name} */
@import url('${cssUrl(pair)}');

:root {
  --font-heading: ${stack(pair.heading)};
  --font-body: ${stack(pair.body)};
}

h1, h2, h3 {
  font-family: var(--font-heading);
  font-weight: ${headingWeight(pair.heading)};
}

body {
  font-family: var(--font-body);
  /* keeps fallback fonts at ${pair.body.name}'s x-height */
  font-size-adjust: ${pair.body.x_height.toFixed(3)};
}`;
}

async function copyText(text, msg) {
  try {
    await navigator.clipboard.writeText(text);
    toast(msg);
  } catch {
    toast("Couldn't access the clipboard");
  }
}

const ICON = {
  heart:
    '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20.5s-7.8-4.7-9.4-9.6C1.6 7.6 3.8 4.5 7.2 4.5c2 0 3.6 1.1 4.8 2.7 1.2-1.6 2.8-2.7 4.8-2.7 3.4 0 5.6 3.1 4.6 6.4-1.6 4.9-9.4 9.6-9.4 9.6Z"/></svg>',
  copy: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6.5A2.5 2.5 0 0 0 13.5 4h-7A2.5 2.5 0 0 0 4 6.5v7A2.5 2.5 0 0 0 6.5 16H8"/></svg>',
  lock: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2.5"/><path d="M8.5 11V8a3.5 3.5 0 0 1 7 0v3"/></svg>',
  hide: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18M10.6 6.1A9.8 9.8 0 0 1 12 6c5.5 0 9 6 9 6a16 16 0 0 1-2.6 3.3M6.6 6.6C4.3 8.1 3 12 3 12s3.5 6 9 6a9 9 0 0 0 4.4-1.1M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>',
  chev: '<svg class="icon chev" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>',
  out: '<svg class="icon arrow" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 16 16 8M9 8h7v7"/></svg>',
};

/* ---------------- Spring (Apple damping / response) ---------------- */

// A critically or under-damped spring that always starts from the current
// on-screen value and current velocity, so it can be interrupted at any frame.
class Spring {
  constructor(value, onUpdate) {
    this.value = value;
    this.velocity = 0;
    this.onUpdate = onUpdate;
    this.raf = 0;
  }

  stop() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  set(value) {
    this.stop();
    this.value = value;
    this.onUpdate(value);
  }

  to(target, { damping = 1, response = 0.35, velocity = this.velocity, onRest } = {}) {
    this.stop();
    if (reduceMotion.matches) {
      this.velocity = 0;
      this.set(target);
      onRest?.();
      return;
    }
    const k = (2 * Math.PI / response) ** 2; // stiffness, mass = 1
    const c = (4 * Math.PI * damping) / response; // damping coefficient
    this.velocity = velocity;
    let last = performance.now();
    const step = (now) => {
      // fixed sub-steps keep the integration stable on slow frames
      let dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      while (dt > 0) {
        const h = Math.min(dt, 1 / 240);
        const a = -k * (this.value - target) - c * this.velocity;
        this.velocity += a * h;
        this.value += this.velocity * h;
        dt -= h;
      }
      this.onUpdate(this.value);
      if (Math.abs(this.value - target) < 0.3 && Math.abs(this.velocity) < 8) {
        this.value = target;
        this.velocity = 0;
        this.onUpdate(target);
        this.raf = 0;
        onRest?.();
      } else {
        this.raf = requestAnimationFrame(step);
      }
    };
    this.raf = requestAnimationFrame(step);
  }
}

// Where a flick would come to rest (Apple's scroll-deceleration projection).
function project(velocity, decelerationRate = 0.998) {
  return ((velocity / 1000) * decelerationRate) / (1 - decelerationRate);
}

// Progressive resistance past a boundary instead of a hard stop.
function rubberband(overshoot, dimension, constant = 0.55) {
  return (overshoot * dimension * constant) / (dimension + constant * Math.abs(overshoot));
}

/* ---------------- Saved sheet ---------------- */

const sheet = {
  el: null,
  scrim: null,
  spring: null,
  open: false,
  returnFocus: null,

  width() {
    return this.el.getBoundingClientRect().width;
  },

  closedX() {
    return this.width() * 1.05;
  },

  render(x) {
    this.el.style.transform = `translateX(${x}px)`;
    this.scrim.style.opacity = String(Math.max(0, Math.min(1, 1 - x / this.width())));
  },

  init() {
    this.el = $("#sheet");
    this.scrim = $("#scrim");
    this.spring = new Spring(0, (x) => this.render(x));
    this.initDrag();
  },

  show() {
    if (this.open) return;
    this.open = true;
    this.returnFocus = document.activeElement;
    this.el.hidden = false;
    this.scrim.hidden = false;
    if (!this.spring.raf) this.spring.set(this.closedX()); // else continue from where it is
    $("#open-saved").setAttribute("aria-expanded", "true");
    // no overshoot when opening from a button — nothing was thrown
    this.spring.to(0, { damping: 1, response: 0.35 });
    $("#close-saved").focus({ preventScroll: true });
  },

  hide(velocity = 0) {
    this.open = false;
    $("#open-saved").setAttribute("aria-expanded", "false");
    // a flick carried momentum, so the exit may keep a little of it
    const damping = Math.abs(velocity) > 300 ? 0.8 : 1;
    this.spring.to(this.closedX(), {
      damping,
      response: 0.3,
      velocity,
      onRest: () => {
        if (this.open) return;
        this.el.hidden = true;
        this.scrim.hidden = true;
      },
    });
    this.returnFocus?.focus?.({ preventScroll: true });
  },

  initDrag() {
    const grip = $("#sheet-grip");
    let startX = 0;
    let startValue = 0;
    let history = [];
    let dragging = false;

    grip.addEventListener("pointerdown", (e) => {
      if (e.target.closest("button")) return;
      grip.setPointerCapture(e.pointerId);
      // grab the sheet wherever it is right now, even mid-animation
      this.spring.stop();
      startX = e.clientX;
      startValue = this.spring.value;
      history = [{ x: e.clientX, t: e.timeStamp }];
      dragging = true;
    });

    grip.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      let x = startValue + (e.clientX - startX); // 1:1, respecting the grab offset
      if (x < 0) x = rubberband(x, this.width());
      this.spring.value = x;
      this.render(x);
      history.push({ x: e.clientX, t: e.timeStamp });
      if (history.length > 6) history.shift();
    });

    const release = (e) => {
      if (!dragging) return;
      dragging = false;
      const first = history[0];
      const last = history[history.length - 1];
      const dt = (last.t - first.t) / 1000;
      const v = dt > 0 ? (last.x - first.x) / dt : 0;
      // decide from where the gesture is going, not where it let go
      const projected = this.spring.value + project(v);
      if (projected > this.width() / 2) this.hide(v);
      else this.spring.to(0, { damping: 1, response: 0.3, velocity: v });
      if (e.pointerId !== undefined && grip.hasPointerCapture(e.pointerId)) grip.releasePointerCapture(e.pointerId);
    };
    grip.addEventListener("pointerup", release);
    grip.addEventListener("pointercancel", release);
  },
};

/* ---------------- Saved data ---------------- */

function loadSaved() {
  try {
    return JSON.parse(localStorage.getItem("fpe.saved") || "[]");
  } catch {
    return [];
  }
}

function persistSaved() {
  try {
    localStorage.setItem("fpe.saved", JSON.stringify(state.saved));
  } catch {
    /* storage unavailable — saved list lasts for this session only */
  }
  const badge = $("#saved-count");
  badge.textContent = state.saved.length;
  badge.hidden = !state.saved.length;
}

const pairKey = (p) => `${p.heading.id}|${p.body.id}`;
const isSaved = (p) => state.saved.some((s) => pairKey(s) === pairKey(p));

function setSaved(pair, on) {
  state.saved = state.saved.filter((s) => pairKey(s) !== pairKey(pair));
  if (on) {
    state.saved.unshift(pair);
    sendFeedback(pair, 1);
  }
  persistSaved();
  renderSaved();
  for (const btn of document.querySelectorAll(`.save-btn[data-key="${CSS.escape(pairKey(pair))}"]`)) {
    btn.setAttribute("aria-pressed", String(on));
    btn.setAttribute("aria-label", on ? "Remove from saved" : "Save pairing");
  }
}

function sendFeedback(pair, vote) {
  fetch(`${API_BASE}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ heading: pair.heading.id, body: pair.body.id, vote, target_dist: Number($("#contrast").value) }),
  }).catch(() => {});
}

function renderSaved() {
  const list = $("#saved-list");
  list.innerHTML = "";
  $("#saved-empty").hidden = state.saved.length > 0;
  for (const p of state.saved) {
    injectCss(cssUrl(p));
    const li = document.createElement("li");
    li.className = "saved-item";
    li.innerHTML = `
      <p class="h" style="font-family:${esc(stack(p.heading))};font-weight:${headingWeight(p.heading)}">${esc(p.heading.name)}</p>
      <p class="b" style="font-family:${esc(stack(p.body))}">${esc(p.body.name)} for the body text.</p>
      <div class="row">
        <button type="button" class="act" data-act="css">${ICON.copy}Copy CSS</button>
        <button type="button" class="act quiet" data-act="remove">Remove</button>
      </div>`;
    li.querySelector('[data-act="css"]').addEventListener("click", () => copyText(cssSnippet(p), "CSS copied"));
    li.querySelector('[data-act="remove"]').addEventListener("click", () => {
      setSaved(p, false);
      toast(`Removed ${p.heading.name} + ${p.body.name}`, () => setSaved(p, true));
    });
    list.appendChild(li);
  }
}

/* ---------------- Cards ---------------- */

function specimenHtml(pair) {
  const head = $("#sample-head").value.trim() || DEFAULT_HEAD;
  const custom = $("#sample-body").value.trim();
  const paras = custom ? custom.split(/\n\s*\n/).map(esc) : DEFAULT_BODY;
  const hw = headingWeight(pair.heading);
  const bs = bodyStyles(pair.body);
  const size = bodySize(pair.body);
  const hItalic = uprightWeights(pair.heading).length ? "" : ";font-style:italic";
  const bItalic = bs.uprightMissing ? ";font-style:italic" : "";
  return `
    <h2 class="spec-h" style="font-family:${esc(stack(pair.heading))};font-weight:${hw}${hItalic}">${esc(head)}</h2>
    ${paras
      .map((p) => `<p class="spec-b" style="font-family:${esc(stack(pair.body))};font-size:${size.toFixed(1)}px;font-weight:${bs.regular}${bItalic}">${p}</p>`)
      .join("")}`;
}

function meterRow(label, v, shown) {
  return `<dt>${label}</dt><dd><div class="bar"><i style="--v:${Math.max(0, Math.min(1, v)).toFixed(3)}"></i></div></dd><dd class="val">${shown}</dd>`;
}

function detailsHtml(pair) {
  const bd = pair.breakdown;
  const bs = bodyStyles(pair.body);
  const dna = Object.entries(DNA_LABELS)
    .map(([k, label]) => {
      const h = (pair.heading.dna[k] * 100).toFixed(1);
      const b = (pair.body.dna[k] * 100).toFixed(1);
      return `<span>${label}</span><div class="track" role="img" aria-label="${label}: heading at the ${Math.round(h)}th percentile, body at the ${Math.round(b)}th">
        <i class="m h" style="left:${h}%"></i><i class="m b" style="left:${b}%"></i></div>`;
    })
    .join("");
  return `
    <div>
      <h3>Score</h3>
      <dl class="meters">
        ${meterRow("Harmony", bd.harmony, Math.round(bd.harmony * 100))}
        ${meterRow("Contrast", bd.contrast, bd.contrast.toFixed(2))}
        ${meterRow("Legibility", bd.legibility, Math.round(bd.legibility * 100))}
        ${meterRow("Familiarity", bd.familiarity, Math.round(bd.familiarity * 100))}
      </dl>
      <h3>Measurements</h3>
      <div class="legend-row"><span><i class="dot h"></i>${esc(pair.heading.name)}</span><span><i class="dot b"></i>${esc(pair.body.name)}</span></div>
      <div class="dna">${dna}</div>
    </div>
    <div>
      <h3>Why it works</h3>
      <ul class="reasons">${pair.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      ${pair.notes.length ? `<ul class="notes">${pair.notes.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
      <p class="lead-reason" style="margin-top:var(--s4)">Body set at ${bodySize(pair.body).toFixed(1)}px so every sample shares one x-height. ${esc(pair.body.name)} ${bs.regular}${bs.bold ? ` / ${bs.bold}` : ""}${bs.italic ? " with italic" : ""}.</p>
    </div>`;
}

function pairCard(pair, i) {
  const el = document.createElement("article");
  el.className = "pair";
  el.style.setProperty("--i", i);
  el.dataset.loading = "true";
  el.setAttribute("aria-label", `${pair.heading.name} with ${pair.body.name}`);
  const saved = isSaved(pair);
  const detailsId = `details-${i}-${pair.heading.id}-${pair.body.id}`;

  el.innerHTML = `
    <div class="pair-head">
      <div class="names">
        <span>Heading <a href="${specimenUrl(pair.heading)}" target="_blank" rel="noopener">${esc(pair.heading.name)}${ICON.out}</a></span>
        <span>Body <a href="${specimenUrl(pair.body)}" target="_blank" rel="noopener">${esc(pair.body.name)}${ICON.out}</a></span>
      </div>
      <div class="score">
        <span class="score-num">${Math.round(pair.score)}</span><span class="score-lbl">match</span>
        <button type="button" class="icon-btn save-btn" data-key="${esc(pairKey(pair))}" aria-pressed="${saved}" aria-label="${saved ? "Remove from saved" : "Save pairing"}">${ICON.heart}</button>
      </div>
    </div>
    <div class="specimen">${specimenHtml(pair)}</div>
    <div class="pair-foot">
      <p class="lead-reason">${esc(pair.reasons[0] || "")}</p>
      <div class="actions">
        <button type="button" class="act" data-act="details" aria-expanded="false" aria-controls="${detailsId}">Details${ICON.chev}</button>
        <button type="button" class="act" data-act="css">${ICON.copy}Copy CSS</button>
        <button type="button" class="act" data-act="keep-h" title="More body fonts for ${esc(pair.heading.name)}">${ICON.lock}Keep heading</button>
        <button type="button" class="act" data-act="keep-b" title="More heading fonts for ${esc(pair.body.name)}">${ICON.lock}Keep body</button>
        <button type="button" class="act quiet" data-act="hide" aria-label="Hide this pairing">${ICON.hide}</button>
      </div>
    </div>
    <div class="details" id="${detailsId}" hidden></div>`;

  el.querySelector(".save-btn").addEventListener("click", () => {
    const on = !isSaved(pair);
    setSaved(pair, on);
    toast(on ? "Saved" : "Removed from saved");
  });
  el.querySelector('[data-act="details"]').addEventListener("click", (e) => {
    const box = el.querySelector(".details");
    const open = box.hidden;
    if (open && !box.innerHTML) box.innerHTML = detailsHtml(pair);
    box.hidden = !open;
    e.currentTarget.setAttribute("aria-expanded", String(open));
  });
  el.querySelector('[data-act="css"]').addEventListener("click", () => copyText(cssSnippet(pair), "CSS copied"));
  el.querySelector('[data-act="keep-h"]').addEventListener("click", () => {
    setAnchor(pair.heading, "heading");
    generate();
  });
  el.querySelector('[data-act="keep-b"]').addEventListener("click", () => {
    setAnchor(pair.body, "body");
    generate();
  });
  el.querySelector('[data-act="hide"]').addEventListener("click", () => hidePair(el, pair));

  loadPairFonts(pair).then(() => {
    el.dataset.loading = "false";
  });
  return el;
}

function hidePair(el, pair) {
  const parent = el.parentNode;
  const next = el.nextSibling;
  el.classList.add("leaving");
  const finish = () => {
    if (el.classList.contains("leaving")) el.remove();
  };
  if (reduceMotion.matches) setTimeout(finish, 120);
  else el.addEventListener("animationend", finish, { once: true });
  sendFeedback(pair, -1);
  // forgiveness over confirmation: hide now, offer undo
  toast("Pairing hidden", () => {
    el.style.setProperty("--i", 0);
    // undo works even mid-animation: drop the exit and the card stays
    el.classList.remove("leaving");
    if (!el.isConnected) parent.insertBefore(el, next && next.parentNode === parent ? next : null);
  });
}

function refreshSpecimens() {
  for (const el of document.querySelectorAll(".pair")) {
    const idx = state.results.findIndex((p) => `${p.heading.name} with ${p.body.name}` === el.getAttribute("aria-label"));
    if (idx >= 0) el.querySelector(".specimen").innerHTML = specimenHtml(state.results[idx]);
  }
}

function renderResults(data) {
  const root = $("#results");
  root.innerHTML = "";
  if (!data.results.length) {
    root.innerHTML = `<div class="empty-state"><h2>No pairings match</h2><p>Try fewer filters, or move the Contrast slider.</p></div>`;
    return;
  }
  data.results.forEach((p, i) => root.appendChild(pairCard(p, i)));
}

/* ---------------- Generate ---------------- */

function buildRequest(seed) {
  return {
    n: 8,
    seed,
    target_dist: Number($("#contrast").value),
    discovery: Number($("#discovery").value),
    variety: 0.35,
    anchor_id: state.anchor?.id ?? null,
    anchor_role: state.role,
    filters: {
      exclude_overused: $("#skip-overused").checked,
      heading_categories: [...state.headingCats],
      body_categories: [...state.bodyCats],
      exclude_ids: [],
    },
  };
}

async function generate() {
  // a new request interrupts the old one instead of being ignored
  state.request?.abort();
  const controller = new AbortController();
  state.request = controller;
  const btn = $("#generate");
  const results = $("#results");
  btn.setAttribute("aria-busy", "true");
  results.setAttribute("aria-busy", "true");

  try {
    const res = await fetch(`${API_BASE}/api/pair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildRequest(Math.floor(Math.random() * 1e9))),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`The server answered ${res.status}`);
    const data = await res.json();
    if (!data.corpus_size) {
      results.innerHTML = `<div class="empty-state"><h2>No font data yet</h2><p>Run <code>fontpair-ingest run</code>, then restart the server.</p></div>`;
      $("#status").textContent = "";
      return;
    }
    state.results = data.results;
    renderResults(data);
    const anchored = state.anchor ? ` around ${state.anchor.name}` : "";
    $("#status").textContent = `${data.results.length} pairings${anchored}, from ${data.corpus_size.toLocaleString()} measured families.`;
  } catch (err) {
    if (err.name === "AbortError") return;
    results.innerHTML = `<div class="empty-state"><h2>Can't reach the pairing server</h2><p>${esc(err.message)}. Start it with <code>make api</code> and try again.</p></div>`;
  } finally {
    if (state.request === controller) {
      state.request = null;
      btn.removeAttribute("aria-busy");
      results.setAttribute("aria-busy", "false");
    }
  }
}

let regenTimer;
function regenerateSoon() {
  clearTimeout(regenTimer);
  regenTimer = setTimeout(generate, 250);
}

/* ---------------- Floating layers ---------------- */

function openLayer(el) {
  el.hidden = false;
  el.dataset.state = "open";
}

function closeLayer(el) {
  if (el.hidden || el.dataset.state === "closing") return;
  el.dataset.state = "closing";
  const done = () => {
    if (el.dataset.state === "closing") el.hidden = true;
  };
  if (reduceMotion.matches) setTimeout(done, 120);
  else el.addEventListener("animationend", done, { once: true });
}

/* ---------------- Anchor search ---------------- */

function setAnchor(font, role) {
  state.anchor = font ? { id: font.id, name: font.name, category: font.category } : null;
  const input = $("#anchor-input");
  input.value = font ? font.name : "";
  input.style.fontFamily = "";
  if (font) {
    injectCss(nameOnlyCss(font));
    input.style.fontFamily = `"${font.name}", var(--font)`;
  }
  $("#anchor-clear").hidden = !font;
  $("#anchor-role").hidden = !font;
  if (role) setRole(role);
  if (font && window.scrollY > $("#toolbar").offsetTop) window.scrollTo({ top: $("#toolbar").offsetTop, behavior: "smooth" });
}

function setRole(role) {
  state.role = role;
  for (const b of $("#anchor-role").querySelectorAll("button")) {
    b.setAttribute("aria-checked", String(b.dataset.role === role));
  }
}

let suggestTimer;
let suggestions = [];
let activeIdx = -1;

function closeSuggest() {
  closeLayer($("#anchor-list"));
  $("#anchor-input").setAttribute("aria-expanded", "false");
  $("#anchor-input").removeAttribute("aria-activedescendant");
  activeIdx = -1;
}

function paintActive() {
  [...$("#anchor-list").children].forEach((li, i) => li.setAttribute("aria-selected", String(i === activeIdx)));
  if (activeIdx >= 0) $("#anchor-input").setAttribute("aria-activedescendant", `opt-${activeIdx}`);
}

async function suggest(q) {
  const res = await fetch(`${API_BASE}/api/families?q=${encodeURIComponent(q)}&per_page=8`);
  const data = await res.json();
  if ($("#anchor-input").value.trim() !== q) return; // stale answer
  suggestions = data.families;
  const list = $("#anchor-list");
  list.innerHTML = "";
  if (!suggestions.length) return closeSuggest();
  suggestions.forEach((f, i) => {
    injectCss(nameOnlyCss(f));
    const li = document.createElement("li");
    li.id = `opt-${i}`;
    li.setAttribute("role", "option");
    li.innerHTML = `<span class="s-name" style="font-family:${esc(stack(f))}">${esc(f.name)}</span><span class="s-cat">${catLabel(f.category)}</span>`;
    // commit on press, so the field's blur can't swallow the choice
    li.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      pick(i);
    });
    list.appendChild(li);
  });
  if (list.hidden || list.dataset.state === "closing") openLayer(list);
  $("#anchor-input").setAttribute("aria-expanded", "true");
  activeIdx = 0;
  paintActive();
}

function pick(i) {
  const f = suggestions[i];
  if (!f) return;
  closeSuggest();
  setAnchor(f, state.role);
  generate();
}

/* ---------------- Filters ---------------- */

function filterCount() {
  return state.headingCats.size + state.bodyCats.size + ($("#skip-overused").checked ? 1 : 0);
}

function paintFilterBadge() {
  const n = filterCount();
  $("#filter-count").textContent = n;
  $("#filter-count").hidden = !n;
}

function buildChips() {
  for (const fs of document.querySelectorAll(".group[data-target]")) {
    const set = fs.dataset.target === "heading" ? state.headingCats : state.bodyCats;
    const wrap = fs.querySelector(".chips");
    for (const [key, label] of CATEGORIES) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = label;
      b.dataset.key = key;
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", () => {
        if (set.has(key)) set.delete(key);
        else set.add(key);
        b.setAttribute("aria-pressed", String(set.has(key)));
        paintFilterBadge();
        regenerateSoon();
      });
      wrap.appendChild(b);
    }
  }
}

function toggleFilters(open) {
  const pop = $("#filters");
  const btn = $("#open-filters");
  if (open) openLayer(pop);
  else closeLayer(pop);
  btn.setAttribute("aria-expanded", String(open));
}

/* ---------------- Wiring ---------------- */

function paintSlider(el) {
  const pct = ((el.value - el.min) / (el.max - el.min)) * 100;
  el.style.setProperty("--fill-pct", `${pct}%`);
}

function init() {
  sheet.init();
  buildChips();
  persistSaved();
  renderSaved();

  // sliders: describe the value continuously while dragging, fetch on release
  for (const [id, words] of [
    ["contrast", contrastWords],
    ["discovery", discoveryWords],
  ]) {
    const el = $(`#${id}`);
    const out = $(`#${id}-out`);
    const paint = () => {
      out.textContent = words(Number(el.value));
      paintSlider(el);
    };
    paint();
    el.addEventListener("input", paint);
    el.addEventListener("change", generate);
  }

  $("#generate").addEventListener("click", generate);

  // filters popover: non-modal, grows from its button, closes on outside press
  $("#open-filters").addEventListener("click", () => toggleFilters($("#filters").hidden || $("#filters").dataset.state === "closing"));
  document.addEventListener("pointerdown", (e) => {
    if (!$("#filters").hidden && !e.target.closest(".popover-anchor")) toggleFilters(false);
  });
  $("#skip-overused").addEventListener("change", () => {
    paintFilterBadge();
    regenerateSoon();
  });
  $("#reset-filters").addEventListener("click", () => {
    state.headingCats.clear();
    state.bodyCats.clear();
    $("#skip-overused").checked = false;
    for (const c of document.querySelectorAll(".chip")) c.setAttribute("aria-pressed", "false");
    paintFilterBadge();
    regenerateSoon();
  });
  // sample text updates every specimen as you type
  for (const id of ["sample-head", "sample-body"]) $(`#${id}`).addEventListener("input", refreshSpecimens);

  const input = $("#anchor-input");
  input.addEventListener("input", () => {
    input.style.fontFamily = "";
    if (state.anchor) {
      state.anchor = null;
      $("#anchor-role").hidden = true;
    }
    $("#anchor-clear").hidden = !input.value;
    clearTimeout(suggestTimer);
    const q = input.value.trim();
    if (!q) return closeSuggest();
    suggestTimer = setTimeout(() => suggest(q).catch(closeSuggest), 90);
  });
  input.addEventListener("keydown", (e) => {
    const open = !$("#anchor-list").hidden;
    if (e.key === "ArrowDown" && open) {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, suggestions.length - 1);
      paintActive();
    } else if (e.key === "ArrowUp" && open) {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, 0);
      paintActive();
    } else if (e.key === "Enter" && open) {
      e.preventDefault();
      pick(activeIdx);
    } else if (e.key === "Escape") {
      closeSuggest();
    }
  });
  input.addEventListener("blur", closeSuggest);
  $("#anchor-clear").addEventListener("click", () => {
    setAnchor(null);
    setRole("either");
    closeSuggest();
    input.focus();
    generate();
  });
  for (const b of $("#anchor-role").querySelectorAll("button")) {
    b.addEventListener("click", () => {
      setRole(b.dataset.role);
      generate();
    });
  }

  $("#open-saved").addEventListener("click", () => (sheet.open ? sheet.hide() : sheet.show()));
  $("#close-saved").addEventListener("click", () => sheet.hide());
  $("#scrim").addEventListener("click", () => sheet.hide());

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (sheet.open) sheet.hide();
      else if (!$("#filters").hidden) {
        toggleFilters(false);
        $("#open-filters").focus();
      }
    }
    const el = document.activeElement;
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(el?.tagName) && el.type !== "range" && el.type !== "checkbox";
    if (!typing && !sheet.open && (e.key === "r" || e.key === "R") && !e.metaKey && !e.ctrlKey && !e.altKey) generate();
  });

  // scroll-edge effect on the toolbar only when content is underneath it
  const toolbar = $("#toolbar");
  let ticking = false;
  window.addEventListener(
    "scroll",
    () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        toolbar.classList.toggle("scrolled", window.scrollY > toolbar.offsetTop + 1);
        ticking = false;
      });
    },
    { passive: true },
  );

  fetch(`${API_BASE}/health`)
    .then((r) => r.json())
    .then((h) => {
      if (h.families) $("#family-count").textContent = `${h.families.toLocaleString()} Google Fonts families`;
    })
    .catch(() => {});

  generate();
}

init();
