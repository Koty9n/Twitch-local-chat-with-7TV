/* Быстрые настройки: масштаб, оптимизация, шрифт, пресеты.
   Используется и в доке OBS (/dock), и в окне программы (/app).
   Quick.mount(host, {onChange(kind), toast(msg, ok)}) */
"use strict";
const Quick = (() => {
  const PERF = [
    ["eco", "Эконом", "Статичные смайлы, без переливаний и пульсаций, blur заменён на плавное появление. Минимум нагрузки."],
    ["balanced", "Баланс", "Смайлы анимированы, но бесконечных анимаций (переливание ника, пульсация, анимации декора) нет."],
    ["full", "Максимум", "Всё включено: переливание, пульсация, анимации декора, blur. Самая красивая картинка, нагрузка выше."],
  ];
  const CSS = `
.qk{display:flex;flex-direction:column;gap:14px}
.qk .qb{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.qk h4{margin:0 0 10px;font-size:13px;font-weight:700;color:var(--text);display:flex;justify-content:space-between;align-items:center}
.qk h4 b{color:var(--accent);font-weight:700}
.qk input[type=range]{width:100%;margin:4px 0}
.qk .seg{display:grid;grid-template-columns:repeat(3,1fr)}
.qk .seg button{padding:9px 4px}
.qk .qh{margin-top:9px;color:var(--faint);font-size:12px;line-height:1.45}
.qk .row{display:flex;gap:8px;align-items:center}
.qk .row>*{min-width:0}
.qk .chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.qk .chip{display:inline-flex;align-items:stretch;border:1px solid var(--btn-line);border-radius:99px;overflow:hidden;background:var(--btn)}
.qk .chip button{border:0;border-radius:0;background:none;padding:6px 12px}
.qk .chip button.x{padding:6px 10px;color:var(--faint);border-left:1px solid var(--btn-line)}
.qk .chip button.x:hover{color:var(--err)}
.qk .chip.on{border-color:var(--accent);background:var(--accent-soft)}
.qk .chip button.s{padding:6px 9px;color:var(--faint);border-left:1px solid var(--btn-line);font-size:12px}
.qk .chip button.s:hover{color:var(--accent)}
.qk .imp{margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
.qk .imp h5{margin:0 0 8px;font-size:12px;font-weight:700;color:var(--text)}
.qk .imp textarea{width:100%;min-height:54px;resize:vertical;font:12px/1.4 Consolas,monospace}
.qk .imp .row{margin-top:8px;flex-wrap:wrap}
.qk .qb.drop{outline:2px dashed var(--accent);outline-offset:-6px;background:var(--accent-soft)}
.qk .qb{position:relative}
.qk .dz{display:none;position:absolute;inset:0;align-items:center;justify-content:center;border-radius:14px;background:var(--accent-soft);color:var(--accent);font-weight:700;font-size:14px;pointer-events:none;text-align:center;padding:12px}
.qk .qb.drop .dz{display:flex}
.qk .none{color:var(--faint);font-size:12px}
.qk .game{width:100%;padding:12px;font-weight:700;font-size:14px}
.qk .game.on{background:var(--ok);border-color:var(--ok);color:#fff}
.qk .rst{padding:3px 9px;font-size:12px}
`;
  const BASES = ["Segoe UI", "Arial", "Arial Black", "Verdana", "Tahoma", "Trebuchet MS", "Calibri", "Georgia", "Times New Roman", "Palatino Linotype", "Courier New", "Consolas", "Impact", "Comic Sans MS"];
  let host, opt, S = {}, assets = {fonts: []}, presets = [], saveT = 0, pend = {}, active = "";
  const $ = s => host.querySelector(s);
  const E = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; };
  const api = async (url, o = {}) => {
    const r = await fetch(url, o); const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || r.statusText); return j;
  };
  const post = (url, body) => api(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})});
  const say = (m, ok) => (opt.toast || (() => {}))(m, ok);

  async function copyText(t) {
    try { await navigator.clipboard.writeText(t); return; } catch (_) { /* в доке OBS буфер может быть закрыт: запасной способ ниже */ }
    const ta = E("textarea"); ta.value = t; ta.style.cssText = "position:fixed;left:-9999px;top:0"; document.body.append(ta);
    ta.select(); let ok = false; try { ok = document.execCommand("copy"); } catch (_) {} ta.remove();
    if (!ok) throw new Error("Не удалось скопировать. Используй кнопку «txt».");
  }
  function saveText(name, text) {
    const a = E("a"); a.href = URL.createObjectURL(new Blob([text], {type: "text/plain;charset=utf-8"})); a.download = name;
    document.body.append(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  function exportNote(msg, r) {
    const m = (r.missing || []).length;
    return msg + (r.embedded && r.embedded.length ? ` (с файлами: ${r.embedded.length})` : "") + (m ? `. Не вложены (нет файла или слишком большие): ${r.missing.join(", ")}` : "");
  }
  async function doImport(code, quiet) {
    const r = await post("/api/presets", {action: "import", code});
    presets = r.presets; active = r.name; chipsFill(); opt.onChange && opt.onChange("presets");
    if (!quiet) say("Пресет добавлен: " + r.name + (r.added.length ? ` (файлов: ${r.added.length})` : "") + (r.missing.length ? ". Нет файлов: " + r.missing.join(", ") : ""), true);
    return r;
  }
  // один или несколько файлов .txt (выбор или перетаскивание)
  async function importFiles(list) {
    const files = [...list].slice(0, 10), ok = [], bad = [];
    for (const f of files) {
      if (f.size > 16 << 20) { bad.push(f.name + ": файл слишком большой"); continue; }
      try { ok.push((await doImport(await f.text(), true)).name); } catch (e) { bad.push(f.name + ": " + e.message); }
    }
    if (!files.length) return;
    if (!bad.length && ok.length === 1) say("Пресет добавлен: " + ok[0], true);
    else say((ok.length ? "Добавлено пресетов: " + ok.length + " (" + ok.join(", ") + ")" : "") + (bad.length ? (ok.length ? ". " : "") + "Не удалось: " + bad.join("; ") : ""), !!ok.length && !bad.length);
  }
  const hasFiles = e => e.dataTransfer && [...(e.dataTransfer.types || [])].some(t => t === "Files" || t === "text/plain");
  function dropZone(el) {
    let depth = 0;
    const off = () => { depth = 0; el.classList.remove("drop"); };
    el.addEventListener("dragenter", e => { if (!hasFiles(e)) return; e.preventDefault(); depth++; el.classList.add("drop"); });
    el.addEventListener("dragover", e => { if (!hasFiles(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = "copy"; });
    el.addEventListener("dragleave", e => { if (--depth <= 0) off(); });
    el.addEventListener("drop", async e => {
      if (!hasFiles(e)) return; e.preventDefault(); off();
      const fl = e.dataTransfer.files;
      if (fl && fl.length) return importFiles(fl);
      const t = (e.dataTransfer.getData("text/plain") || "").trim();   // перетащили выделенный текст с кодом
      if (t) try { await doImport(t); } catch (er) { say(er.message); }
    });
  }

  function patch(k, v) {
    S[k] = v; pend[k] = v; clearTimeout(saveT);
    saveT = setTimeout(() => {
      const body = pend; pend = {};
      post("/api/config", {style: body}).then(() => opt.onChange && opt.onChange("style", body)).catch(e => say(e.message));
    }, 200);
  }

  function build() {
    host.textContent = ""; host.classList.add("qk");
    // --- режим игры ---
    const b0 = E("div", "qb"); const g = E("button", "game", "🎮 Режим игры: выкл"); g.id = "qGame";
    g.onclick = () => { patch("game", !S.game); markGame(); };
    b0.append(g, E("div", "qh", "Одной кнопкой отключает все анимации, свечения и анимированные смайлы. Ничего не стирает: выключишь, и вид вернётся. Включай на время игры."));
    // --- масштаб ---
    const b1 = E("div", "qb"); const h1 = E("h4"); h1.append(E("span", "", "Масштаб чата на экране"));
    const val = E("b", "", "100%"); val.id = "qScaleVal";
    const rst = E("button", "rst", "100%"); rst.title = "Сбросить масштаб";
    const hr = E("span"); hr.style.cssText = "display:flex;gap:8px;align-items:center"; hr.append(val, rst); h1.append(hr);
    const rg = E("input"); rg.type = "range"; rg.min = 50; rg.max = 200; rg.step = 5; rg.id = "qScale";
    rg.oninput = () => { val.textContent = rg.value + "%"; patch("uiScale", +rg.value); };
    rst.onclick = () => { rg.value = 100; rg.oninput(); };
    b1.append(h1, rg, E("div", "qh", "Увеличивает или уменьшает весь чат целиком: текст, рамки, декор. Область в OBS не меняется."));
    // --- оптимизация ---
    const b2 = E("div", "qb"); b2.append(E("h4", "", "Оптимизация"));
    const seg = E("div", "seg"); seg.id = "qPerf";
    for (const [id, name] of PERF) {
      const b = E("button", "", name); b.dataset.p = id;
      b.onclick = () => { patch("perf", id); mark(); };
      seg.append(b);
    }
    const ph = E("div", "qh"); ph.id = "qPerfHint";
    b2.append(seg, ph);
    // --- шрифт ---
    const b3 = E("div", "qb"); b3.append(E("h4", "", "Шрифт"));
    const fs = E("select"); fs.id = "qFont";
    fs.onchange = () => {
      if (fs.value.startsWith("file:")) patch("font", fs.value.slice(5));
      else { patch("fontBase", fs.value.slice(5)); patch("font", ""); }
    };
    b3.append(fs, E("div", "qh", "Больше шрифтов: вкладка «Вид» в программе, кнопка «＋» рядом со списком."));
    // --- пресеты ---
    const b4 = E("div", "qb"); b4.append(E("h4", "", "Пресеты"));
    const chips = E("div", "chips"); chips.id = "qChips";
    const row = E("div", "row"); const nm = E("input"); nm.type = "text"; nm.id = "qName"; nm.placeholder = "Название нового пресета"; nm.maxLength = 40;
    const sv = E("button", "", "💾 Сохранить"); sv.title = "Сохранить текущие настройки (с таким же названием обновляет)";
    sv.onclick = async () => {
      const name = nm.value.trim();
      if (!name) { say("Введи название пресета"); nm.focus(); return; }
      try {
        await flush();
        const had = presets.includes(name);
        const r = await post("/api/presets", {action: "save", name});
        presets = r.presets; active = name; nm.value = ""; chipsFill(); say(had ? "Пресет обновлён: " + name : "Пресет сохранён: " + name, true);
        opt.onChange && opt.onChange("presets");
      } catch (e) { say(e.message); }
    };
    nm.addEventListener("keydown", e => { if (e.key === "Enter") sv.click(); });
    row.append(nm, sv); nm.style.flex = "1";
    b4.append(chips, row, E("div", "qh", "Пресет запоминает внешний вид: конструктор, шрифт, масштаб, анимации и оптимизацию. Подключение и фильтры не затрагиваются. Каждый пресет лежит файлом .txt в папке data\\presets. «Код» копирует его, чтобы отправить другому человеку, вместе с подложкой, декором и шрифтом (если они небольшие)."));
    const imp = E("div", "imp"); imp.append(E("h5", "", "Получить пресет от другого человека"));
    const ta = E("textarea"); ta.id = "qCode"; ta.placeholder = "Вставь код пресета (начинается с TC7TV1:) или перетащи сюда файл .txt"; ta.spellcheck = false;
    const r2 = E("div", "row");
    const bi = E("button", "pri", "Добавить по коду"); bi.id = "qImport";
    bi.onclick = async () => {
      const code = ta.value.trim();
      if (!code) { say("Вставь код пресета"); ta.focus(); return; }
      try { await doImport(code); ta.value = ""; } catch (e) { say(e.message); }
    };
    const bp = E("button", "", "Из буфера"); bp.title = "Вставить код из буфера обмена и добавить";
    bp.onclick = async () => {
      try { const t = (await navigator.clipboard.readText()).trim(); ta.value = t; if (t) await doImport(t), ta.value = ""; else say("Буфер пуст"); }
      catch (e) { say(e.name === "NotAllowedError" || e.name === "SecurityError" ? "Буфер недоступен: вставь код в поле вручную (Ctrl+V)" : e.message); }
    };
    const bf = E("button", "", "Из файла txt"); const fi = E("input"); fi.type = "file"; fi.accept = ".txt,text/plain"; fi.style.display = "none"; fi.id = "qFile";
    bf.onclick = () => fi.click();
    fi.multiple = true;
    fi.onchange = () => { const l = [...fi.files]; fi.value = ""; importFiles(l); };
    r2.append(bi, bp, bf, fi); imp.append(ta, r2);
    const dz = E("div", "dz", "Отпусти файл .txt, чтобы добавить пресет"); b4.append(imp, dz); dropZone(b4);
    host.append(b0, b1, b2, b3, b4);
  }

  async function flush() {            // дожидаемся отправки отложенных правок перед снимком пресета
    if (!Object.keys(pend).length) return;
    clearTimeout(saveT); const body = pend; pend = {};
    await post("/api/config", {style: body});
  }

  function markGame() {
    const g = $("#qGame"); g.classList.toggle("on", !!S.game);
    g.textContent = S.game ? "🎮 Режим игры: ВКЛ" : "🎮 Режим игры: выкл";
  }
  function mark() {
    markGame();
    for (const b of host.querySelectorAll("#qPerf button")) b.classList.toggle("on", b.dataset.p === S.perf);
    const p = PERF.find(x => x[0] === S.perf); $("#qPerfHint").textContent = p ? p[2] : "";
  }
  function chipsFill() {
    const c = $("#qChips"); c.textContent = "";
    if (!presets.length) { c.append(E("span", "none", "Пока нет сохранённых пресетов.")); return; }
    for (const name of presets) {
      const ch = E("span", "chip" + (name === active ? " on" : ""));
      const a = E("button", "", name); a.title = "Применить пресет";
      a.onclick = async () => {
        try {
          await post("/api/presets", {action: "apply", name}); active = name;
          await load(); opt.onChange && opt.onChange("preset");
        } catch (e) { say(e.message); }
      };
      const cp = E("button", "s", "Код"); cp.title = "Скопировать код пресета, чтобы отправить другому человеку";
      cp.onclick = async () => {
        try { const r = await post("/api/presets", {action: "export", name}); await copyText(r.code); say(exportNote("Код пресета «" + name + "» скопирован", r), true); }
        catch (e) { say(e.message); }
      };
      const tx = E("button", "s", "txt"); tx.title = "Скачать пресет файлом .txt";
      tx.onclick = async () => {
        try { const r = await post("/api/presets", {action: "export", name}); saveText(name.replace(/[^\w\-. ]+/g, "_") + ".txt", r.code); say(exportNote("Файл пресета сохранён", r), true); }
        catch (e) { say(e.message); }
      };
      const x = E("button", "x", "✕"); x.title = "Удалить пресет";
      x.onclick = async () => {
        if (x.dataset.arm !== "1") { x.dataset.arm = "1"; x.textContent = "удалить?"; setTimeout(() => { x.dataset.arm = ""; x.textContent = "✕"; }, 2500); return; }
        try { const r = await post("/api/presets", {action: "delete", name}); presets = r.presets; if (active === name) active = ""; chipsFill(); opt.onChange && opt.onChange("presets"); }
        catch (e) { say(e.message); }
      };
      ch.append(a, cp, tx, x); c.append(ch);
    }
  }
  function fill() {
    const rg = $("#qScale"), val = $("#qScaleVal");
    if (document.activeElement !== rg) { rg.value = S.uiScale ?? 100; }
    val.textContent = (S.uiScale ?? 100) + "%";
    const fs = $("#qFont");
    if (document.activeElement !== fs) {
      fs.textContent = "";
      const g1 = document.createElement("optgroup"); g1.label = "Готовые шрифты";
      for (const f of BASES) { const o = new Option(f, "base:" + f); o.style.fontFamily = `"${f}"`; g1.append(o); }
      fs.append(g1);
      if ((assets.fonts || []).length) { const g2 = document.createElement("optgroup"); g2.label = "Свои файлы";
        for (const n of assets.fonts) g2.append(new Option(n.replace(/\.[^.]+$/, ""), "file:" + n)); fs.append(g2); }
      fs.value = S.font ? "file:" + S.font : "base:" + (S.fontBase || "Segoe UI");
    }
    mark(); chipsFill();
  }
  async function load() {
    const c = await api("/api/config");
    if (Object.keys(pend).length) c.style = Object.assign({}, c.style, pend);   // не затираем то, что ещё не ушло на сервер
    if (window.AppTheme && c.app) AppTheme.sync(c.app.theme);
    S = c.style; assets = c.assets; presets = c.presets || []; fill(); return c;
  }
  function mount(h, o) {
    host = h; opt = o || {};
    if (!mount.once) {       // файл, брошенный мимо поля, не должен открываться в окне вместо пресета
      mount.once = true;
      for (const t of ["dragover", "drop"]) window.addEventListener(t, e => { if (e.dataTransfer && [...(e.dataTransfer.types || [])].includes("Files")) e.preventDefault(); });
    }
    if (!document.getElementById("qkcss")) { const st = E("style"); st.id = "qkcss"; st.textContent = CSS; document.head.append(st); }
    build(); return load();
  }
  return {mount, load, get style() { return S; }};
})();
