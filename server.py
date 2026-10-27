#!/usr/bin/env python3
"""
Twitch chat 7TV
================
Один лёгкий процесс (только aiohttp):
  * читает чат Twitch по IRC-WebSocket (анонимно или с OAuth-токеном)
  * подгружает 7TV (глобальные + канальные) и нативные смайлы Twitch,
    кеширует их на диск и в память
  * раздаёт /overlay (Browser Source в OBS) и /dock (Custom Browser Dock)
  * хранит загруженные PNG-подложки и шрифты в папке data/

Запуск:  python server.py
"""
from __future__ import annotations

import asyncio
import collections
import json
import logging
import logging.handlers
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger("chat")
APP_VERSION = "1.5.0"
APP_NAME = "Twitch chat 7TV"


def fatal(msg: str) -> None:
    """Ошибка запуска. Без консоли (pythonw/exe) показываем окно Windows, иначе печатаем."""
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "Twitch chat 7TV", 0x10)
        elif sys.stderr:
            print(msg, file=sys.stderr)
    except Exception:
        pass
    sys.exit(1)


try:
    from aiohttp import ClientSession, ClientTimeout, WSMsgType, web
except ImportError:
    fatal("Не установлена библиотека aiohttp.\nЗапусти install.bat ещё раз (нужен интернет).")

# RES: где лежат overlay.html / dock.html; APP: рядом с приложением (для data/)
if getattr(sys, "frozen", False):  # собранный .exe (PyInstaller)
    RES = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    BASE = Path(sys.executable).resolve().parent
else:
    RES = BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
SKINS, FONTS, EMOTES, DECOR = DATA / "skins", DATA / "fonts", DATA / "emotes", DATA / "decor"
for _d in (SKINS, FONTS, EMOTES, DECOR):
    _d.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = DATA / "config.json"

IRC_URL = "wss://irc-ws.chat.twitch.tv:443"
SEVENTV_GLOBAL = "https://7tv.io/v3/emote-sets/global"
SEVENTV_USER = "https://7tv.io/v3/users/twitch/{}"
SEVENTV_CDN = "https://cdn.7tv.app/emote/{}/2x.webp"
TWITCH_CDN = "https://static-cdn.jtvnw.net/emoticons/v2/{}/default/dark/2.0"

PERF_MODES = ("eco", "balanced", "full")
# готовые системные шрифты (стеки с запасными вариантами собирает bubble.js)
FONT_BASES = ("Segoe UI", "Arial", "Arial Black", "Verdana", "Tahoma", "Trebuchet MS", "Calibri", "Georgia",
              "Times New Roman", "Palatino Linotype", "Courier New", "Consolas", "Impact", "Comic Sans MS")
BADGE_IDS = {"broadcaster": "b", "moderator": "m", "lead_moderator": "l"}
# что входит в пресет: внешний вид (без подключения, фильтров и переключателей смайлов)
PRESET_SKIP = {"game", "use7tv", "useTwitchEmotes", "hideCommands", "ignoredUsers", "blockedWords"}
MAX_PRESETS = 30

ANIMS_IN = {"slide", "up", "pop", "fade", "bounce", "blur", "flip", "wipe", "none"}
ANIMS_OUT = {"fade", "slide", "shrink", "none"}
PALETTE = ["#ff4d6d", "#ff9f1c", "#2ec4b6", "#4cc9f0", "#9d4edd", "#80ed99", "#f72585", "#ffd166"]

# ----------------------------------------------------------------------------
# Журнал: кольцевой буфер для окна программы + файл data/app.log (консоли нет)
# ----------------------------------------------------------------------------
class LogRing(logging.Handler):
    def __init__(self, size: int = 400) -> None:
        super().__init__(logging.INFO)
        self.lines: collections.deque = collections.deque(maxlen=size)
        self.n = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.n += 1
            self.lines.append((self.n, time.strftime("%H:%M:%S", time.localtime(record.created)),
                               record.levelname, record.getMessage()))
        except Exception:
            pass

    def since(self, n: int) -> list:
        return [list(x) for x in self.lines if x[0] > n]


LOG_RING = LogRing()


