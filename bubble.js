/* Общий движок сообщения: оверлей и конструктор строят сообщение одним и тем же кодом,
   поэтому в редакторе всё выглядит ровно так же, как в OBS. */
(function (g) {
"use strict";
const BK = {};

const okColor = c => typeof c === "string" && /^#[0-9a-f]{6}$/i.test(c);
const n = (v, d) => (v !== null && v !== "" && Number.isFinite(+v)) ? +v : d;
const rgba = (h, a) => {
  const m = /^#?([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(h || "");
  return m ? `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a})` : `rgba(16,16,24,${a})`;
};
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
BK.el = el;

/* ---------- тема по умолчанию (зеркало server.py) ---------- */
BK.defaultTheme = () => ({
  frame: "", base: "css", bgMode: "solid", bgColor2: "#2a2a4a", bgAngle: 135,
  borderW: 0, borderMode: "solid", borderColor: "#ffffff", borderColor2: "#4cc9f0", borderAngle: 135, borderAlpha: 100,
  glowSize: 0, glowColor: "#7a5cff", shadowSize: 0,
  gradOn: false, gradC1: "#ff4d6d", gradC2: "#4cc9f0", gradAngle: 90, gradAlpha: 35,
  layout: "inline", textAlign: "left", maxW: 100, minW: 0, decorScale: 100, decor: [],
});

/* ---------- готовые рамки ---------- */
const WHITE = {textColor: "#ffffff", shadow: true};
BK.FRAMES = [
  {id: "space", name: "Космос",
   S: {...WHITE, bgColor: "#0b0b3b", bgOpacity: 0.92, radius: 8, padT: 8, padR: 16, padB: 8, padL: 16},
   T: {bgMode: "gradient", bgColor2: "#1a1a8a", bgAngle: 180, borderW: 2, borderColor: "#6b7bff", borderAlpha: 85, glowSize: 14, glowColor: "#4a5cff"},
   decor: [
     {kind: "glyph", glyph: "★", color: "#7fb8ff", ax: 100, ay: 0, ox: -6, oy: -6, w: 40, rot: 14, anim: "float"},
     {kind: "glyph", glyph: "✦", color: "#ffffff", ax: 0, ay: 100, ox: 8, oy: -2, w: 16, anim: "blink"},
     {kind: "glyph", glyph: "✦", color: "#bcd4ff", ax: 100, ay: 100, ox: -10, oy: -4, w: 12, anim: "blink"}]},
  {id: "neon", name: "Неон",
   S: {...WHITE, bgColor: "#0a0a14", bgOpacity: 0.85, radius: 10, padT: 8, padR: 16, padB: 8, padL: 16},
   T: {borderW: 3, borderMode: "gradient", borderColor: "#ff2bd6", borderColor2: "#2bd9ff", borderAngle: 135, glowSize: 16, glowColor: "#c02bff"},
   decor: []},
  {id: "gold", name: "Золото",
   S: {...WHITE, bgColor: "#2a1c06", bgOpacity: 0.93, radius: 6, padT: 8, padR: 16, padB: 8, padL: 16},
   T: {bgMode: "gradient", bgColor2: "#4a3410", bgAngle: 135, borderW: 3, borderMode: "gradient", borderColor: "#fff0a6", borderColor2: "#b8860b", glowSize: 8, glowColor: "#ffc800"},
   decor: [{kind: "glyph", glyph: "♛", color: "#ffd700", ax: 0, ay: 0, ox: 10, oy: -14, w: 30, rot: -12, anim: "none"}]},
  {id: "glass", name: "Стекло",
   S: {...WHITE, bgColor: "#ffffff", bgOpacity: 0.14, radius: 16, padT: 8, padR: 16, padB: 8, padL: 16},
   T: {borderW: 1, borderColor: "#ffffff", borderAlpha: 35, shadowSize: 18}, decor: []},
  {id: "pixel", name: "Пиксель",
   S: {...WHITE, bgColor: "#14142b", bgOpacity: 1, radius: 0, padT: 8, padR: 14, padB: 8, padL: 14},
   T: {borderW: 4, borderColor: "#ffffff", borderAlpha: 100}, decor: []},
  {id: "sunset", name: "Закат",
   S: {...WHITE, bgColor: "#ff6a3d", bgOpacity: 0.92, radius: 18, padT: 8, padR: 16, padB: 8, padL: 16},
   T: {bgMode: "gradient", bgColor2: "#8a2be2", bgAngle: 120, shadowSize: 14}, decor: []},
  {id: "ice", name: "Лёд",
   S: {...WHITE, bgColor: "#0e3350", bgOpacity: 0.78, radius: 14, padT: 8, padR: 16, padB: 8, padL: 16},
   T: {bgMode: "gradient", bgColor2: "#1f6f9f", bgAngle: 160, borderW: 2, borderColor: "#bfeaff", borderAlpha: 80, glowSize: 10, glowColor: "#6fd3ff"},
   decor: [{kind: "glyph", glyph: "❄", color: "#d8f4ff", ax: 100, ay: 0, ox: -2, oy: -8, w: 30, rot: 10, anim: "swing"}]},
  {id: "sakura", name: "Сакура",
   S: {textColor: "#3a0a24", shadow: false, bgColor: "#ffb3d1", bgOpacity: 0.9, radius: 20, padT: 8, padR: 16, padB: 8, padL: 16},
   T: {bgMode: "gradient", bgColor2: "#ff7eb6", bgAngle: 135, borderW: 2, borderColor: "#ffffff", borderAlpha: 90, shadowSize: 10},
   decor: [{kind: "glyph", glyph: "✿", color: "#ffffff", ax: 0, ay: 0, ox: 6, oy: -8, w: 28, rot: -15, anim: "none"}]},
  {id: "soft", name: "Тёмная плашка",
   S: {...WHITE, bgColor: "#000000", bgOpacity: 0.62, radius: 16, padT: 8, padR: 16, padB: 8, padL: 16},
   T: {shadowSize: 12}, decor: []},
  {id: "text", name: "Только текст",
   S: {...WHITE, bgColor: "#000000", bgOpacity: 0, radius: 0, padT: 2, padR: 6, padB: 2, padL: 6},
   T: {}, decor: []},
];
BK.GLYPHS = ["★", "✦", "✧", "♥", "❄", "✿", "☾", "⚡", "♪", "♛", "❖", "☘", "🌸", "🔥", "👑", "✨"];

/* ---------- шрифт ---------- */
BK.FONT_BASES = ["Segoe UI", "Arial", "Arial Black", "Verdana", "Tahoma", "Trebuchet MS", "Calibri", "Georgia",
  "Times New Roman", "Palatino Linotype", "Courier New", "Consolas", "Impact", "Comic Sans MS"];
function setFont(root, name, base) {
  const key = name || "";
  if (BK._fk !== key) {
    BK._fk = key;
    const old = document.getElementById("ff"); if (old) old.remove();
    if (key) {
      const ext = key.split(".").pop().toLowerCase();
      const fmt = {ttf: "truetype", otf: "opentype", woff: "woff", woff2: "woff2"}[ext] || "truetype";
      const st = document.createElement("style"); st.id = "ff";
      st.textContent = `@font-face{font-family:"CustomChat";font-weight:100 900;font-display:block;` +
        `src:url("/files/fonts/${encodeURIComponent(key)}") format("${fmt}")}`;
      document.head.appendChild(st);
    }
  }
  const b = BK.FONT_BASES.includes(base) ? base : "Segoe UI";
  const fb = ["Georgia", "Times New Roman", "Palatino Linotype"].includes(b) ? "serif" : ["Courier New", "Consolas"].includes(b) ? "monospace" : "sans-serif";
  root.style.setProperty("--font", key ? `"CustomChat","${b}",system-ui,sans-serif` : `"${b}","Segoe UI",system-ui,${fb}`);
  if (!key) return Promise.resolve();
  return Promise.resolve(document.fonts.load('1em "CustomChat"')).catch(() => {});
}

/* ---------- режим оптимизации: eco / balanced / full ---------- */
// lite: без бесконечных анимаций (переливание, пульсация, анимации декора) и без blur;
// animEmotes: анимированные смайлы (в eco рисуются статичным кадром)
BK.eff = function (S) {
  S = S || {};
  const p = ["eco", "balanced", "full"].includes(S.perf) ? S.perf : (S.lite === false ? "full" : "balanced");
  return {perf: p, lite: p !== "full", animEmotes: p !== "eco"};
};

/* ---------- применение стиля и темы к контейнеру (.bk) ---------- */
BK.apply = function (root, S, T, o) {
  o = o || {}; S = S || {}; T = Object.assign(BK.defaultTheme(), T || {});
  const set = (k, v) => root.style.setProperty(k, v);
  const ts = Math.max(20, n(S.textScale, 100)) / 100;
  set("--fs", n(S.fontSize, 28) * ts + "px"); set("--fw", n(S.fontWeight, 600)); set("--nw", n(S.nameWeight, 800));
  set("--text", S.textColor || "#ffffff"); set("--name", S.nameColor || "#ffcc00");
  set("--es", n(S.emoteScale, 1.5)); set("--gap", n(S.gap, 8) + "px");
  set("--pt", n(S.padT, 6) + "px"); set("--pr", n(S.padR, 10) + "px");
  set("--pb", n(S.padB, 6) + "px"); set("--pl", n(S.padL, 10) + "px");
  set("--radius", n(S.radius, 14) + "px");
  set("--maxw", n(T.maxW, 100) + "%"); set("--minw", n(T.minW, 0) + "px");
  set("--ta", T.textAlign); set("--dsc", n(T.decorScale, 100) / 100);
  set("--shadow", S.shadow === false ? "none" : "0 2px 4px rgba(0,0,0,.85)");
  root.classList.add("bk");
  root.classList.toggle("lite", BK.eff(S).lite);
  root.classList.toggle("fixedname", S.nameMode === "fixed");
  root.classList.toggle("stacked", T.layout === "stacked");

  // заливка, контур, свечение
  const a = Math.max(0, Math.min(1, n(S.bgOpacity, 0.6)));
  set("--fill", T.bgMode === "gradient"
    ? `linear-gradient(${n(T.bgAngle, 135)}deg,${rgba(S.bgColor, a)},${rgba(T.bgColor2, a)})`
    : rgba(S.bgColor, a));
  const bw = Math.max(0, n(T.borderW, 0)), ba = Math.max(0, Math.min(100, n(T.borderAlpha, 100))) / 100;
  set("--bw", bw + "px");
  set("--ringbg", bw > 0
    ? (T.borderMode === "gradient"
        ? `linear-gradient(${n(T.borderAngle, 135)}deg,${rgba(T.borderColor, ba)},${rgba(T.borderColor2, ba)})`
        : rgba(T.borderColor, ba))
    : "none");
  const glow = Math.max(0, n(T.glowSize, 0)), sh = Math.max(0, n(T.shadowSize, 0));
  const bs = [], ds = [];
  if (glow > 0) { bs.push(`0 0 ${glow}px ${rgba(T.glowColor, 0.9)}`); ds.push(`drop-shadow(0 0 ${glow}px ${rgba(T.glowColor, 0.9)})`); }
  if (sh > 0) { bs.push(`0 ${Math.round(sh / 3)}px ${sh}px rgba(0,0,0,.55)`); ds.push(`drop-shadow(0 ${Math.round(sh / 3)}px ${Math.round(sh / 2)}px rgba(0,0,0,.55))`); }
  set("--glow", bs.join(",") || "none"); set("--pglow", ds.join(" ") || "none");

  // градиент поверх подложки
  const ga = Math.max(0, Math.min(100, n(T.gradAlpha, 35))) / 100;
  set("--gl", T.gradOn ? `linear-gradient(${n(T.gradAngle, 90)}deg,${rgba(T.gradC1, ga)},${rgba(T.gradC2, ga)})` : "none");

  // PNG-подложка
  const png = T.base === "png" && !!S.skin;
  const mode = S.skinMode || "slice";
  root.classList.toggle("png", png);
  root.classList.toggle("stretch", png && mode === "stretch");
  root.classList.toggle("cover", png && mode === "cover");
  const sl = [n(S.slT, 24), n(S.slR, 24), n(S.slB, 24), n(S.slL, 24)];
  set("--slt", sl[0]); set("--slr", sl[1]); set("--slb", sl[2]); set("--sll", sl[3]);
  const k = mode === "native" ? 1 : n(S.skinScale, 1);
  const slicing = png && (mode === "slice" || mode === "native");
  set("--it", slicing ? sl[0] * k + "px" : "0px"); set("--ir", slicing ? sl[1] * k + "px" : "0px");
  set("--ib", slicing ? sl[2] * k + "px" : "0px"); set("--il", slicing ? sl[3] * k + "px" : "0px");
  const sk = png ? S.skin : "";
  if (root._sk !== sk) {
    root._sk = sk;
    if (sk) set("--skin", `url("/files/skins/${encodeURIComponent(sk)}")`); else set("--skin", "none");
  }
  return o.font ? setFont(root, S.font, S.fontBase) : Promise.resolve();
};

/* ---------- смайлы ---------- */
BK.freeze = function (img) {          // статичный первый кадр: браузер не декодирует анимацию каждый кадр
  const go = () => {
    try {
      const c = document.createElement("canvas");
      c.width = img.naturalWidth; c.height = img.naturalHeight; c.className = img.className; c.title = img.alt;
      c.getContext("2d").drawImage(img, 0, 0);
      if (img.parentNode) img.replaceWith(c);
    } catch (_) {}
  };
  if (img.complete && img.naturalWidth) go(); else img.addEventListener("load", go, {once: true});
};

BK.renderParts = function (parts, host, animated) {
  let lastBase = null;
  const all = [];
  for (const p of parts) {
    if (p.t === "x") { host.appendChild(document.createTextNode(p.v)); lastBase = null; continue; }
    if (!p.u || !p.u.startsWith("/files/emotes/")) continue;
    const img = new Image();
    img.className = "emote"; img.src = p.u; img.alt = p.n; img.decoding = "async"; img.draggable = false;
    if (p.z && lastBase) {
      let w = lastBase.parentNode;
      if (!w.classList || !w.classList.contains("zwrap")) {
        w = el("span", "zwrap");
        lastBase.replaceWith(w); w.appendChild(lastBase);
      }
      img.className = "emote zw"; w.appendChild(img);
    } else { host.appendChild(img); lastBase = img; }
    all.push(img);
  }
  if (!animated) for (const i of all) BK.freeze(i);
};

/* ---------- эффекты ников ---------- */
function applyFx(fx, name, text, msg) {
  const gs = Math.max(0, Math.min(60, +fx.glowSize || 0)) + "px";
  const gc = okColor(fx.glowColor) ? fx.glowColor : "#ffffff";
  const targets = fx.onText ? [name, text] : [name];
  if (okColor(fx.nameColor) && !fx.gradient) name.style.setProperty("color", fx.nameColor, "important");
  for (const t of targets) {
    if (fx.gradient && okColor(fx.c1) && okColor(fx.c2)) {
      const stops = [fx.c1, fx.c2];
      if (okColor(fx.c3)) stops.push(fx.c3);
      if (fx.flow) stops.push(fx.c1);
      t.style.setProperty("--g", stops.join(","));
      t.classList.add("fx-grad");
      if (fx.flow) t.classList.add("flow");
    }
    if (fx.glow) {
      t.style.setProperty("--gs", gs); t.style.setProperty("--gc", gc);
      t.classList.add("fx-glow");
      if (fx.pulse) t.classList.add("fx-pulse");
    }
  }
  if (fx.bubbleGlow) msg.style.filter = `drop-shadow(0 0 ${gs} ${gc})`;
}

/* ---------- декор ---------- */
BK.setDecorVars = function (w, d) {
  const v = (k, x) => w.style.setProperty(k, x);
  v("--ax", [0, 50, 100].includes(+d.ax) ? +d.ax : 50); v("--ay", [0, 50, 100].includes(+d.ay) ? +d.ay : 50);
  v("--ox", n(d.ox, 0)); v("--oy", n(d.oy, 0)); v("--w", Math.max(2, n(d.w, 40)));
  v("--rot", n(d.rot, 0)); v("--op", Math.max(0, Math.min(100, n(d.op, 100)))); v("--fl", d.flip ? -1 : 1);
};

BK.decorEl = function (d, lite, o) {
  o = o || {};
  const glyph = d.kind === "glyph";
  const layer = ["under", "back", "front"].includes(d.layer) ? d.layer : "front";
  const anim = !lite && ["float", "spin", "pulse", "swing", "blink"].includes(d.anim) ? " a-" + d.anim : "";
  const w = el("div", "dc " + (glyph ? "g" : "img") + " " + layer + anim);
  BK.setDecorVars(w, d);
  const da = el("div", "da");
  let di;
  if (glyph) {
    di = el("span", "di", d.glyph || "★");
    di.style.setProperty("--c", okColor(d.color) ? d.color : "#ffffff");
  } else {
    if (!d.file) return document.createComment("");
    di = new Image();
    di.className = "di"; di.alt = ""; di.draggable = false; di.decoding = "async";
    di.src = "/files/decor/" + encodeURIComponent(d.file);
    di.onerror = () => { w.style.display = "none"; };
  }
  da.appendChild(di); w.appendChild(da);
  if (o.edit) {
    w.dataset.id = d.id; w.classList.add("edit");
    if (d.id === o.selected) w.classList.add("sel");
  }
  return w;
};

/* ---------- сборка сообщения ---------- */
/* значки у ника: b = стример, m = модератор, l = главный модератор.
   По умолчанию берём значки из Twitch (m.bd); у ника в «Эффектах ников» можно скрыть их или всегда показывать нужный. */
BK.badgeList = function (m, S, fx) {
  S = S || {};
  const k = (fx && fx.badge) || "auto";
  if (k === "none") return [];
  if (k === "b" || k === "m" || k === "l") return [k];
  if (S.badges === false) return [];
  const on = {b: S.bdB !== false, m: S.bdM !== false, l: S.bdL !== false};
  return (m.bd || []).filter(x => on[x]);
};
BK.BADGE_NAMES = {b: "Стример", m: "Модератор", l: "Главный модератор"};

BK.build = function (m, S, T, users, o) {
  o = o || {}; S = S || {};
  const decor = (T && T.decor) || [];
  const msg = el("div", "msg" + (m.me ? " me" : ""));
  msg.append(el("div", "bgl"), el("div", "gl"), el("div", "ring"));
  for (const d of decor) msg.append(BK.decorEl(d, BK.eff(S).lite, o));
  const name = el("span", "name", m.name);
  name.style.color = m.color;
  const text = el("span", "text");
  BK.renderParts(m.parts || [{t: "x", v: m.text || ""}], text, BK.eff(S).animEmotes);
  const fx = users && users[m.user];
  const nm = el("span", "nm");
  if (fx) {
    applyFx(fx, name, text, msg);
    if (fx.prefix) nm.append(el("span", "pfx", fx.prefix));
  }
  for (const b of BK.badgeList(m, S, fx)) { const i = el("span", "bdg " + b); i.title = BK.BADGE_NAMES[b]; nm.append(i); }
  nm.append(name);
  msg.append(nm, el("span", "sep", ": "), text);
  return msg;
};

g.BubbleKit = BK;
})(window);
