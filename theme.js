/* Тема приложения: dark / light / auto. Подключается первым в <head>, чтобы не мигал белый фон. */
(function () {
  const mq = window.matchMedia ? matchMedia("(prefers-color-scheme: light)") : null;
  let mode = "dark";
  try { mode = localStorage.getItem("appTheme") || "dark"; } catch (_) {}
  const resolve = m => m === "auto" ? (mq && mq.matches ? "light" : "dark") : (m === "light" ? "light" : "dark");
  const apply = () => { document.documentElement.dataset.theme = resolve(mode); };
  window.AppTheme = {
    get mode() { return mode; },
    set(m) { if (!["dark", "light", "auto"].includes(m)) return; mode = m; try { localStorage.setItem("appTheme", m); } catch (_) {} apply(); },
    sync(m) { if (m && m !== mode) this.set(m); },   // значение с сервера (общее для окна, дока и конструктора)
  };
  if (mq && mq.addEventListener) mq.addEventListener("change", () => { if (mode === "auto") apply(); });
  apply();
})();