def setup_logging(console: bool) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
    root.addHandler(LOG_RING)
    try:
        fh = logging.handlers.RotatingFileHandler(DATA / "app.log", maxBytes=512 << 10, backupCount=1, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass
    if console and sys.stderr:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

    def hook(et, ev, tb):  # необработанное исключение попадает в журнал, а не пропадает вместе с окном
        log.error("Необработанная ошибка", exc_info=(et, ev, tb))
    sys.excepthook = hook


# ----------------------------------------------------------------------------
# Конфиг
# ----------------------------------------------------------------------------
STYLE = {
    # текст
    "font": "", "fontBase": "Segoe UI", "fontSize": 28, "fontWeight": 600, "nameWeight": 800, "textColor": "#ffffff",
    # значки у ника: streamer / модератор / главный модератор (рисуются самой программой)
    "badges": True, "bdB": True, "bdM": True, "bdL": True,
    "nameMode": "twitch", "nameColor": "#ffcc00", "shadow": True, "emoteScale": 1.5, "textScale": 100,
    # подложка: PNG с 9-slice нарезкой (px исходного изображения)
    "skin": "", "skinMode": "slice", "slT": 24, "slR": 24, "slB": 24, "slL": 24, "skinScale": 1.0,
    "padT": 6, "padR": 10, "padB": 6, "padL": 10,
    # запасной фон, если PNG не выбран
    "bgColor": "#101018", "bgOpacity": 0.6, "radius": 14,
    # анимации и поведение
    "animIn": "slide", "animOut": "fade", "animMs": 450,
    "lifetime": 30, "maxMessages": 8, "gap": 8, "anchor": "bottom", "align": "left",
    # производительность: eco / balanced / full (см. PERF_MODES); uiScale = масштаб всего чата на экране, %
    "perf": "balanced", "uiScale": 100,
    # защита от просадок FPS: guard = автоупрощение при подтормаживании, maxPerSec = лимит новых сообщений в секунду
    "guard": True, "maxPerSec": 5,
    # режим игры: временно отключает все анимации и эффекты (в пресеты не входит)
    "game": False,
    # фильтры и смайлы
    "use7tv": True, "useTwitchEmotes": True, "hideCommands": True,
    "ignoredUsers": "streamelements, nightbot, moobot, fossabot, streamlabs",
    "blockedWords": "",
}
# Тема сообщения (конструктор): заливка, контур, свечение, градиент поверх, раскладка текста, декор
THEME = {
    "frame": "", "base": "css", "bgMode": "solid", "bgColor2": "#2a2a4a", "bgAngle": 135,
    "borderW": 0, "borderMode": "solid", "borderColor": "#ffffff", "borderColor2": "#4cc9f0",
    "borderAngle": 135, "borderAlpha": 100,
    "glowSize": 0, "glowColor": "#7a5cff", "shadowSize": 0,
    "gradOn": False, "gradC1": "#ff4d6d", "gradC2": "#4cc9f0", "gradAngle": 90, "gradAlpha": 35,
    "layout": "inline", "textAlign": "left", "maxW": 100, "minW": 0, "decorScale": 100,
    "decor": [],
}
THEME_ENUMS = {"base": {"css", "png"}, "bgMode": {"solid", "gradient"}, "borderMode": {"solid", "gradient"},
               "layout": {"inline", "stacked"}, "textAlign": {"left", "center", "right"}}
THEME_RANGES = {"bgAngle": (0, 360), "borderW": (0, 40), "borderAngle": (0, 360), "borderAlpha": (0, 100),
                "glowSize": (0, 80), "shadowSize": (0, 80), "gradAngle": (0, 360), "gradAlpha": (0, 100),
                "maxW": (20, 100), "minW": (0, 1200), "decorScale": (20, 300)}
THEME_COLORS = {"bgColor2", "borderColor", "borderColor2", "glowColor", "gradC1", "gradC2"}
DECOR_ANIMS = {"none", "float", "spin", "pulse", "swing", "blink"}
DECOR_LAYERS = {"under", "back", "front"}

DEFAULT_CONFIG = {"channel": "", "nick": "", "oauth": "", "port": 8787, "style": STYLE, "users": {},
                  "theme": THEME, "presets": {}, "app": {}}

# настройки самой программы (не внешнего вида): окно, трей, обновления, кеш
APP_DEFAULT = {"theme": "dark", "onClose": "tray", "checkUpdates": True, "updateSource": "", "cacheMb": 400}


def sanitize_app(raw, old=None) -> dict:
    out = dict(APP_DEFAULT)
    out.update(old or {})
    if isinstance(raw, dict):
        if raw.get("theme") in ("dark", "light", "auto"):
            out["theme"] = raw["theme"]
        if raw.get("onClose") in ("tray", "quit"):
            out["onClose"] = raw["onClose"]
        if "checkUpdates" in raw:
            out["checkUpdates"] = bool(raw["checkUpdates"])
        if "updateSource" in raw:
            src = str(raw["updateSource"]).strip()[:200]
            out["updateSource"] = src if (re.fullmatch(r"[\w.\-]+/[\w.\-]+", src) or src.startswith("https://")) else ""
        if "cacheMb" in raw:
            try:
                out["cacheMb"] = max(50, min(5000, int(float(raw["cacheMb"]))))
            except (TypeError, ValueError):
                pass
    return out

# Эффекты ников: users = {"ник": {...USER_FX}}
USER_FX = {
    "prefix": "", "nameColor": "",
    "gradient": False, "c1": "#ff4d6d", "c2": "#4cc9f0", "c3": "", "flow": True,
    "glow": False, "glowColor": "#ffffff", "glowSize": 8, "pulse": False,
    "onText": False, "bubbleGlow": False,
    "badge": "auto",   # auto = по Twitch, none = скрыть значки, b / m / l = всегда показывать этот значок
}
COLOR_KEYS = {"nameColor", "c1", "c2", "c3", "glowColor"}
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def sanitize_users(raw) -> dict:
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for login, fx in list(raw.items())[:200]:
        login = str(login).strip().lower().lstrip("@")
        if not re.fullmatch(r"[a-z0-9_]{1,25}", login) or not isinstance(fx, dict):
            continue
        o = {}
        for k, d in USER_FX.items():
            v = fx.get(k, d)
            if k in COLOR_KEYS:
                o[k] = v if isinstance(v, str) and HEX_RE.match(v) else ("" if k in ("c3", "nameColor") else d)
            elif isinstance(d, bool):
                o[k] = bool(v)
            elif isinstance(d, int):
                try:
                    o[k] = max(0, min(60, int(float(v))))
                except (TypeError, ValueError):
                    o[k] = d
            elif k == "badge":
                o[k] = v if v in ("auto", "none", "b", "m", "l") else "auto"
            else:
                o[k] = str(v)[:8]
        out[login] = o
    return out


def _int(v, lo, hi, d):
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError, OverflowError):
        return d


def _color(v, d):
    return v if isinstance(v, str) and HEX_RE.match(v) else d


def sanitize_decor(raw) -> list:
    out: list = []
    if not isinstance(raw, list):
        return out
    seen: set = set()
    for i, it in enumerate(raw[:40]):
        if not isinstance(it, dict):
            continue
        iid = re.sub(r"[^a-z0-9]", "", str(it.get("id", "")).lower())[:12] or f"d{i}{random.randrange(10 ** 5)}"
        while iid in seen:
            iid += "x"
        seen.add(iid)
        ax, ay = _int(it.get("ax"), 0, 100, 50), _int(it.get("ay"), 0, 100, 50)
        out.append({
            "id": iid,
            "kind": it.get("kind") if it.get("kind") in ("image", "glyph") else "image",
            "file": Path(str(it.get("file", ""))).name[:80],
            "glyph": str(it.get("glyph", ""))[:12],
            "color": _color(it.get("color"), "#ffffff"),
            "ax": ax if ax in (0, 50, 100) else 50, "ay": ay if ay in (0, 50, 100) else 50,
            "ox": _int(it.get("ox"), -800, 800, 0), "oy": _int(it.get("oy"), -800, 800, 0),
            "w": _int(it.get("w"), 4, 800, 40), "rot": _int(it.get("rot"), -360, 360, 0),
            "op": _int(it.get("op"), 0, 100, 100), "flip": bool(it.get("flip")),
            "layer": it.get("layer") if it.get("layer") in DECOR_LAYERS else "front",
            "anim": it.get("anim") if it.get("anim") in DECOR_ANIMS else "none",
        })
    return out


def sanitize_theme(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out: dict = {}
    for k, d in THEME.items():
        v = raw.get(k, d)
        if k == "decor":
            out[k] = sanitize_decor(v)
        elif k == "frame":
            out[k] = re.sub(r"[^a-z0-9_]", "", str(v).lower())[:24]
        elif k in THEME_ENUMS:
            out[k] = v if v in THEME_ENUMS[k] else d
        elif k in THEME_COLORS:
            out[k] = _color(v, d)
        elif k in THEME_RANGES:
            out[k] = _int(v, *THEME_RANGES[k], d)
        else:
            out[k] = bool(v)
    return out


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg["app"] = dict(APP_DEFAULT)
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text("utf-8"))
            style = saved.pop("style", {})
            cfg.update({k: v for k, v in saved.items() if k in cfg and k != "style"})
            cfg["style"].update({k: v for k, v in style.items() if k in STYLE})
            if "perf" not in style and ("lite" in style or "animEmotes" in style):  # старые настройки
                lite, anim = style.get("lite", True), style.get("animEmotes", True)
                cfg["style"]["perf"] = "full" if not lite else ("balanced" if anim else "eco")
            if "theme" not in saved and cfg["style"].get("skin"):  # старый конфиг с PNG: сохраняем вид
                cfg["theme"]["base"] = "png"
            cfg["theme"] = sanitize_theme(cfg.get("theme"))
            cfg["users"] = sanitize_users(cfg.get("users"))
            cfg["style"] = coerce_style(STYLE, cfg["style"])
            cfg["presets"] = sanitize_presets(cfg.get("presets"))
            cfg["app"] = sanitize_app(saved.get("app"))
        except Exception as e:  # битый файл не должен ронять запуск
            log.warning("config.json не прочитан: %s", e)
    return cfg


def save_config(cfg: dict) -> None:
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(CONFIG_PATH)


def sanitize_presets(raw) -> dict:
    """Пресеты: {имя: {"style": {...}, "theme": {...}}}. Всё прогоняется через те же проверки, что и обычные настройки."""
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for name, v in list(raw.items())[:MAX_PRESETS]:
        name = str(name).strip()[:40]
        if not name or not isinstance(v, dict):
            continue
        st = coerce_style(STYLE, {k: x for k, x in (v.get("style") or {}).items() if k not in PRESET_SKIP})
        out[name] = {"style": {k: st[k] for k in STYLE if k not in PRESET_SKIP},
                     "theme": sanitize_theme(v.get("theme"))}
    return out


def coerce_style(old: dict, new: dict) -> dict:
    """Принимает только известные ключи, приводит типы, проверяет перечисления."""
    out = dict(old)
    for k, v in new.items():
        if k not in STYLE:
            continue
        d = STYLE[k]
        try:
            if isinstance(d, bool):
                out[k] = bool(v)
            elif isinstance(d, int):
                out[k] = max(0, min(5000, int(float(v))))
            elif isinstance(d, float):
                out[k] = max(0.0, min(100.0, float(v)))
            else:
                out[k] = str(v)[:500]
        except (TypeError, ValueError):
            continue
    if out["animIn"] not in ANIMS_IN:
        out["animIn"] = old["animIn"]
    if out["animOut"] not in ANIMS_OUT:
        out["animOut"] = old["animOut"]
    if out["nameMode"] not in ("twitch", "fixed"):
        out["nameMode"] = "twitch"
    if out["skinMode"] not in ("slice", "native", "stretch", "cover"):
        out["skinMode"] = "slice"
    out["textScale"] = max(20, min(300, out["textScale"]))  # % от размера шрифта
    out["uiScale"] = max(30, min(300, out["uiScale"]))      # % масштаб всего чата
    out["gap"] = min(out["gap"], 300)
    out["maxPerSec"] = max(1, min(30, out["maxPerSec"]))
    out["fontWeight"] = max(100, min(900, out["fontWeight"]))
    out["nameWeight"] = max(100, min(900, out["nameWeight"]))
    if out["fontBase"] not in FONT_BASES:
        out["fontBase"] = "Segoe UI"
    if out["perf"] not in PERF_MODES:
        out["perf"] = "balanced"
    if out["anchor"] not in ("top", "bottom"):
        out["anchor"] = "bottom"
    if out["align"] not in ("left", "right"):
        out["align"] = "left"
    for k in ("skin", "font"):  # только имя файла, без путей
        out[k] = Path(out[k]).name if out[k] else ""
    return out


# ----------------------------------------------------------------------------
# Хаб WebSocket (оверлеи)
# ----------------------------------------------------------------------------
class Hub:
    def __init__(self) -> None:
        self.clients: set[web.WebSocketResponse] = set()

    async def broadcast(self, obj: dict) -> None:
        if not self.clients:
            return
        data = json.dumps(obj, ensure_ascii=False)
        clients = list(self.clients)
        res = await asyncio.gather(*(c.send_str(data) for c in clients), return_exceptions=True)
        for c, r in zip(clients, res):
            if isinstance(r, Exception):
                self.clients.discard(c)


# ----------------------------------------------------------------------------
# Смайлы: 7TV + Twitch, кеш на диске и в памяти
# ----------------------------------------------------------------------------
class Emotes:
    EXT = {"image/webp": ".webp", "image/gif": ".gif", "image/png": ".png", "image/avif": ".avif"}

    def __init__(self, session: ClientSession) -> None:
        self.s = session
        self.glob: dict[str, tuple[str, int]] = {}
        self.chan: dict[str, tuple[str, int]] = {}
        self.room: str | None = None
        # ключ (например "7tv_ID") -> имя файла на диске
        self.files = {p.stem: p.name for p in EMOTES.iterdir() if p.is_file() and p.suffix != ".tmp"}
        self.sem = asyncio.Semaphore(6)      # живые сообщения
        self.bg_sem = asyncio.Semaphore(2)   # фоновая предзагрузка (не мешает живым сообщениям)
        self.failed: dict[str, float] = {}
        self._bg: set[asyncio.Task] = set()

    def lookup(self, word: str):
        return self.chan.get(word) or self.glob.get(word)

    def names(self) -> list[str]:
        return list(self.chan) + list(self.glob)

    async def _json(self, url: str):
        try:
            async with self.s.get(url, timeout=ClientTimeout(total=15)) as r:
                if r.status != 200:
                    log.warning("%s -> HTTP %s", url, r.status)
                    return None
                return await r.json(content_type=None)
        except Exception as e:
            log.warning("%s: %s", url, e)
            return None

    @staticmethod
    def _ingest(lst) -> dict[str, tuple[str, int]]:
        out = {}
        for e in lst or []:
            name, eid = e.get("name"), e.get("id")
            if not name or not eid:
                continue
            zw = 1 if (e.get("flags", 0) & 1) or ((e.get("data") or {}).get("flags", 0) & 256) else 0
            out[name] = (eid, zw)
        return out

    async def load_global(self) -> None:
        d = await self._json(SEVENTV_GLOBAL)
        if d:
            self.glob = self._ingest(d.get("emotes"))
            log.info("7TV global: %d смайлов", len(self.glob))

    async def load_channel(self, room_id: str) -> None:
        self.room = room_id
        d = await self._json(SEVENTV_USER.format(room_id))
        es = ((d or {}).get("emote_set") or {}).get("emotes")
        self.chan = self._ingest(es)
        log.info("7TV канал %s: %d смайлов", room_id, len(self.chan))
        # прогреваем кеш канальных смайлов в фоне
        t = asyncio.create_task(self._prefetch(list(self.chan.values())))
        self._bg.add(t)
        t.add_done_callback(self._bg.discard)

    async def _prefetch(self, items) -> None:
        await asyncio.sleep(3)  # сначала пусть стартует чат
        todo = [(eid, f"7tv_{eid}") for eid, _ in items if f"7tv_{eid}" not in self.files]
        await asyncio.gather(*(self.ensure(k, SEVENTV_CDN.format(eid), bg=True) for eid, k in todo),
                             return_exceptions=True)

    async def ensure(self, key: str, url: str, bg: bool = False) -> str | None:
        fn = self.files.get(key)
        if fn:
            return fn
        if self.failed.get(key, 0) > time.monotonic():
            return None
        # у фоновой загрузки своя очередь: иначе живое сообщение стоит за сотнями смайлов и теряется по таймауту
        async with (self.bg_sem if bg else self.sem):
            fn = self.files.get(key)
            if fn:
                return fn
            try:
                async with self.s.get(url, timeout=ClientTimeout(total=10)) as r:
                    if r.status != 200:
                        raise RuntimeError(f"HTTP {r.status}")
                    ext = self.EXT.get(r.headers.get("content-type", "").split(";")[0], ".webp")
                    data = await r.read()
                fn = key + ext
                tmp = EMOTES / (fn + ".tmp")
                tmp.write_bytes(data)
                tmp.replace(EMOTES / fn)
                self.files[key] = fn
                return fn
            except Exception as e:
                log.debug("emote %s: %s", key, e)
                self.failed[key] = time.monotonic() + 60
                return None

    async def build_parts(self, text: str, tw_ranges, use_7tv: bool) -> list[dict]:
        parts: list[dict] = []

        def add_text(s: str) -> None:
            if not s:
                return
            if parts and parts[-1]["t"] == "x":
                parts[-1]["v"] += s
            else:
                parts.append({"t": "x", "v": s})

        async def text_segment(seg: str) -> None:
            for tok in re.split(r"(\s+)", seg):
                if not tok:
                    continue
                hit = self.lookup(tok) if (use_7tv and not tok.isspace()) else None
                if hit:
                    fn = await self.ensure(f"7tv_{hit[0]}", SEVENTV_CDN.format(hit[0]))
                    if fn:
                        parts.append({"t": "e", "u": f"/files/emotes/{fn}", "n": tok, "z": hit[1]})
                        continue
                add_text(tok)

        pos = 0
        for a, b, eid in sorted(tw_ranges):
            if a < pos or b >= len(text) or a > b:
                continue
            await text_segment(text[pos:a])
            fn = await self.ensure(f"tw_{eid}", TWITCH_CDN.format(eid))
            if fn:
                parts.append({"t": "e", "u": f"/files/emotes/{fn}", "n": text[a:b + 1], "z": 0})
            else:
                add_text(text[a:b + 1])
            pos = b + 1
        await text_segment(text[pos:])
        return parts


# ----------------------------------------------------------------------------
# Twitch IRC
# ----------------------------------------------------------------------------
class AuthError(Exception):
    pass


def unescape_tag(v: str) -> str:
    return (v.replace("\\s", " ").replace("\\:", ";").replace("\\r", "").replace("\\n", "")
             .replace("\\\\", "\\"))


def parse_irc(line: str):
    tags: dict[str, str] = {}
    if line.startswith("@"):
        raw, line = line.split(" ", 1)
        for kv in raw[1:].split(";"):
            k, _, v = kv.partition("=")
            tags[k] = v
    prefix = ""
    if line.startswith(":"):
        prefix, _, line = line[1:].partition(" ")
    if " :" in line:
        head, trailing = line.split(" :", 1)
        params = head.split(" ") + [trailing]
    else:
        params = line.split(" ")
    return tags, prefix, params[0], params[1:]


def parse_badges(s: str) -> list:
    """badges=broadcaster/1,moderator/1 → ["b","m"]; главный модератор показывается вместо обычного."""
    got = {BADGE_IDS[x.split("/", 1)[0]] for x in s.split(",") if x.split("/", 1)[0] in BADGE_IDS}
    if "l" in got:
        got.discard("m")
    return [b for b in ("b", "l", "m") if b in got]


def parse_tw_emotes(s: str):
    out = []
    if not s:
        return out
    for grp in s.split("/"):
        eid, _, rngs = grp.partition(":")
        for r in rngs.split(","):
            a, _, b = r.partition("-")
            try:
                out.append((int(a), int(b), eid))
            except ValueError:
                pass
    return out


def set_status(app: web.Application, state: str, detail: str = "") -> None:
    app["status"] = {"state": state, "detail": detail}


def enqueue(app: web.Application, item: dict) -> None:
    q: asyncio.Queue = app["queue"]
    if q.full():  # защита от спам-рейдов: выкидываем самое старое
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            pass
    q.put_nowait(item)


async def irc_session(app: web.Application, channel: str) -> None:
    cfg = app["cfg"]
    token, nick = cfg["oauth"], cfg["nick"].lower()
    if token and nick:
        pw, nk = f"oauth:{token}", nick
    else:
        pw, nk = "SCHMOOPIIE", f"justinfan{random.randint(10000, 99999)}"
    set_status(app, "connecting", channel)
    async with app["session"].ws_connect(IRC_URL, heartbeat=None, receive_timeout=330) as ws:
        for cmd in ("CAP REQ :twitch.tv/tags twitch.tv/commands", f"PASS {pw}", f"NICK {nk}", f"JOIN #{channel}"):
            await ws.send_str(cmd)
        async for m in ws:
            if m.type != WSMsgType.TEXT:
                if m.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
                continue
            for line in m.data.split("\r\n"):
                if line:
                    await handle_irc(app, ws, line)


async def handle_irc(app: web.Application, ws, line: str) -> None:
    tags, prefix, cmd, args = parse_irc(line)
    hub: Hub = app["hub"]
    if cmd == "PING":
        await ws.send_str("PONG :" + (args[0] if args else "tmi.twitch.tv"))
    elif cmd == "001":
        set_status(app, "connected", app["cfg"]["channel"])
    elif cmd == "NOTICE" and "authentication failed" in line.lower():
        raise AuthError("Twitch отклонил токен/ник")
    elif cmd in ("ROOMSTATE", "PRIVMSG"):
        rid = tags.get("room-id")
        em: Emotes = app["emotes"]
        if rid and em.room != rid:
            em.room = rid
            asyncio.create_task(em.load_channel(rid))
        if cmd == "PRIVMSG" and len(args) >= 2:
            text = args[1]
            me = False
            if text.startswith("\x01ACTION "):
                text, me = text[8:].rstrip("\x01"), True
            user = prefix.split("!", 1)[0]
            enqueue(app, {
                "id": tags.get("id") or f"{time.time_ns()}",
                "user": user,
                "name": unescape_tag(tags.get("display-name", "")) or user,
                "color": tags.get("color", ""),
                "text": text, "me": me,
                "tw": parse_tw_emotes(tags.get("emotes", "")),
                "bd": parse_badges(tags.get("badges", "")),
            })
    elif cmd == "CLEARMSG" and tags.get("target-msg-id"):
        await hub.broadcast({"type": "delete", "id": tags["target-msg-id"]})
    elif cmd == "CLEARCHAT":
        if len(args) >= 2:
            await hub.broadcast({"type": "clear_user", "user": args[1].lower()})
        else:
            await hub.broadcast({"type": "clear"})


async def irc_supervisor(app: web.Application) -> None:
    restart: asyncio.Event = app["irc_restart"]
    backoff = 1
    while True:
        restart.clear()
        channel = app["cfg"]["channel"]
        if not channel:
            set_status(app, "idle")
            await restart.wait()
            continue
        t0 = time.monotonic()
        task = asyncio.create_task(irc_session(app, channel))
        waiter = asyncio.create_task(restart.wait())
        done, pending = await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
        for p in pending:
            p.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if task in done:
            exc = task.exception()
            if isinstance(exc, AuthError):
                log.error("%s", exc)
                set_status(app, "error", str(exc))
                await restart.wait()  # ждём новых настроек, не долбим Twitch
                continue
            if exc:
                log.warning("IRC: %r", exc)
            if time.monotonic() - t0 > 30:
                backoff = 1
            set_status(app, "reconnecting", f"через {backoff} c")
            try:
                await asyncio.wait_for(restart.wait(), backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 30)
        else:
            backoff = 1


# ----------------------------------------------------------------------------
# Обработка сообщений: фильтры -> смайлы -> рассылка в оверлей
# ----------------------------------------------------------------------------
def refresh_filters(app: web.Application) -> None:
    st = app["cfg"]["style"]
    app["ignored"] = {u.strip().lower() for u in re.split(r"[,\n]", st["ignoredUsers"]) if u.strip()}
    app["blocked"] = [w.strip().lower() for w in re.split(r"[,\n]", st["blockedWords"]) if w.strip()]


async def build_payload(app: web.Application, it: dict) -> dict | None:
    st = app["cfg"]["style"]
    text = it["text"].strip()[:400]
    if not text or it["user"] in app["ignored"]:
        return None
    if st["hideCommands"] and text.startswith("!"):
        return None
    low = text.lower()
    if any(w in low for w in app["blocked"]):
        return None
    parts = await app["emotes"].build_parts(text, it["tw"] if st["useTwitchEmotes"] else [], st["use7tv"])
    color = it["color"] or PALETTE[sum(map(ord, it["user"])) % len(PALETTE)]
    return {"type": "msg", "id": it["id"], "user": it["user"], "name": it["name"],
            "color": color, "me": it["me"], "parts": parts, "bd": it.get("bd", [])}


async def msg_worker(app: web.Application) -> None:
    q: asyncio.Queue = app["queue"]
    while True:
        it = await q.get()  # один воркер = порядок сообщений сохраняется
        try:
            payload = await asyncio.wait_for(build_payload(app, it), 8)
            if payload:
                await app["hub"].broadcast(payload)
        except Exception as e:
            log.warning("сообщение пропущено: %r", e)


async def emote_refresher(app: web.Application) -> None:
    em: Emotes = app["emotes"]
    await em.load_global()
    while True:
        await asyncio.sleep(6 * 3600)
        await em.load_global()
        if em.room:
            await em.load_channel(em.room)


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------
@web.middleware
async def guard(request: web.Request, handler):
    """Запрещаем изменяющие запросы с чужих сайтов (CSRF на localhost)."""
    origin = request.headers.get("Origin")
    if origin and request.method not in ("GET", "HEAD", "OPTIONS"):
        if urlparse(origin).netloc != request.headers.get("Host"):
            raise web.HTTPForbidden(text="bad origin")
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception:
        # сервер только на localhost, поэтому показываем причину прямо на странице
        import traceback
        tb = traceback.format_exc()
        log.error("Ошибка в %s:\n%s", request.path, tb)
        return web.Response(status=500, text="Ошибка сервера:\n\n" + tb,
                            content_type="text/plain", charset="utf-8")


MIME = {".html": "text/html; charset=utf-8", ".png": "image/png", ".apng": "image/apng",
        ".webp": "image/webp", ".gif": "image/gif", ".avif": "image/avif",
        ".ico": "image/x-icon", ".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2",
        ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


def send_file(request: web.Request, p: Path, cache: str) -> web.Response:
    """Отдаём файл обычным Response (без sendfile): на Windows FileResponse
    иногда даёт ERR_INVALID_RESPONSE. Файлы маленькие, читать целиком безопасно.
    ETag: если файл не менялся, отвечаем 304 и не читаем его с диска."""
    st = p.stat()
    etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
    headers = {"Cache-Control": cache, "ETag": etag}
    if request.headers.get("If-None-Match") == etag:
        return web.Response(status=304, headers=headers)
    headers["Content-Type"] = MIME.get(p.suffix.lower(), "application/octet-stream")
    return web.Response(body=p.read_bytes(), headers=headers)


def page(name: str):
    async def h(request):
        return send_file(request, RES / name, "no-cache")
    return h


async def index(_):
    raise web.HTTPFound("/app")


async def ws_handler(request: web.Request):
    ws = web.WebSocketResponse(heartbeat=25)
    await ws.prepare(request)
    hub: Hub = request.app["hub"]
    hub.clients.add(ws)
    await ws.send_str(json.dumps({"type": "users", "users": request.app["cfg"]["users"]}))
    await ws.send_str(json.dumps({"type": "theme", "theme": request.app["cfg"]["theme"]}))
    await ws.send_str(json.dumps({"type": "style", "style": request.app["cfg"]["style"]}))
    try:
        async for m in ws:
            if m.type == WSMsgType.TEXT and len(m.data) < 2000:   # оверлей присылает свою нагрузку (для диагностики)
                try:
                    d = json.loads(m.data)
                    if d.get("type") == "stats":
                        request.app["ovstats"][id(ws)] = {**{k: d.get(k) for k in ("frameMs", "longs", "rows", "anim", "guard", "game")}, "t": time.time()}
                except ValueError:
                    pass
    finally:
        hub.clients.discard(ws)
        request.app["ovstats"].pop(id(ws), None)
    return ws


async def serve_file(request: web.Request):
    kind, name = request.match_info["kind"], request.match_info["name"]
    base = {"skins": SKINS, "fonts": FONTS, "emotes": EMOTES, "decor": DECOR}.get(kind)
    if base is None or name != Path(name).name:
        raise web.HTTPNotFound()
    p = base / name
    if not p.is_file():
        raise web.HTTPNotFound()
    cc = "public, max-age=31536000, immutable" if kind == "emotes" else "no-cache"
    return send_file(request, p, cc)


def list_assets() -> dict:
    ls = lambda d: sorted(p.name for p in d.iterdir() if p.is_file())
    return {"skins": ls(SKINS), "fonts": ls(FONTS), "decor": ls(DECOR)}


async def api_get_config(request: web.Request):
    cfg = request.app["cfg"]
    return web.json_response({
        "channel": cfg["channel"], "nick": cfg["nick"], "has_token": bool(cfg["oauth"]),
        "style": cfg["style"], "theme": cfg["theme"], "users": cfg["users"], "assets": list_assets(),
        "presets": list(cfg["presets"]), "app": cfg["app"], "info": app_info(request.app),
    })


async def api_set_config(request: web.Request):
    app = request.app
    body = await request.json()
    cfg = app["cfg"]
    reconnect = False
    if "channel" in body:
        ch = str(body["channel"]).strip().lower().lstrip("#")
        if ch and not re.fullmatch(r"[a-z0-9_]{1,25}", ch):
            return web.json_response({"error": "Некорректное имя канала"}, status=400)
        if ch != cfg["channel"]:
            cfg["channel"] = ch
            app["emotes"].room, app["emotes"].chan = None, {}
            reconnect = True
    if "nick" in body:
        nick = str(body["nick"]).strip().lower()[:25]
        reconnect |= nick != cfg["nick"]
        cfg["nick"] = nick
    if body.get("clear_oauth"):
        cfg["oauth"], reconnect = "", True
    elif body.get("oauth"):
        cfg["oauth"] = str(body["oauth"]).strip().removeprefix("oauth:")[:100]
        reconnect = True
    if "app" in body:
        cfg["app"] = sanitize_app(body["app"], cfg["app"])
        apply_tray(app)
    if "users" in body:
        cfg["users"] = sanitize_users(body["users"])
        await app["hub"].broadcast({"type": "users", "users": cfg["users"]})
    if "theme" in body:
        cfg["theme"] = sanitize_theme(body["theme"])
        await app["hub"].broadcast({"type": "theme", "theme": cfg["theme"]})
    if "style" in body:
        cfg["style"] = coerce_style(cfg["style"], body["style"])
        refresh_filters(app)
        await app["hub"].broadcast({"type": "style", "style": cfg["style"]})
    save_config(cfg)
    if reconnect:
        app["irc_restart"].set()
    return web.json_response({"ok": True})


async def api_status(request: web.Request):
    app = request.app
    em: Emotes = app["emotes"]
    return web.json_response({**app["status"], "channel": app["cfg"]["channel"],
                              "emotes_global": len(em.glob), "emotes_channel": len(em.chan),
                              "cached": len(em.files), "overlays": len(app["hub"].clients),
                              "update": (app.get("update") or {}).get("newer", False)})


# ----------------------------------------------------------------------------
# Автозапуск, трей, обновления
# ----------------------------------------------------------------------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --no-window'
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else py}" "{BASE / "server.py"}" --no-window'


def autostart_get() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return bool(winreg.QueryValueEx(k, APP_NAME)[0])
    except OSError:
        return False


def autostart_set(on: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


try:  # значок в трее: необязательные библиотеки (pystray + Pillow), без них программа работает как раньше
    import pystray
    from PIL import Image as _PILImage
except Exception:  # noqa: BLE001
    pystray = None


class Tray:
    icon = None


def request_quit(loop: asyncio.AbstractEventLoop) -> None:
    def stop():
        loop.call_later(4, os._exit, 0)   # страховка, если остановка зависнет
        raise web.GracefulExit()
    loop.call_soon_threadsafe(stop)


def apply_tray(app: web.Application) -> None:
    """Значок в трее показываем, когда выбран режим «закрытие окна = свернуть в трей»."""
    want = app["cfg"]["app"]["onClose"] == "tray" and pystray is not None
    if want and Tray.icon is None:
        port, loop = app["cfg"]["port"], asyncio.get_running_loop()
        try:
            img = _PILImage.open(RES / "icon.png")
            menu = pystray.Menu(
                pystray.MenuItem("Открыть окно программы", lambda: open_panel(f"http://127.0.0.1:{port}/app"), default=True),
                pystray.MenuItem("Режим игры (без анимаций и эффектов)",
                                 lambda: asyncio.run_coroutine_threadsafe(set_game(app, not app["cfg"]["style"]["game"]), loop),
                                 checked=lambda item: app["cfg"]["style"]["game"]),
                pystray.MenuItem("Выход", lambda: request_quit(loop)))
            Tray.icon = pystray.Icon("TwitchChat7TV", img, APP_NAME, menu)
            import threading
            threading.Thread(target=Tray.icon.run, daemon=True).start()
            log.info("Значок в трее включён")
        except Exception as e:  # noqa: BLE001
            Tray.icon = None
            log.warning("Трей не запустился: %s", e)
    elif not want and Tray.icon is not None:
        try:
            Tray.icon.stop()
        except Exception:  # noqa: BLE001
            pass
        Tray.icon = None


def app_info(app: web.Application) -> dict:
    return {"version": APP_VERSION, "name": APP_NAME, "windows": sys.platform == "win32",
            "frozen": bool(getattr(sys, "frozen", False)), "autostart": autostart_get(),
            "tray": pystray is not None, "update": app.get("update") or {}}


def vtuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4]) or (0,)


def pick_version(*names: str) -> str:
    """Версия из тега или названия релиза: «v1.5.0», «b1.0», «Twitch chat b1.0.2». Пусто, если цифр нет."""
    for n in names:
        m = re.search(r"\d+(?:\.\d+){0,3}", str(n or ""))
        if m:
            return m.group(0)
    return ""


async def check_update(app: web.Application) -> dict:
    """Источник: «владелец/репозиторий» GitHub (последний релиз) или https-ссылка на version.json {"version","url","notes"}."""
    src = app["cfg"]["app"]["updateSource"]
    res = {"current": APP_VERSION, "source": src, "newer": False}
    if not src:
        res["error"] = "Источник обновлений не задан. Укажи GitHub-репозиторий (владелец/репозиторий) или ссылку на version.json."
        return res
    try:
        sess: ClientSession = app["session"]
        t = ClientTimeout(total=15)
        if src.startswith("https://"):
            async with sess.get(src, timeout=t) as r:
                r.raise_for_status()
                d = json.loads(await r.text())
            latest, url, notes = str(d.get("version", "")), str(d.get("url", "")), str(d.get("notes", ""))
        else:
            async with sess.get(f"https://api.github.com/repos/{src}/releases/latest", timeout=t,
                                headers={"Accept": "application/vnd.github+json"}) as r:
                if r.status == 404:
                    res["error"] = "Релизы в репозитории не найдены."
                    return res
                r.raise_for_status()
                d = await r.json()
            latest, notes = pick_version(d.get("tag_name"), d.get("name")), str(d.get("body", ""))[:600]
            assets = [a for a in d.get("assets", []) if str(a.get("name", "")).lower().endswith(".zip")]
            url = assets[0]["browser_download_url"] if assets else str(d.get("zipball_url", ""))
        if not latest or not url.startswith("https://"):
            res["error"] = "В релизе нет номера версии (назови тег, например, v1.5.0) или приложенного zip."
            return res
        res.update(latest=latest.lstrip("vV"), url=url, notes=notes, newer=vtuple(latest) > vtuple(APP_VERSION))
    except Exception as e:  # noqa: BLE001
        res["error"] = f"Не удалось проверить: {e}"
    if not res.get("error"):
        app["update"] = res
    return res


async def update_checker(app: web.Application) -> None:
    await asyncio.sleep(15)
    cfg = app["cfg"]["app"]
    if cfg["checkUpdates"] and cfg["updateSource"]:
        r = await check_update(app)
        log.info("Проверка обновлений: %s", f"доступна {r['latest']}" if r.get("newer") else r.get("error") or "у тебя последняя версия")


async def api_autostart(request: web.Request):
    if sys.platform != "win32":
        return web.json_response({"error": "Автозапуск работает только в Windows"}, status=400)
    on = bool((await request.json()).get("enabled"))
    try:
        autostart_set(on)
    except OSError as e:
        return web.json_response({"error": f"Не удалось записать в реестр: {e}"}, status=500)
    log.info("Автозапуск с Windows: %s", "включён" if on else "выключен")
    return web.json_response({"ok": True, "autostart": autostart_get()})


async def api_update_check(request: web.Request):
    return web.json_response(await check_update(request.app))


async def api_update_install(request: web.Request):
    app = request.app
    up = app.get("update") or {}
    if not up.get("newer"):
        return web.json_response({"error": "Сначала нажми «Проверить обновления»"}, status=400)
    if getattr(sys, "frozen", False) or sys.platform != "win32":
        return web.json_response({"error": "Автоустановка работает для обычной установки в Windows. Скачай архив вручную: " + up["url"]}, status=400)
    zp = Path(os.environ.get("TEMP", str(DATA))) / "twitchchat7tv_update.zip"
    size = 0
    try:
        async with app["session"].get(up["url"], timeout=ClientTimeout(total=120)) as r:
            r.raise_for_status()
            with zp.open("wb") as f:
                async for chunk in r.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > 80 << 20:
                        raise ValueError("архив больше 80 МБ")
                    f.write(chunk)
        import zipfile
        with zipfile.ZipFile(zp) as z:
            if not any(n.endswith("server.py") for n in z.namelist()):
                raise ValueError("в архиве нет server.py")
    except Exception as e:  # noqa: BLE001
        zp.unlink(missing_ok=True)
        return web.json_response({"error": f"Не удалось скачать обновление: {e}"}, status=500)
    log.info("Устанавливаю обновление %s", up.get("latest"))
    bat = BASE / "update.bat"
    subprocess.Popen(f'start "" /min cmd /c ""{bat}" "{zp}" /y"', shell=True, cwd=str(BASE))
    return web.json_response({"ok": True})


async def ws_panel(request: web.Request):
    """Сокет окна программы: когда окно закрыто и выбран режим «закрытие = выход», программа завершается."""
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    app = request.app
    app["panels"].add(ws)
    try:
        async for _ in ws:
            pass
    finally:
        app["panels"].discard(ws)
        if app["cfg"]["app"]["onClose"] == "quit":
            loop = asyncio.get_running_loop()

            def check():
                if not app["panels"] and app["cfg"]["app"]["onClose"] == "quit":
                    log.info("Окно программы закрыто, выход")
                    request_quit(loop)
            loop.call_later(6, check)      # запас на перезагрузку страницы
    return ws


async def api_stats(request: web.Request):
    """Нагрузка: процесс сервера (измеряется) и оверлеи (присылают сами). Браузер OBS считается внутри OBS."""
    app = request.app
    w0, c0 = app["cpu_last"]
    w1, c1 = time.time(), time.process_time()
    app["cpu_last"] = (w1, c1)
    cpu = round(100 * (c1 - c0) / max(w1 - w0, 0.001) / (os.cpu_count() or 1), 1)
    ov = [v for v in app["ovstats"].values() if time.time() - v["t"] < 30]
    return web.json_response({"server_cpu": cpu, "overlays": ov})


async def set_game(app: web.Application, on: bool) -> None:
    app["cfg"]["style"]["game"] = bool(on)
    save_config(app["cfg"])
    await app["hub"].broadcast({"type": "style", "style": app["cfg"]["style"]})
    log.info("Режим игры: %s", "включён" if on else "выключен")


async def api_logs(request: web.Request):
    try:
        since = int(request.query.get("since", "0"))
    except ValueError:
        since = 0
    return web.json_response({"last": LOG_RING.n, "lines": LOG_RING.since(since)})


async def api_quit(request: web.Request):
    log.info("Выход по кнопке в программе")

    loop = asyncio.get_running_loop()
    loop.call_later(0.3, request_quit, loop)
    return web.json_response({"ok": True})


async def api_open_app(request: web.Request):
    """Открывает окно программы (кнопка в доке OBS: сам док внутри OBS окон не открывает)."""
    open_panel(f"http://127.0.0.1:{request.app['cfg']['port']}/app")
    return web.json_response({"ok": True})


async def api_presets(request: web.Request):
    """Пресеты внешнего вида: save (снимок текущих настроек), apply, delete."""
    app = request.app
    cfg = app["cfg"]
    body = await request.json()
    action, name = body.get("action"), str(body.get("name", "")).strip()[:40]
    if not name:
        return web.json_response({"error": "Введи название пресета"}, status=400)
    if action == "save":
        if name not in cfg["presets"] and len(cfg["presets"]) >= MAX_PRESETS:
            return web.json_response({"error": f"Не больше {MAX_PRESETS} пресетов"}, status=400)
        snap = {"style": {k: v for k, v in cfg["style"].items() if k not in PRESET_SKIP}, "theme": cfg["theme"]}
        cfg["presets"][name] = sanitize_presets({name: snap})[name]
    elif action == "apply":
        pr = cfg["presets"].get(name)
        if pr is None:
            return web.json_response({"error": "Пресет не найден"}, status=404)
        cfg["theme"] = sanitize_theme(pr["theme"])
        cfg["style"] = coerce_style(cfg["style"], pr["style"])
        await app["hub"].broadcast({"type": "theme", "theme": cfg["theme"]})
        await app["hub"].broadcast({"type": "style", "style": cfg["style"]})
    elif action == "delete":
        cfg["presets"].pop(name, None)
    else:
        return web.json_response({"error": "bad action"}, status=400)
    save_config(cfg)
    return web.json_response({"ok": True, "presets": list(cfg["presets"])})


async def api_upload(request: web.Request):
    kind = request.match_info["kind"]
    img_ext = {".png", ".webp", ".gif", ".apng"}
    rules = {"skins": (SKINS, img_ext), "decor": (DECOR, img_ext), "fonts": (FONTS, {".ttf", ".otf", ".woff", ".woff2"})}
    if kind not in rules:
        raise web.HTTPNotFound()
    folder, exts = rules[kind]
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "file":
        return web.json_response({"error": "нет файла"}, status=400)
    name = re.sub(r"[^\w.\-]+", "_", Path(field.filename or "file").name)[:80] or "file"
    if Path(name).suffix.lower() not in exts:
        return web.json_response({"error": "Допустимо: " + ", ".join(sorted(exts))}, status=400)
    # имя не должно повторяться: иначе браузер OBS может показать старую картинку из кеша
    stem, suf, i = Path(name).stem, Path(name).suffix, 1
    while (folder / name).exists():
        i += 1
        name = f"{stem}_{i}{suf}"
    tmp, size = folder / (name + ".tmp"), 0
    with tmp.open("wb") as f:
        while chunk := await field.read_chunk(65536):
            size += len(chunk)
            if size > 8 << 20:
                f.close()
                tmp.unlink(missing_ok=True)
                return web.json_response({"error": "Файл больше 8 МБ"}, status=413)
            f.write(chunk)
    tmp.replace(folder / name)
    return web.json_response({"name": name})


async def api_delete_asset(request: web.Request):
    app = request.app
    kind, name = request.match_info["kind"], request.match_info["name"]
    folder = {"skins": SKINS, "fonts": FONTS, "decor": DECOR}.get(kind)
    if folder is None or name != Path(name).name:
        raise web.HTTPNotFound()
    (folder / name).unlink(missing_ok=True)
    cfg = app["cfg"]
    if kind == "decor":  # убираем из темы элементы, которые ссылались на файл
        th = cfg["theme"]
        left = [d for d in th["decor"] if d.get("file") != name]
        if len(left) != len(th["decor"]):
            th["decor"] = left
            save_config(cfg)
            await app["hub"].broadcast({"type": "theme", "theme": th})
    else:
        key = "skin" if kind == "skins" else "font"
        st = cfg["style"]
        if st[key] == name:
            st[key] = ""
            save_config(cfg)
            await app["hub"].broadcast({"type": "style", "style": st})
    return web.json_response({"ok": True})


async def api_test(request: web.Request):
    app = request.app
    samples = [("Streamer", "#ff4d6d", "Привет, чат! Проверка оформления", ["b"]),
               ("Viewer_42", "#4cc9f0", "Очень длинное сообщение, чтобы посмотреть как переносится текст внутри подложки и не ломается ли дизайн", []),
               ("Moder", "#2ec4b6", "Смайлики работают?", ["m"]),
               ("LeadMod", "#a970ff", "Порядок в чате под контролем", ["l"])]
    names = app["emotes"].names()
    try:
        body = await request.json()
    except Exception:
        body = {}
    target = str(body.get("user", "")).strip().lower() if isinstance(body, dict) else ""
    users = list(app["cfg"]["users"])
    if target:  # тест от конкретного ника (кнопка ▶ в карточке эффекта)
        samples = [(target, "#ffffff", "Так выглядит моё сообщение с эффектами", [])]
    elif users:  # в обычном тесте подмешиваем ник с эффектами, чтобы их было видно
        samples[1] = (random.choice(users), "#4cc9f0", samples[1][2], [])

    async def run():
        for user, color, text, bd in samples:
            if names:
                text += " " + " ".join(random.sample(names, min(2, len(names))))
            enqueue(app, {"id": f"test-{time.time_ns()}", "user": user.lower(), "name": user,
                          "color": color, "text": text, "me": False, "tw": [], "bd": bd})
            await asyncio.sleep(0.4)

    asyncio.create_task(run())
    return web.json_response({"ok": True})


async def api_clear(request: web.Request):
    await request.app["hub"].broadcast({"type": "clear"})
    return web.json_response({"ok": True})


async def api_refresh_emotes(request: web.Request):
    em: Emotes = request.app["emotes"]
    await em.load_global()
    if em.room:
        await em.load_channel(em.room)
    return web.json_response({"global": len(em.glob), "channel": len(em.chan)})


async def on_startup(app: web.Application) -> None:
    app["session"] = ClientSession(headers={"User-Agent": "obs-chat-overlay/1.0"})
    app["emotes"] = Emotes(app["session"])
    app["queue"] = asyncio.Queue(maxsize=300)
    app["irc_restart"] = asyncio.Event()
    refresh_filters(app)
    app["tasks"] = [asyncio.create_task(f(app)) for f in (irc_supervisor, msg_worker, emote_refresher, update_checker)]
    apply_tray(app)


async def on_cleanup(app: web.Application) -> None:
    if Tray.icon is not None:
        try:
            Tray.icon.stop()
        except Exception:  # noqa: BLE001
            pass
    for t in app["tasks"]:
        t.cancel()
    await asyncio.gather(*app["tasks"], return_exceptions=True)
    await app["session"].close()


def make_app(cfg: dict) -> web.Application:
    app = web.Application(middlewares=[guard], client_max_size=16 << 20)
    app["cfg"], app["hub"] = cfg, Hub()
    app["status"] = {"state": "idle", "detail": ""}
    app["panels"] = set()
    app["ovstats"] = {}
    app["cpu_last"] = (time.time(), time.process_time())
    app.router.add_get("/", index)
    app.router.add_get("/overlay", page("overlay.html"))
    app.router.add_get("/app", page("app.html"))
    app.router.add_get("/dock", page("dock.html"))
    app.router.add_get("/quick.js", page("quick.js"))
    app.router.add_get("/theme.css", page("theme.css"))
    app.router.add_get("/theme.js", page("theme.js"))
    app.router.add_get("/favicon.ico", page("icon.ico"))
    app.router.add_get("/icon.png", page("icon.png"))
    app.router.add_get("/editor", page("editor.html"))
    app.router.add_get("/bubble.js", page("bubble.js"))
    app.router.add_get("/bubble.css", page("bubble.css"))
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/files/{kind}/{name}", serve_file)
    app.router.add_get("/api/config", api_get_config)
    app.router.add_post("/api/config", api_set_config)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/logs", api_logs)
    app.router.add_get("/api/stats", api_stats)
    app.router.add_get("/ws-panel", ws_panel)
    app.router.add_post("/api/autostart", api_autostart)
    app.router.add_post("/api/update/check", api_update_check)
    app.router.add_post("/api/update/install", api_update_install)
    app.router.add_post("/api/quit", api_quit)
    app.router.add_post("/api/open-app", api_open_app)
    app.router.add_post("/api/presets", api_presets)
    app.router.add_post("/api/upload/{kind}", api_upload)
    app.router.add_delete("/api/asset/{kind}/{name}", api_delete_asset)
    app.router.add_post("/api/test", api_test)
    app.router.add_post("/api/clear", api_clear)
    app.router.add_post("/api/refresh-emotes", api_refresh_emotes)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def open_panel(url: str) -> None:
    """Открывает панель управления отдельным окном-приложением (Edge/Chrome --app)."""
    if sys.platform == "win32":
        cands = [shutil.which("msedge"), shutil.which("chrome"),
                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
        for exe in cands:
            if exe and Path(exe).exists():
                try:
                    # отдельный профиль: свой процесс браузера (не смешивается с твоим Chrome, без расширений),
                    # наследует пониженный приоритет программы
                    subprocess.Popen([exe, f"--app={url}", "--window-size=1280,860", f"--user-data-dir={DATA / 'browser'}",
                                      "--no-first-run", "--no-default-browser-check", "--disable-extensions"],
                                     creationflags=0x00004000)  # BELOW_NORMAL_PRIORITY_CLASS
                    return
                except OSError:
                    pass
    webbrowser.open(url)


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def lower_priority() -> None:
    """Фоновый приоритет процесса: чат никогда не отбирает CPU у OBS и игры."""
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL
        else:
            import os
            os.nice(5)
    except Exception:
        pass


CACHE_MAX_MB = 400


def prune_cache(max_mb: int = CACHE_MAX_MB) -> None:
    """Если кеш смайлов вырос больше лимита, удаляем самые старые файлы до ~80% лимита."""
    try:
        files = [(p.stat().st_mtime, p.stat().st_size, p) for p in EMOTES.iterdir() if p.is_file()]
        total = sum(s for _, s, _ in files)
        if total <= max_mb << 20:
            return
        target = int((max_mb << 20) * 0.8)
        for _, size, p in sorted(files):
            p.unlink(missing_ok=True)
            total -= size
            if total <= target:
                break
        log.info("Кеш смайлов очищен до %d МБ", total >> 20)
    except OSError as e:
        log.warning("не удалось почистить кеш: %s", e)


def main() -> None:
    console = "--console" in sys.argv
    for name in ("stdout", "stderr"):          # pythonw / exe без консоли: потоков нет, print не должен падать
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    setup_logging(console)
    lower_priority()
    cfg = load_config()
    prune_cache(cfg["app"]["cacheMb"])
    port = int(cfg["port"])
    panel = f"http://127.0.0.1:{port}/app"
    quiet = "--no-window" in sys.argv
    need = ("overlay.html", "app.html", "dock.html", "editor.html", "bubble.js", "bubble.css", "quick.js", "theme.css", "theme.js", "icon.ico", "icon.png")
    missing = [n for n in need if not (RES / n).is_file()]
    if missing:
        fatal(f"Не найдены файлы: {', '.join(missing)}\nв папке {RES}\n\n"
              "Положи server.py и все файлы программы в ОДНУ папку (без приписок вроде \"(1)\").")
    if port_in_use(port):  # уже запущено: просто открываем панель
        log.info("Приложение уже запущено, открываю панель.")
        if not quiet:
            open_panel(panel)
        return
    log.info("Twitch chat 7TV запущен")
    log.info("Overlay (Browser Source в OBS): http://127.0.0.1:%d/overlay", port)
    log.info("Док OBS (Custom Browser Dock):   http://127.0.0.1:%d/dock", port)
    app = make_app(cfg)
    if not quiet:
        async def _open(_app):
            asyncio.get_running_loop().call_later(0.8, open_panel, panel)
        app.on_startup.append(_open)
    try:
        # access_log=None: не пишем строку на каждый запрос
        web.run_app(app, host="127.0.0.1", port=port, print=None, access_log=None)
    except OSError as e:
        log.error("Не удалось занять порт %d: %s", port, e)
        fatal(f"Не удалось занять порт {port}: {e}\nИзмени port в data\\config.json.")


if __name__ == "__main__":
    main()
