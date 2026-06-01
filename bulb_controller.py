"""
Graphical controller for Tuya smart bulbs over the local network (LAN).

Reads its configuration from 'devices.json' (id, ip, key, version) and talks to
the bulb 100% over the LAN with tinytuya - no cloud, no app, no internet.

Run (or use the desktop shortcut / "run.bat"):
    .venv/Scripts/pythonw.exe bulb_controller.py   (no console window)
    .venv/Scripts/python.exe  bulb_controller.py   (with console, handy for debug)

Tested on an Intelbras EWS 410, but works with most Tuya Wi-Fi bulbs.
Author: Faderaulas - MIT License.
"""
import os
import sys
import json
import math
import time
import datetime
import queue
import random
import threading
import colorsys
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import colorchooser, messagebox, simpledialog

import tinytuya

try:                       # tray + screen capture (optional; bundled in the .exe)
    import pystray
    from PIL import Image, ImageGrab
    TRAY_OK = True
except Exception:
    TRAY_OK = False

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)     # .exe: config/prefs live next to it
    RES = getattr(sys, "_MEIPASS", BASE_DIR)       # bundled resources (icons)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RES = BASE_DIR
CONFIG = os.path.join(BASE_DIR, "devices.json")
PREFS = os.path.join(BASE_DIR, "preferences.json")
ICON = os.path.join(RES, "icon.png")

# Data points (DPS) - standard Tuya mapping for a "type B" colour bulb
DP_POWER = "20"
DP_MODE = "21"        # white | colour | scene | music
DP_BRIGHT = "22"      # 10..1000
DP_TEMP = "23"        # 0..1000 (0 = warm, 1000 = cool)
DP_COLOUR = "24"      # HSV hex: HHHH SSSS VVVV

BRIGHT_MIN = 10
BRIGHT_MAX = 1000

# Preset colours (name -> RGB)
PRESETS = {
    "Red": (255, 0, 0),
    "Orange": (255, 120, 0),
    "Yellow": (255, 220, 0),
    "Green": (0, 255, 0),
    "Cyan": (0, 255, 255),
    "Blue": (0, 80, 255),
    "Purple": (150, 0, 255),
    "Pink": (255, 0, 150),
}

# Modern dark theme palette
BG = "#15161c"          # window background
CARD = "#1e2029"        # card background
CARD2 = "#2c303d"       # subtle highlight
SLIDER_TRACK = "#3b4156"  # slider track (contrasts with the card)
BTN = "#2b2e3b"         # base button
BTN_HOVER = "#373b4c"   # hover
BTN_ACTIVE = "#434a60"  # pressed
FG = "#e9eaf0"          # main text
MUTED = "#969cab"       # secondary text
ACCENT = "#5b8def"
ACCENT_HOVER = "#6f9cf3"
ACCENT_ACTIVE = "#4878d4"
OFF = "#3a3e4d"
OFF_HOVER = "#454a5c"
OFF_ACTIVE = "#50566b"
STOP = "#5a3a3a"
STOP_HOVER = "#6c4646"
OK = "#62c98a"
WARN = "#e06c6c"
AMBER = "#d9a05b"       # discreet warning (bulb offline)


def load_bulbs():
    """Read devices.json -> list of valid bulbs (may be empty)."""
    try:
        with open(CONFIG, encoding="utf-8") as f:
            devs = json.load(f)
    except Exception:
        return []
    if isinstance(devs, dict):
        devs = [devs]
    return [d for d in devs if d.get("id") and d.get("ip") and d.get("key")]


def save_bulbs(bulbs):
    """Save the list to devices.json (and mirror into dist/ when running from source)."""
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(bulbs, f, indent=2, ensure_ascii=False)
    if not getattr(sys, "frozen", False):
        dist_cfg = os.path.join(BASE_DIR, "dist", "devices.json")
        if os.path.isdir(os.path.dirname(dist_cfg)):
            try:
                with open(dist_cfg, "w", encoding="utf-8") as f:
                    json.dump(bulbs, f, indent=2, ensure_ascii=False)
            except Exception:
                pass


SAT_MIN = 0.30   # minimum saturation so the colour actually shows on the bulb


def _steps(start, end, n=6):
    """List of n values going from 'start' (exclusive) to 'end' (inclusive)."""
    return [round(start + (end - start) * (k + 1) / n) for k in range(n)]


def displayable_color(rgb):
    """Adjust the colour to the closest one the bulb can actually show.
    Returns (is_white, adjusted_rgb): nearly-desaturated colours become 'white'
    (the bulb can't show pastel/white in colour mode); the others get their
    saturation boosted so they appear with the right hue."""
    r, g, b = (c / 255.0 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.12:
        return True, rgb
    r2, g2, b2 = colorsys.hsv_to_rgb(h, max(s, SAT_MIN), max(v, 0.15))
    return False, (int(r2 * 255), int(g2 * 255), int(b2 * 255))


def parse_hsv_hex(s):
    """Convert the Tuya colour hex (HHHHSSSSVVVV) into RGB 0-255."""
    try:
        h = int(s[0:4], 16)        # 0..360
        sat = int(s[4:8], 16)      # 0..1000
        val = int(s[8:12], 16)     # 0..1000
        r, g, b = colorsys.hsv_to_rgb(h / 360.0, sat / 1000.0, val / 1000.0)
        return int(r * 255), int(g * 255), int(b * 255)
    except Exception:
        return (255, 255, 255)


# ---------- Moving scenes (generators: yield the delay until the next frame) ----------
def scene_rainbow(b):
    """Smoothly cycles through the whole colour spectrum."""
    h = 0.0
    while True:
        b.set_hsv(h, 1.0, 1.0, nowait=True)
        h = (h + 0.03) % 1.0
        yield 0.30


def scene_candle(b):
    """Warm flicker imitating a candle flame."""
    while True:
        h = random.uniform(25, 42) / 360.0   # orange/yellow
        v = random.uniform(0.45, 0.9)
        b.set_hsv(h, 0.85, v, nowait=True)
        yield random.uniform(0.07, 0.16)


def scene_breathe(b):
    """Brightness slowly rising and falling, in warm white."""
    phase = 0.0
    while True:
        v = 0.12 + 0.85 * (1 + math.sin(phase)) / 2
        b.set_hsv(38 / 360.0, 0.35, v, nowait=True)
        phase += 0.22
        yield 0.08


# Static scenes: (name, temp%, brightness%) | Moving scenes: (name, generator)
STATIC_SCENES = [
    ("Reading", 100, 100),
    ("Cozy", 0, 45),
    ("Movie", 0, 8),
]
MOVING_SCENES = [
    ("Candle", scene_candle),
    ("Rainbow", scene_rainbow),
    ("Breathe", scene_breathe),
]


def temp_to_rgb(temp_pct, bright_pct=100):
    """Approximate the adjustable-white colour for the display swatch:
    0% = warm (orange-ish), 100% = cool (bluish white). Darkens with brightness."""
    t = max(0, min(100, temp_pct)) / 100.0
    warm = (255, 140, 42)
    cool = (215, 230, 255)
    r = warm[0] + (cool[0] - warm[0]) * t
    g = warm[1] + (cool[1] - warm[1]) * t
    bl = warm[2] + (cool[2] - warm[2]) * t
    f = 0.25 + 0.75 * (max(1, min(100, bright_pct)) / 100.0)
    return (int(r * f), int(g * f), int(bl * f))


def load_prefs():
    try:
        with open(PREFS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_prefs(p):
    with open(PREFS, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)


def build_state_func(state):
    """Build a func(bulb) that applies a saved state (mode/brightness/temp/color)."""
    mode = state.get("mode", "white")
    brightness = int(state.get("brightness", 100))
    if mode == "colour":
        color = state.get("color", [255, 255, 255])

        def apply(b):
            r, g, bl = (c / 255.0 for c in color)
            h, s, _ = colorsys.rgb_to_hsv(r, g, bl)
            b.set_hsv(h, s, max(0.05, brightness / 100.0))
        return apply

    temp = int(state.get("temp", 50))

    def apply(b):
        b.set_colourtemp_percentage(temp)
        b.set_brightness_percentage(brightness)
    return apply


class BulbController:
    """Serialized access to one bulb via a single worker thread."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.queue = queue.Queue()
        self.bulb = None
        self.on_status = None       # callback(dps_dict)
        self.on_connection = None   # callback(ok: bool, msg: str)
        self.on_online = None       # callback(online: bool)
        self._anim = None           # active animation generator (or None)
        self._anim_delay = 0.1      # delay until the next frame
        self.fade = False           # smooth transition on/off
        self._lb = None             # last brightness (%) applied/read
        self._lt = None             # last temperature (%)
        self._lc = None             # last colour (rgb)
        threading.Thread(target=self._worker, daemon=True).start()

    def _connect(self):
        ver = float(self.cfg.get("version") or 3.3)
        b = tinytuya.BulbDevice(self.cfg["id"], self.cfg["ip"], self.cfg["key"], version=ver)
        b.set_socketPersistent(True)
        b.set_socketTimeout(5)
        b.set_socketRetryLimit(1)
        self.bulb = b

    def _drain(self):
        """Discard stale responses left in the socket buffer (echoes of commands sent
        with nowait by fade/animations), so the next read gets the current state."""
        s = getattr(self.bulb, "socket", None)
        if s is None:
            return
        try:
            s.settimeout(0.0)
            while True:
                try:
                    if not s.recv(8192):
                        break
                except Exception:
                    break
        finally:
            try:
                s.settimeout(getattr(self.bulb, "connection_timeout", 5) or 5)
            except Exception:
                pass

    def _worker(self):
        try:
            self._connect()
            if self.on_connection:
                self.on_connection(True, f"connected ({self.cfg['ip']})")
        except Exception as e:
            if self.on_connection:
                self.on_connection(False, f"failed to connect: {e}")
            if self.on_online:
                self.on_online(False)
        while True:
            timeout = self._anim_delay if self._anim is not None else None
            try:
                action, args = self.queue.get(timeout=timeout)
            except queue.Empty:
                # no pending command: advance one animation frame
                try:
                    self._anim_delay = next(self._anim)
                except Exception:
                    self._anim = None
                continue

            if action == "_quit":
                break

            if action == "anim":
                # start/stop an animated scene (args = generator or None)
                self._anim = None
                if args is not None:
                    try:
                        if self.bulb is None:
                            self._connect()
                        self.bulb.turn_on()
                        self._anim = args(self.bulb)
                        self._anim_delay = 0.05
                    except Exception as e:
                        if self.on_connection:
                            self.on_connection(False, f"error: {e}")
                continue

            # any manual command (except a status read) interrupts the scene
            if action != "status":
                self._anim = None
            try:
                self._execute(action, args)
            except Exception as e:
                if self.on_connection:
                    self.on_connection(False, f"error: {e}")
                if self.on_online:
                    self.on_online(False)
                # try to reconnect on the next action
                try:
                    self._connect()
                except Exception:
                    pass

    def _execute(self, action, args):
        b = self.bulb
        if b is None:
            self._connect()
            b = self.bulb
        if action == "status":
            self._drain()
            resp = b.status()
            dps = resp.get("dps") if isinstance(resp, dict) else None
            if dps:
                self._sync_last(dps)
                if self.on_status:
                    self.on_status(dps)
                if self.on_online:
                    self.on_online(True)
            elif self.on_online:
                # responded without data / with an error -> treat as unavailable
                self.on_online(False)
        elif action == "power":
            b.turn_on() if args else b.turn_off()
        elif action == "brightness":
            self._apply_num(b.set_brightness_percentage, self._lb, args, "_lb")
        elif action == "brightness_direct":
            v = max(1, min(100, int(args)))
            b.set_brightness_percentage(v)
            self._lb = v
        elif action == "temp":
            self._apply_num(b.set_colourtemp_percentage, self._lt, args, "_lt")
        elif action == "white":
            b.set_mode("white")
        elif action == "color":
            self._apply_color_fade(b, args)
        elif action == "color_direct":
            r, g, bl = (int(c) for c in args)
            b.set_colour(r, g, bl)
            self._lc = (r, g, bl)
        elif action == "func":
            args(b)

    def _sync_last(self, dps):
        try:
            if DP_BRIGHT in dps:
                self._lb = max(1, min(100, round((int(dps[DP_BRIGHT]) - BRIGHT_MIN) /
                                                 (BRIGHT_MAX - BRIGHT_MIN) * 100)))
            if DP_TEMP in dps:
                self._lt = round(int(dps[DP_TEMP]) / 1000 * 100)
            if DP_COLOUR in dps and dps[DP_COLOUR]:
                self._lc = parse_hsv_hex(dps[DP_COLOUR])
        except Exception:
            pass

    def _apply_num(self, fn, current, target, attr):
        target = max(1, min(100, int(target)))
        if self.fade and current is not None and current != target:
            steps = _steps(current, target)
            for i, v in enumerate(steps):
                last = (i == len(steps) - 1)
                fn(max(1, min(100, v)), nowait=not last)
                if not last:
                    time.sleep(0.05)
        else:
            fn(target)
        setattr(self, attr, target)

    def _apply_color_fade(self, b, rgb):
        r, g, bl = (int(c) for c in rgb)
        if self.fade and self._lc is not None and tuple(self._lc) != (r, g, bl):
            lr, lg, lb = self._lc
            n = 6
            for k in range(1, n + 1):
                rr = round(lr + (r - lr) * k / n)
                gg = round(lg + (g - lg) * k / n)
                bb = round(lb + (bl - lb) * k / n)
                b.set_colour(rr, gg, bb, nowait=(k < n))
                if k < n:
                    time.sleep(0.05)
        else:
            b.set_colour(r, g, bl)
        self._lc = (r, g, bl)

    # --- public API (enqueues) ---
    def request_status(self):
        self.queue.put(("status", None))

    def start_scene(self, generator):
        self.queue.put(("anim", generator))

    def stop_scene(self):
        self.queue.put(("anim", None))

    def apply_func(self, func):
        self.queue.put(("anim", None))
        self.queue.put(("func", func))

    def power(self, on):
        self.queue.put(("power", on))

    def brightness(self, pct):
        self.queue.put(("brightness", pct))

    def brightness_direct(self, pct):
        self.queue.put(("brightness_direct", pct))

    def temperature(self, pct):
        self.queue.put(("temp", pct))

    def white_mode(self):
        self.queue.put(("white", None))

    def color(self, rgb):
        self.queue.put(("color", rgb))

    def color_direct(self, rgb):
        self.queue.put(("color_direct", rgb))

    def shutdown(self):
        self.queue.put(("_quit", None))


# =================== custom widgets (modern look) ===================
def _rounded_points(x1, y1, x2, y2, r):
    """Points of a rounded-corner rectangle (use with smooth=True)."""
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


class RoundedButton(tk.Canvas):
    """Rounded-corner button with hover and click feedback."""

    def __init__(self, parent, text="", command=None, width=120, height=38,
                 radius=11, fill=BTN, hover=BTN_HOVER, active=BTN_ACTIVE,
                 fg=FG, font=("Segoe UI", 10)):
        super().__init__(parent, width=width, height=height, bg=parent["bg"],
                         highlightthickness=0, bd=0)
        self.command = command
        self._fill, self._hover, self._active = fill, hover, active
        self._bw, self._bh = width, height
        self._shape = self.create_polygon(
            *_rounded_points(1, 1, width - 1, height - 1, radius),
            smooth=True, splinesteps=28, fill=fill)
        self._txt = self.create_text(width // 2, height // 2, text=text, fill=fg, font=font)
        self.configure(cursor="hand2")
        self.bind("<Enter>", lambda e: self._set(self._hover))
        self.bind("<Leave>", lambda e: self._set(self._fill))
        self.bind("<ButtonPress-1>", lambda e: self._set(self._active))
        self.bind("<ButtonRelease-1>", self._release)

    def _set(self, color):
        self.itemconfig(self._shape, fill=color)

    def _release(self, e):
        inside = 0 <= e.x <= self._bw and 0 <= e.y <= self._bh
        self._set(self._hover if inside else self._fill)
        if inside and self.command:
            self.command()

    def set_text(self, t):
        self.itemconfig(self._txt, text=t)

    def set_colors(self, fill, hover, active):
        self._fill, self._hover, self._active = fill, hover, active
        self._set(fill)


class ColorDot(tk.Canvas):
    """Rounded colour dot with an outline on hover."""

    def __init__(self, parent, rgb, command, size=30, radius=9):
        super().__init__(parent, width=size, height=size, bg=parent["bg"],
                         highlightthickness=0, bd=0)
        self.command = command
        self._shape = self.create_polygon(
            *_rounded_points(2, 2, size - 2, size - 2, radius),
            smooth=True, splinesteps=24, fill="#%02x%02x%02x" % rgb,
            outline="", width=0)
        self.configure(cursor="hand2")
        self.bind("<Enter>", lambda e: self.itemconfig(self._shape, outline=FG, width=2))
        self.bind("<Leave>", lambda e: self.itemconfig(self._shape, outline="", width=0))
        self.bind("<ButtonRelease-1>", lambda e: self.command() if self.command else None)


class Swatch(tk.Canvas):
    """Rounded square showing the current colour/white."""

    def __init__(self, parent, w=66, h=42, radius=12):
        super().__init__(parent, width=w, height=h, bg=parent["bg"],
                         highlightthickness=0, bd=0)
        self._shape = self.create_polygon(
            *_rounded_points(1, 1, w - 1, h - 1, radius),
            smooth=True, splinesteps=28, fill="#ffffff")

    def set(self, rgb):
        self.itemconfig(self._shape, fill="#%02x%02x%02x" % rgb)


class Slider(tk.Canvas):
    """Modern horizontal slider: rounded contrasting track, highlighted filled
    portion and a round thumb. Syncs with an IntVar."""

    def __init__(self, parent, variable, from_=0, to=100, command=None,
                 width=300, height=26, fill=ACCENT, track=SLIDER_TRACK):
        super().__init__(parent, width=width, height=height, bg=parent["bg"],
                         highlightthickness=0, bd=0)
        self.var = variable
        self.from_, self.to = from_, to
        self.command = command
        self._wpx, self._h = width, height
        self._fill, self._track = fill, track
        self._pad = 12
        self.configure(cursor="hand2")
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<ButtonPress-1>", self._move)
        self.bind("<B1-Motion>", self._move)
        self.var.trace_add("write", lambda *a: self._redraw())
        self.after(0, self._redraw)

    def _frac(self):
        rng = (self.to - self.from_) or 1
        return max(0.0, min(1.0, (self.var.get() - self.from_) / rng))

    def _redraw(self):
        w = self.winfo_width()
        if w <= 1:
            w = self._wpx
        self.delete("all")
        cy = self._h // 2
        x0, x1 = self._pad, w - self._pad
        self.create_line(x0, cy, x1, cy, fill=self._track, width=6, capstyle="round")
        fx = x0 + self._frac() * (x1 - x0)
        if fx > x0 + 1:
            self.create_line(x0, cy, fx, cy, fill=self._fill, width=6, capstyle="round")
        r = 9
        self.create_oval(fx - r, cy - r, fx + r, cy + r, fill="#ffffff",
                         outline=self._fill, width=2)

    def _move(self, e):
        w = self.winfo_width() or self._wpx
        x = min(max(e.x, self._pad), w - self._pad)
        rng = (self.to - self.from_) or 1
        val = round(self.from_ + (x - self._pad) / max(1, (w - 2 * self._pad)) * rng)
        val = max(self.from_, min(self.to, val))
        if val != self.var.get():
            self.var.set(val)
        if self.command:
            self.command(val)


# ---------- global hotkeys (Windows, via RegisterHotKey) ----------
HOTKEYS_OK = sys.platform == "win32"
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
_WM_HOTKEY, _WM_QUIT = 0x0312, 0x0012

SHORTCUT_ACTIONS = [
    ("toggle_power", "Turn on / off"),
    ("show", "Show / hide window"),
    ("default", "Apply default state"),
    ("stop_scene", "Stop scene"),
]
SHORTCUT_KEYS = ([chr(c) for c in range(ord("A"), ord("Z") + 1)] +
                 [str(d) for d in range(10)] +
                 [f"F{n}" for n in range(1, 13)] + ["Space"])


def _key_to_vk(k):
    k = (k or "").upper()
    if len(k) == 1 and ("A" <= k <= "Z" or "0" <= k <= "9"):
        return ord(k)
    if k.startswith("F") and k[1:].isdigit() and 1 <= int(k[1:]) <= 12:
        return 0x70 + (int(k[1:]) - 1)
    return {"SPACE": 0x20}.get(k, 0)


class HotkeyManager:
    """Registers global hotkeys on Windows (RegisterHotKey) on its own thread."""

    def __init__(self, on_trigger):
        self.on_trigger = on_trigger
        self._thread = None
        self._tid = None
        self._shortcuts = []

    def apply(self, shortcuts):
        if not HOTKEYS_OK:
            return
        self.stop()
        self._shortcuts = shortcuts
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        t, tid = self._thread, self._tid
        self._thread = self._tid = None
        if t and tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(tid, _WM_QUIT, 0, 0)
            except Exception:
                pass
            t.join(timeout=1.0)

    def _run(self):
        u = ctypes.windll.user32
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        registered = []
        for i, (action, mods, vk) in enumerate(self._shortcuts):
            try:
                if u.RegisterHotKey(None, i + 1, mods | MOD_NOREPEAT, vk):
                    registered.append(i + 1)
            except Exception:
                pass
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == _WM_HOTKEY:
                idx = int(msg.wParam) - 1
                if 0 <= idx < len(self._shortcuts):
                    self.on_trigger(self._shortcuts[idx][0])
        for hid in registered:
            try:
                u.UnregisterHotKey(None, hid)
            except Exception:
                pass


# =============================== application ===============================
class _NullController:
    """No-op controller used when no bulb is configured."""
    on_status = on_connection = on_online = None

    def __getattr__(self, _):
        return lambda *a, **k: None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.bulbs = load_bulbs()
        self.controllers = [BulbController(c) for c in self.bulbs]
        self.idx = 0
        self.ctrl = self.controllers[0] if self.controllers else _NullController()
        self._online = True

        self._debounce_bright = None
        self._debounce_temp = None
        self._syncing = False        # avoids firing commands while reflecting status
        self._mute_until = 0.0       # ignore polls for a few sec after a user action
        self.prefs = load_prefs()
        self._fade = bool(self.prefs.get("fade"))
        for c in self.controllers:
            c.fade = self._fade
        self._tray = None
        self._tray_active = False
        self._timer_id = None
        self._timer_left = 0
        self._dn_period = None       # current 'day' / 'night' (scheduler)
        self._dn_base_b = None       # night base brightness (for the ramp)
        self._dn_last_target = None  # last ramp brightness sent (avoids re-send)
        self._ambient_active = False  # ambient mode (ambilight)

        self.title("Bulb Control")
        self.configure(bg=BG)
        self.resizable(False, False)
        try:
            self._icon = tk.PhotoImage(file=ICON)
            self.iconphoto(True, self._icon)
        except Exception:
            pass
        self._bind_display(self.ctrl)
        self._build_ui()

        pos = self.prefs.get("window_pos")
        if pos:
            try:
                self.geometry(pos)   # restore the last position
            except Exception:
                pass

        if self.bulbs:
            self.after(300, self.ctrl.request_status)
            # do NOT apply the default state when the app opens (preserves the current
            # light); the default only kicks in when the bulb comes back online (switch).
        else:
            self._status("no bulb - opening configuration...", AMBER)
            self.after(500, self._open_config)
        self.after(7000, self._poll_status)    # checks state/availability periodically
        self.after(1500, self._dn_loop)        # day/night scheduler
        self.hotkeys = HotkeyManager(self._hotkey_trigger)
        self.after(1200, self._apply_shortcuts)
        self.after(400, self._start_tray)      # tray icon always present
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- UI building ----------
    def _card(self, parent, title=None):
        outer = tk.Frame(parent, bg=CARD)
        outer.pack(fill="x", padx=6, pady=(0, 7))
        inner = tk.Frame(outer, bg=CARD)
        inner.pack(fill="x", padx=12, pady=8)
        if title:
            tk.Label(inner, text=title, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 3))
        return outer, inner

    # ---------- multi-bulb ----------
    def _active_name(self):
        if self.bulbs and 0 <= self.idx < len(self.bulbs):
            return self.bulbs[self.idx].get("name", "Bulb")
        return "No bulb"

    def _bind_display(self, ctrl):
        """Route the status/connection callbacks to the displayed controller."""
        for c in self.controllers:
            c.on_status = c.on_connection = c.on_online = None
        ctrl.on_status = self._status_received
        ctrl.on_connection = self._connection_changed
        ctrl.on_online = self._online_changed

    def _build_selector(self):
        for w in self.sel_frame.winfo_children():
            w.destroy()
        if len(self.bulbs) > 1:
            tabs = tk.Frame(self.sel_frame, bg=CARD)
            tabs.pack(side="left")
            for i, lmp in enumerate(self.bulbs):
                b = RoundedButton(tabs, text=lmp.get("name", f"Bulb {i + 1}"),
                                  width=96, height=26, radius=9,
                                  command=lambda x=i: self._select_bulb(x))
                b.pack(side="left", padx=(0, 4))
                if i == self.idx:
                    b.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
        RoundedButton(self.sel_frame, text="⚙ Bulbs", width=104, height=26, radius=9,
                      command=self._open_config).pack(side="right")

    def _select_bulb(self, idx):
        if idx == self.idx or not (0 <= idx < len(self.controllers)):
            return
        # don't let ambient/scene "migrate" to another bulb
        self._stop_active_effects()
        self.idx = idx
        self.ctrl = self.controllers[idx]
        self._bind_display(self.ctrl)
        self.lbl_title.config(text=self._active_name())
        self._build_selector()
        self._status(f"bulb: {self._active_name()}")
        self.ctrl.request_status()

    def _stop_active_effects(self):
        """Turn off ambient mode and the moving scene of the currently active bulb."""
        if self._ambient_active:
            self._ambient_active = False
            self._reflect_ambient()
        try:
            self.ctrl.stop_scene()
        except Exception:
            pass

    def _open_config(self):
        ConfigWindow(self)

    def reload_bulbs(self):
        self._stop_active_effects()
        current_id = self.bulbs[self.idx].get("id") if (
            self.bulbs and 0 <= self.idx < len(self.bulbs)) else None
        for c in self.controllers:
            try:
                c.shutdown()
            except Exception:
                pass
        self.bulbs = load_bulbs()
        self.controllers = [BulbController(c) for c in self.bulbs]
        for c in self.controllers:
            c.fade = self._fade
        # keep the selected bulb if it still exists
        self.idx = next((i for i, l in enumerate(self.bulbs)
                         if l.get("id") == current_id), 0)
        self.ctrl = self.controllers[self.idx] if self.controllers else _NullController()
        self._bind_display(self.ctrl)
        self.lbl_title.config(text=self._active_name())
        self._build_selector()
        if self.controllers:
            self.ctrl.request_status()
            self._status("configuration updated", OK)
        else:
            self._status("no bulb configured", AMBER)

    def _build_ui(self):
        tk.Frame(self, bg=BG, height=8).pack()  # top breathing room

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=6)
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", anchor="n")
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", anchor="n")

        # ===================== LEFT COLUMN =====================
        # Header
        _, head = self._card(left)
        top = tk.Frame(head, bg=CARD)
        top.pack(fill="x")
        self.lbl_title = tk.Label(top, text=self._active_name(), bg=CARD, fg=FG,
                                  font=("Segoe UI Semibold", 16))
        self.lbl_title.pack(side="left")
        self.lbl_status = tk.Label(top, text="connecting...", bg=CARD, fg=MUTED,
                                   font=("Segoe UI", 8))
        self.lbl_status.pack(side="right", pady=(7, 0))
        # bulb selector + config gear
        self.sel_frame = tk.Frame(head, bg=CARD)
        self.sel_frame.pack(fill="x", pady=(6, 0))
        self._build_selector()
        power_row = tk.Frame(head, bg=CARD)
        power_row.pack(fill="x", pady=(8, 0))
        self.var_power = tk.BooleanVar(value=True)
        self.btn_power = RoundedButton(power_row, text="ON", command=self._toggle_power,
                                       width=180, height=44, radius=13, fill=ACCENT,
                                       hover=ACCENT_HOVER, active=ACCENT_ACTIVE, fg="white",
                                       font=("Segoe UI Semibold", 12))
        self.btn_power.pack(side="left")
        self.swatch = Swatch(power_row)
        self.swatch.pack(side="right")
        # discreet warning (only shows when the bulb is unreachable)
        self.lbl_warn = tk.Label(head, text="", bg=CARD, fg=AMBER, anchor="w",
                                 justify="left", font=("Segoe UI", 9))

        # Mode (segmented)
        _, cmode = self._card(left, "MODE")
        seg = tk.Frame(cmode, bg=CARD)
        seg.pack(fill="x")
        self.var_mode = tk.StringVar(value="white")
        self.btn_white = RoundedButton(seg, text="White", width=132, height=32, radius=10,
                                       command=lambda: self._select_mode("white"))
        self.btn_white.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_color = RoundedButton(seg, text="Color", width=132, height=32, radius=10,
                                       command=lambda: self._select_mode("colour"))
        self.btn_color.pack(side="left", expand=True, fill="x", padx=(4, 0))

        # Brightness
        _, cbri = self._card(left)
        self.lbl_bright = tk.Label(cbri, text="Brightness — 100%", bg=CARD, fg=FG,
                                   font=("Segoe UI", 10))
        self.lbl_bright.pack(anchor="w")
        self.var_bright = tk.IntVar(value=100)
        self.sld_bright = Slider(cbri, self.var_bright, from_=1, to=100, width=276,
                                 command=self._brightness_changed)
        self.sld_bright.pack(fill="x", pady=(6, 0))

        # Temperature (white mode only)
        self.card_temp, ctmp = self._card(left)
        self.lbl_temp = tk.Label(ctmp, text="Temperature — 50%   (warm ↔ cool)",
                                 bg=CARD, fg=FG, font=("Segoe UI", 10))
        self.lbl_temp.pack(anchor="w")
        self.var_temp = tk.IntVar(value=50)
        self.sld_temp = Slider(ctmp, self.var_temp, from_=0, to=100, width=276,
                               command=self._temp_changed)
        self.sld_temp.pack(fill="x", pady=(6, 0))

        # Colors
        self.card_colors, ccol = self._card(left, "COLORS")
        grid = tk.Frame(ccol, bg=CARD)
        grid.pack(fill="x")
        for name, rgb in PRESETS.items():
            ColorDot(grid, rgb, command=lambda c=rgb: self._apply_color(c)).pack(
                side="left", expand=True)
        RoundedButton(ccol, text="Pick color...", width=140, height=30, radius=10,
                      command=self._pick_color).pack(anchor="w", pady=(8, 0))

        # Day / Night automatic
        _, cdn = self._card(left, "DAY / NIGHT (AUTOMATIC)")
        dn_row = tk.Frame(cdn, bg=CARD)
        dn_row.pack(fill="x")
        self.btn_dn = RoundedButton(dn_row, text="", width=130, height=30, radius=10,
                                    command=self._toggle_day_night)
        self.btn_dn.pack(side="left")
        RoundedButton(dn_row, text="Configure...", width=120, height=30, radius=10,
                      command=self._open_day_night).pack(side="right")
        self.lbl_dn = tk.Label(cdn, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_dn.pack(anchor="w", pady=(6, 0))
        self._reflect_day_night()

        # ===================== RIGHT COLUMN =====================
        # Static scenes
        _, cfix = self._card(right, "STATIC SCENES")
        gfix = tk.Frame(cfix, bg=CARD)
        gfix.pack(fill="x")
        for name, temp, bri in STATIC_SCENES:
            RoundedButton(gfix, text=name, width=88, height=32, radius=10,
                          command=lambda n=name, t=temp, b=bri: self._static_scene(n, t, b)).pack(
                side="left", expand=True, fill="x", padx=2)

        # Moving scenes
        _, cmov = self._card(right, "MOVING SCENES")
        gmov = tk.Frame(cmov, bg=CARD)
        gmov.pack(fill="x")
        for name, gen in MOVING_SCENES:
            RoundedButton(gmov, text=name, width=88, height=32, radius=10,
                          command=lambda n=name, g=gen: self._moving_scene(n, g)).pack(
                side="left", expand=True, fill="x", padx=2)
        RoundedButton(cmov, text="Stop scene", width=110, height=28, radius=9,
                      fill=STOP, hover=STOP_HOVER, active=STOP_HOVER,
                      command=self._stop_scene).pack(anchor="w", pady=(8, 0))

        # Ambient mode (Ambilight)
        _, camb = self._card(right, "AMBIENT MODE (SCREEN)")
        self.btn_ambient = RoundedButton(camb, text="", width=160, height=30, radius=10,
                                         command=self._toggle_ambient)
        self.btn_ambient.pack(anchor="w")
        tk.Label(camb, text="the light follows the screen's dominant color",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 0))
        self._reflect_ambient()

        # Favorites
        _, cfav = self._card(right, "FAVORITES")
        self.fav_frame = tk.Frame(cfav, bg=CARD)
        self.fav_frame.pack(fill="x")
        RoundedButton(cfav, text="+  Save current as favorite", width=250, height=30, radius=10,
                      command=self._save_favorite).pack(anchor="w", pady=(8, 0))
        self._render_favorites()

        # Sleep timer
        _, ctim = self._card(right, "SLEEP TIMER")
        gtim = tk.Frame(ctim, bg=CARD)
        gtim.pack(fill="x")
        for mins in (15, 30, 60):
            RoundedButton(gtim, text=f"{mins} min", width=70, height=30, radius=10,
                          command=lambda mm=mins: self._set_timer(mm)).pack(
                side="left", expand=True, fill="x", padx=2)
        custom = tk.Frame(ctim, bg=CARD)
        custom.pack(fill="x", pady=(6, 0))
        tk.Label(custom, text="Custom:", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        self.ent_timer = tk.Entry(custom, width=5, bg=CARD2, fg=FG, insertbackground=FG,
                                  relief="flat", justify="center", font=("Segoe UI", 10))
        self.ent_timer.pack(side="left", padx=6, ipady=3)
        self.ent_timer.bind("<Return>", lambda e: self._custom_timer())
        tk.Label(custom, text="min", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        RoundedButton(custom, text="Start", width=66, height=28, radius=9,
                      command=self._custom_timer).pack(side="right")
        tim_foot = tk.Frame(ctim, bg=CARD)
        tim_foot.pack(fill="x", pady=(8, 0))
        RoundedButton(tim_foot, text="Cancel", width=110, height=28, radius=9,
                      fill=STOP, hover=STOP_HOVER, active=STOP_HOVER,
                      command=self._cancel_timer).pack(side="left")
        self.lbl_timer = tk.Label(tim_foot, text="—", bg=CARD, fg=MUTED,
                                  font=("Segoe UI", 10))
        self.lbl_timer.pack(side="right")

        # Default state
        _, cdef = self._card(right, "DEFAULT STATE")
        def_row = tk.Frame(cdef, bg=CARD)
        def_row.pack(fill="x")
        RoundedButton(def_row, text="Save current", width=120, height=30, radius=10,
                      command=self._save_default).pack(side="left", padx=(0, 6))
        RoundedButton(def_row, text="Apply", width=96, height=30, radius=10,
                      command=self._apply_default).pack(side="left")
        self.btn_on_power = RoundedButton(cdef, text="", width=250, height=28, radius=9,
                                          command=self._toggle_on_power)
        self.btn_on_power.pack(anchor="w", pady=(8, 0))
        self._reflect_on_power()

        # Footer (below the two columns)
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=12, pady=(2, 10))
        RoundedButton(foot, text="Refresh state", width=140, height=30, radius=10,
                      command=lambda: self.ctrl.request_status()).pack(side="left")
        self.btn_fade = RoundedButton(foot, text="", width=160, height=30, radius=10,
                                      command=self._toggle_fade)
        self.btn_fade.pack(side="left", padx=(8, 0))
        self._reflect_fade()
        RoundedButton(foot, text="⌨ Shortcuts", width=110, height=30, radius=10,
                      command=self._open_shortcuts).pack(side="right")

        self._select_mode("white", send=False)
        self._update_mode_visibility()
        self._update_white_swatch()

    # ---------- visual-state helpers ----------
    def _mark_action(self):
        """After a user action, ignore the poll for a few seconds so the periodic
        read doesn't 'revert' the menu/sliders to the previous state."""
        self._mute_until = time.monotonic() + 3.0

    def _status(self, msg, color=MUTED):
        self.lbl_status.config(text=msg, fg=color)

    def _reflect_power(self, on):
        self.btn_power.set_text("ON" if on else "OFF")
        if on:
            self.btn_power.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
        else:
            self.btn_power.set_colors(OFF, OFF_HOVER, OFF_ACTIVE)

    def _set_mode_ui(self, mode):
        if mode == "white":
            self.btn_white.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
            self.btn_color.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)
        else:
            self.btn_color.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
            self.btn_white.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)

    def _reflect_on_power(self):
        on = bool(self.prefs.get("apply_on_power"))
        self.btn_on_power.set_text(("●  " if on else "○  ") + "Apply when bulb powers on")
        if on:
            self.btn_on_power.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
        else:
            self.btn_on_power.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)

    def _update_mode_visibility(self):
        if self.var_mode.get() == "white":
            self.card_temp.pack(fill="x", padx=6, pady=(0, 7), before=self.card_colors)
        else:
            self.card_temp.pack_forget()

    def _update_white_swatch(self):
        self.swatch.set(temp_to_rgb(int(self.var_temp.get()), int(self.var_bright.get())))

    # ---------- UI callbacks ----------
    def _toggle_power(self):
        self._mark_action()
        new = not self.var_power.get()
        self.var_power.set(new)
        self._reflect_power(new)
        self.ctrl.power(new)

    def _select_mode(self, mode, send=True):
        self.var_mode.set(mode)
        self._set_mode_ui(mode)
        self._update_mode_visibility()
        if not send or self._syncing:
            return
        self._mark_action()
        if mode == "white":
            self.ctrl.white_mode()
            self._update_white_swatch()
        else:
            self._apply_color(self._current_color_rgb(), switch_mode=False)

    def _brightness_changed(self, _=None):
        if self._syncing:
            return
        self._mark_action()
        pct = int(float(self.var_bright.get()))
        self.lbl_bright.config(text=f"Brightness — {pct}%")
        if self.var_mode.get() == "white":
            self._update_white_swatch()
        if self._debounce_bright:
            self.after_cancel(self._debounce_bright)
        self._debounce_bright = self.after(220, lambda: self.ctrl.brightness(pct))

    def _temp_changed(self, _=None):
        if self._syncing:
            return
        self._mark_action()
        pct = int(float(self.var_temp.get()))
        self.lbl_temp.config(text=f"Temperature — {pct}%   (warm ↔ cool)")
        self._update_white_swatch()
        if self._debounce_temp:
            self.after_cancel(self._debounce_temp)
        self._debounce_temp = self.after(220, lambda: self.ctrl.temperature(pct))

    def _pick_color(self):
        rgb, _ = colorchooser.askcolor(color=self._current_color_hex(), parent=self,
                                       title="Pick color")
        if rgb:
            self._apply_color(tuple(int(c) for c in rgb))

    def _apply_color(self, rgb, switch_mode=True):
        self._mark_action()
        is_white, adj = displayable_color(rgb)
        if is_white:
            # nearly unsaturated colour -> the bulb shows it better as white
            self.var_mode.set("white")
            self._set_mode_ui("white")
            self._update_mode_visibility()
            self.ctrl.white_mode()
            self._update_white_swatch()
            self._status("color too pale — shown as white", MUTED)
            return
        if switch_mode:
            self.var_mode.set("colour")
            self._set_mode_ui("colour")
            self._update_mode_visibility()
        self.swatch.set(adj)            # show the colour that will actually appear
        self.ctrl.color(adj)

    def _toggle_fade(self):
        self._fade = not self._fade
        self.prefs["fade"] = self._fade
        save_prefs(self.prefs)
        for c in self.controllers:
            c.fade = self._fade
        self._reflect_fade()

    def _reflect_fade(self):
        on = self._fade
        self.btn_fade.set_text(("●  " if on else "○  ") + "Smooth transition")
        if on:
            self.btn_fade.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
        else:
            self.btn_fade.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)

    def _current_color_hex(self):
        return "#%02x%02x%02x" % self._current_color_rgb()

    def _current_color_rgb(self):
        h = self.swatch.itemcget(self.swatch._shape, "fill").lstrip("#")
        if len(h) == 6:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        return (255, 255, 255)

    # ---------- scenes and default state ----------
    def _static_scene(self, name, temp, brightness):
        self._mark_action()
        self._syncing = True
        try:
            self.var_mode.set("white")
            self._set_mode_ui("white")
            self.var_bright.set(brightness)
            self.lbl_bright.config(text=f"Brightness — {brightness}%")
            self.var_temp.set(temp)
            self.lbl_temp.config(text=f"Temperature — {temp}%   (warm ↔ cool)")
            self._update_white_swatch()
            self._update_mode_visibility()
        finally:
            self._syncing = False
        self.ctrl.apply_func(build_state_func(
            {"mode": "white", "temp": temp, "brightness": brightness}))
        self._status(f"scene: {name}")

    def _moving_scene(self, name, generator):
        self._mark_action()
        self.var_power.set(True)
        self._reflect_power(True)
        self._status(f"scene: {name} (moving)", ACCENT)
        self.ctrl.start_scene(generator)

    def _stop_scene(self):
        self.ctrl.stop_scene()
        self._status("scene stopped")

    def _current_state(self):
        mode = self.var_mode.get()
        st = {"mode": mode, "brightness": int(self.var_bright.get())}
        if mode == "colour":
            st["color"] = list(self._current_color_rgb())
        else:
            st["temp"] = int(self.var_temp.get())
        return st

    def _save_default(self):
        self.prefs["default"] = self._current_state()
        save_prefs(self.prefs)
        self._status("default saved", OK)

    def _apply_state(self, st, msg=None):
        """Reflect a saved state (default/favorite) on the UI and apply it on the bulb."""
        self._mark_action()
        self._syncing = True
        try:
            mode = st.get("mode", "white")
            self.var_mode.set(mode)
            self._set_mode_ui(mode)
            self.var_bright.set(int(st.get("brightness", 100)))
            self.lbl_bright.config(text=f"Brightness — {int(st.get('brightness', 100))}%")
            if mode == "colour" and st.get("color"):
                self.swatch.set(tuple(st["color"]))
            else:
                self.var_temp.set(int(st.get("temp", 50)))
                self.lbl_temp.config(
                    text=f"Temperature — {int(st.get('temp', 50))}%   (warm ↔ cool)")
                self._update_white_swatch()
            self.var_power.set(True)
            self._reflect_power(True)
            self._update_mode_visibility()
        finally:
            self._syncing = False
        self.ctrl.apply_func(build_state_func(st))
        if msg:
            self._status(msg, OK)

    def _apply_default(self):
        st = self.prefs.get("default")
        if not st:
            messagebox.showinfo("Default state",
                                "No default state saved yet.\n"
                                "Adjust the light and click 'Save current'.")
            return
        self._apply_state(st, "default applied")

    def _toggle_on_power(self):
        self.prefs["apply_on_power"] = not bool(self.prefs.get("apply_on_power"))
        save_prefs(self.prefs)
        self._reflect_on_power()

    # ---------- favorites ----------
    def _render_favorites(self):
        for w in self.fav_frame.winfo_children():
            w.destroy()
        favs = self.prefs.get("favorites", [])
        if not favs:
            tk.Label(self.fav_frame, text="(no favorites saved)", bg=CARD, fg=MUTED,
                     font=("Segoe UI", 9)).pack(anchor="w")
            return
        for i, f in enumerate(favs):
            row = tk.Frame(self.fav_frame, bg=CARD)
            row.pack(fill="x", pady=2)
            RoundedButton(row, text=f.get("name", "favorite"), width=210, height=28, radius=9,
                          command=lambda e=f.get("state", {}):
                          self._apply_state(e, "favorite applied")).pack(
                side="left", expand=True, fill="x")
            RoundedButton(row, text="✕", width=30, height=28, radius=9,
                          fill=STOP, hover=STOP_HOVER, active=STOP_HOVER,
                          command=lambda idx=i: self._delete_favorite(idx)).pack(
                side="right", padx=(6, 0))

    def _save_favorite(self):
        name = simpledialog.askstring("New favorite", "Favorite name:", parent=self)
        if not name or not name.strip():
            return
        self.prefs.setdefault("favorites", []).append(
            {"name": name.strip(), "state": self._current_state()})
        save_prefs(self.prefs)
        self._render_favorites()
        self._status(f"favorite '{name.strip()}' saved", OK)

    def _delete_favorite(self, idx):
        favs = self.prefs.get("favorites", [])
        if 0 <= idx < len(favs):
            name = favs[idx].get("name", "favorite")
            if messagebox.askyesno("Delete favorite", f"Delete the favorite '{name}'?",
                                    parent=self):
                favs.pop(idx)
                save_prefs(self.prefs)
                self._render_favorites()
                self._status("favorite deleted")

    # ---------- sleep timer ----------
    def _set_timer(self, minutes):
        self._cancel_timer(silent=True)
        self._timer_left = minutes * 60
        self._status(f"timer set for {minutes} min", ACCENT)
        self._tick_timer()

    def _tick_timer(self):
        if self._timer_left <= 0:
            self._timer_id = None
            self.lbl_timer.config(text="—")
            self._ambient_active = False           # stop ambilight if it's on
            self._reflect_ambient()
            self.ctrl.stop_scene()                 # stop any moving scene
            self.var_power.set(False)
            self._reflect_power(False)
            self.ctrl.power(False)
            self._status("turned off by the timer", OK)
            return
        m, s = divmod(self._timer_left, 60)
        self.lbl_timer.config(text=f"⏱ {m:02d}:{s:02d}")
        self._timer_left -= 1
        self._timer_id = self.after(1000, self._tick_timer)

    def _cancel_timer(self, silent=False):
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        self._timer_left = 0
        self.lbl_timer.config(text="—")
        if not silent:
            self._status("timer cancelled")

    def _custom_timer(self):
        try:
            mins = int(self.ent_timer.get().strip())
        except ValueError:
            mins = 0
        if mins > 0:
            self._set_timer(mins)
        else:
            self._status("enter a valid number of minutes", WARN)

    # ---------- day / night (automatic schedule) ----------
    def _reflect_day_night(self):
        on = bool((self.prefs.get("day_night") or {}).get("active"))
        self.btn_dn.set_text(("●  " if on else "○  ") + "Automatic")
        if on:
            self.btn_dn.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
        else:
            self.btn_dn.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)
        self._dn_update_label()

    def _toggle_day_night(self):
        cfg = self.prefs.setdefault("day_night", {})
        if not cfg.get("active") and not (cfg.get("day_fav") and cfg.get("night_fav")):
            messagebox.showinfo("Day / Night",
                                "Configure first: click 'Configure...' and pick a favorite "
                                "for day and another for night.", parent=self)
            return
        cfg["active"] = not cfg.get("active")
        save_prefs(self.prefs)
        self._dn_period = None
        self._reflect_day_night()
        if cfg["active"]:
            self._dn_evaluate()

    def _open_day_night(self):
        DayNightWindow(self)

    # ---------- global shortcuts ----------
    def _hotkey_trigger(self, action):
        self.after(0, lambda: self._run_shortcut(action))

    def _run_shortcut(self, action):
        if action == "toggle_power":
            self._toggle_power()
        elif action == "show":
            if self.winfo_viewable():
                self._on_close()                     # hide to tray
            else:
                self.deiconify(); self.lift(); self.focus_force()
        elif action == "default":
            self._apply_default()
        elif action == "stop_scene":
            self._stop_scene()

    def _build_shortcut_list(self):
        lst = []
        cfgs = self.prefs.get("shortcuts") or {}
        for action, _ in SHORTCUT_ACTIONS:
            a = cfgs.get(action)
            if not (a and a.get("active") and a.get("key")):
                continue
            mods = ((MOD_CONTROL if a.get("ctrl") else 0) | (MOD_ALT if a.get("alt") else 0) |
                    (MOD_SHIFT if a.get("shift") else 0) | (MOD_WIN if a.get("win") else 0))
            vk = _key_to_vk(a["key"])
            if mods and vk:   # requires at least one modifier
                lst.append((action, mods, vk))
        return lst

    def _apply_shortcuts(self):
        self.hotkeys.apply(self._build_shortcut_list())

    def _open_shortcuts(self):
        ShortcutsWindow(self)

    # ---------- ambient mode (ambilight) ----------
    def _reflect_ambient(self):
        on = self._ambient_active
        self.btn_ambient.set_text(("●  " if on else "○  ") + "Ambient Mode")
        if on:
            self.btn_ambient.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
        else:
            self.btn_ambient.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)

    def _toggle_ambient(self):
        if self._ambient_active:
            self._ambient_active = False
            self._status("ambient mode off")
        elif not TRAY_OK:
            messagebox.showinfo("Ambient Mode",
                                "Screen capture (Pillow) unavailable in this build.",
                                parent=self)
            return
        else:
            self._ambient_active = True
            self._mark_action()
            self.var_mode.set("colour")
            self._set_mode_ui("colour")
            self._update_mode_visibility()
            self._status("ambient mode on", ACCENT)
            threading.Thread(target=self._ambient_loop, daemon=True).start()
        self._reflect_ambient()

    def _ambient_loop(self):
        prev = None
        while self._ambient_active:
            try:
                px = list(ImageGrab.grab().resize((48, 27)).getdata())
                # circular hue mean weighted by saturation*value: vivid pixels
                # dominate; white/gray/UI barely count
                sx = sy = wsum = vsum = 0.0
                for p in px:
                    h, s, v = colorsys.rgb_to_hsv(p[0] / 255, p[1] / 255, p[2] / 255)
                    w = s * v
                    ang = h * 6.2831853
                    sx += math.cos(ang) * w
                    sy += math.sin(ang) * w
                    wsum += w
                    vsum += v
                n = len(px)
                val = max(0.30, min(1.0, vsum / n * 1.3))
                if wsum > 0.02 * n:        # there's a relevant colour on screen
                    hue = (math.atan2(sy, sx) / 6.2831853) % 1.0
                    rr, gg, bb = colorsys.hsv_to_rgb(hue, 0.9, val)
                else:                       # neutral screen -> soft warm white
                    rr, gg, bb = colorsys.hsv_to_rgb(0.09, 0.25, val)
                cor = [int(rr * 255), int(gg * 255), int(bb * 255)]
                if prev:                    # smooth to reduce flicker
                    cor = [int(cor[i] * 0.6 + prev[i] * 0.4) for i in range(3)]
                prev = cor
                c = tuple(cor)
                self.ctrl.color_direct(c)
                self.after(0, lambda x=c: self.swatch.set(x))
            except Exception:
                pass
            time.sleep(0.3)

    def _fav_by_name(self, name):
        for f in self.prefs.get("favorites", []):
            if f.get("name") == name:
                return f.get("state")
        return None

    @staticmethod
    def _hhmm(s):
        try:
            h, m = str(s).split(":")
            return int(h) * 60 + int(m)
        except Exception:
            return 0

    def _dn_loop(self):
        self.after(60000, self._dn_loop)
        self._dn_evaluate()

    def _dn_evaluate(self):
        cfg = self.prefs.get("day_night") or {}
        if not cfg.get("active") or not self.controllers:
            self._dn_update_label()
            return
        now = datetime.datetime.now()
        nm = now.hour * 60 + now.minute
        ds = self._hhmm(cfg.get("day_time", "07:00"))
        ns = self._hhmm(cfg.get("night_time", "18:00"))
        period = "day" if (ds <= nm < ns) else "night"
        if period != self._dn_period:
            self._dn_period = period
            self._dn_last_target = None
            name = cfg.get("day_fav") if period == "day" else cfg.get("night_fav")
            fav = self._fav_by_name(name)
            if fav:
                self._apply_state(dict(fav))
            self._dn_base_b = int((fav or {}).get("brightness", 100))
        if period == "night":
            self._dn_ramp(cfg, nm, ns)
        self._dn_update_label()

    def _dn_ramp(self, cfg, nm, ns):
        ramp = max(1, int(cfg.get("ramp_min", 120)))
        minb = max(1, min(100, int(cfg.get("brightness_min", 10))))
        base = self._dn_base_b if self._dn_base_b is not None else 100
        elapsed = nm - ns if nm >= ns else nm + (1440 - ns)
        frac = min(1.0, elapsed / ramp)
        target = max(1, min(100, round(base + (minb - base) * frac)))
        # only send when the computed TARGET changes (ignores the poll's rounding)
        if target != self._dn_last_target:
            self._dn_last_target = target
            self._mark_action()
            self.var_bright.set(target)
            self.lbl_bright.config(text=f"Brightness — {target}%")
            if self.var_mode.get() == "white":
                self._update_white_swatch()
            self.ctrl.brightness_direct(target)   # direct, no fade (the ramp is already gradual)

    def _dn_update_label(self):
        cfg = self.prefs.get("day_night") or {}
        if not cfg.get("active"):
            self.lbl_dn.config(text="off")
            return
        self.lbl_dn.config(text=f"now: {self._dn_period or '—'}")

    # ---------- controller callbacks (run on the worker thread) ----------
    def _status_received(self, dps):
        self.after(0, lambda: self._apply_status(dps))

    def _connection_changed(self, ok, msg):
        # only shows successful connection messages; failures go to the discreet warning
        if ok and msg:
            self.after(0, lambda: self._status(msg, OK))

    def _online_changed(self, online):
        self.after(0, lambda: self._set_online(online))

    def _set_online(self, online):
        if online == self._online:
            return
        came_back = online and not self._online   # was offline and came back (switch)
        self._online = online
        if online:
            self.lbl_warn.pack_forget()
            if came_back:
                self.after(800, self._on_bulb_power_on)
        else:
            self.lbl_warn.config(
                text="⚠  Bulb offline — turn it on at the wall switch")
            self.lbl_warn.pack(fill="x", pady=(8, 0))

    def _on_bulb_power_on(self):
        """When the bulb comes back online (wall switch turned on): apply the
        day/night profile if active, or the default state (if configured)."""
        if not self.controllers:
            return
        if (self.prefs.get("day_night") or {}).get("active"):
            self._dn_period = None
            self._dn_evaluate()
        elif self.prefs.get("apply_on_power") and self.prefs.get("default"):
            self._apply_state(self.prefs["default"], "default applied")

    def _poll_status(self):
        if self.controllers:
            self.ctrl.request_status()
        self.after(7000, self._poll_status)

    def _apply_status(self, dps):
        if time.monotonic() < self._mute_until:
            return   # recent user action: don't let the poll overwrite the UI
        self._syncing = True
        try:
            if DP_POWER in dps:
                on = bool(dps[DP_POWER])
                self.var_power.set(on)
                self._reflect_power(on)
            mode = self.var_mode.get()   # if status doesn't carry the mode, keep the current one
            if DP_MODE in dps:
                mode = "colour" if dps[DP_MODE] == "colour" else "white"
                self.var_mode.set(mode)
                self._set_mode_ui(mode)
            if DP_BRIGHT in dps:
                v = int(dps[DP_BRIGHT])
                pct = max(1, min(100, round((v - BRIGHT_MIN) / (BRIGHT_MAX - BRIGHT_MIN) * 100)))
                # 1% dead zone: ignores the round-trip rounding wobble
                if abs(pct - int(self.var_bright.get())) > 1:
                    self.var_bright.set(pct)
                    self.lbl_bright.config(text=f"Brightness — {pct}%")
            if DP_TEMP in dps:
                pct = round(int(dps[DP_TEMP]) / 1000 * 100)
                if abs(pct - int(self.var_temp.get())) > 1:
                    self.var_temp.set(pct)
                    self.lbl_temp.config(text=f"Temperature — {pct}%   (warm ↔ cool)")
            if mode == "colour":
                if dps.get(DP_COLOUR):
                    self.swatch.set(parse_hsv_hex(dps[DP_COLOUR]))
            else:
                self._update_white_swatch()
            self._update_mode_visibility()
        finally:
            self._syncing = False

    # ---------- system tray / close ----------
    def _create_tray(self):
        img = Image.open(ICON)
        menu = pystray.Menu(
            pystray.MenuItem("Show", lambda i, it: self.after(0, self.deiconify), default=True),
            pystray.MenuItem("Turn on / off", lambda i, it: self.after(0, self._toggle_power)),
            pystray.MenuItem("Quit", lambda i, it: self.after(0, self._quit)),
        )
        return pystray.Icon("tuya_bulb", img, "Bulb Control", menu)

    def _save_pos(self):
        try:
            self.prefs["window_pos"] = f"+{self.winfo_x()}+{self.winfo_y()}"
            save_prefs(self.prefs)
        except Exception:
            pass

    def _start_tray(self):
        """Create the tray icon (stays present the whole time the app runs)."""
        if not TRAY_OK or self._tray_active:
            return
        try:
            self._tray = self._create_tray()
            self._tray_active = True
            threading.Thread(target=self._tray.run, daemon=True).start()
        except Exception:
            pass

    def _on_close(self):
        # closing the window only hides it to the tray (does not quit)
        self._save_pos()
        if TRAY_OK:
            self._start_tray()
            self.withdraw()
        else:
            self._quit()

    def _quit(self):
        self._save_pos()
        self._ambient_active = False
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
        if self._timer_id:
            try:
                self.after_cancel(self._timer_id)
            except Exception:
                pass
        for c in self.controllers:
            try:
                c.shutdown()
            except Exception:
                pass
        self.destroy()


class ConfigWindow(tk.Toplevel):
    """Window to add / edit / remove bulbs (without touching the JSON)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Bulbs")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        self.bulbs = [dict(l) for l in load_bulbs()]  # editable copy

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(top, text="Configured bulbs", bg=BG, fg=FG,
                 font=("Segoe UI Semibold", 13)).pack(side="left")
        self.list = tk.Frame(self, bg=BG)
        self.list.pack(fill="x", padx=14)
        actions = tk.Frame(self, bg=BG)
        actions.pack(fill="x", padx=14, pady=12)
        RoundedButton(actions, text="+ Add", width=110, height=30, radius=10, fill=ACCENT,
                      hover=ACCENT_HOVER, active=ACCENT_ACTIVE, fg="white",
                      command=lambda: self._form()).pack(side="left", padx=(0, 6))
        RoundedButton(actions, text="Scan network", width=130, height=30, radius=10,
                      command=self._scan).pack(side="left")
        RoundedButton(actions, text="Close", width=90, height=30, radius=10,
                      command=self.destroy).pack(side="right")
        self._render_list()

    def _render_list(self):
        for w in self.list.winfo_children():
            w.destroy()
        if not self.bulbs:
            tk.Label(self.list, text="(none - click Add or Scan network)",
                     bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=4)
            return
        for i, l in enumerate(self.bulbs):
            row = tk.Frame(self.list, bg=CARD)
            row.pack(fill="x", pady=3)
            inner = tk.Frame(row, bg=CARD)
            inner.pack(fill="x", padx=10, pady=8)
            tk.Label(inner, text=f"{l.get('name', '(no name)')}   —   {l.get('ip', '?')}",
                     bg=CARD, fg=FG, font=("Segoe UI", 10)).pack(side="left")
            RoundedButton(inner, text="✕", width=30, height=26, radius=8, fill=STOP,
                          hover=STOP_HOVER, active=STOP_HOVER,
                          command=lambda x=i: self._remove(x)).pack(side="right")
            RoundedButton(inner, text="Edit", width=70, height=26, radius=8,
                          command=lambda x=i: self._form(x)).pack(side="right", padx=(0, 6))

    def _form(self, idx=None, base=None):
        source = self.bulbs[idx] if idx is not None else (base or {})
        win = tk.Toplevel(self)
        win.title("Edit bulb" if idx is not None else "New bulb")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self)
        fields = [("Name", "name"), ("ID (Device ID)", "id"), ("IP on the network", "ip"),
                  ("Local key", "key"), ("Version (3.3 / 3.4 / 3.5)", "version")]
        ents = {}
        for label, key in fields:
            fr = tk.Frame(win, bg=BG)
            fr.pack(fill="x", padx=14, pady=4)
            tk.Label(fr, text=label, bg=BG, fg=MUTED, width=22, anchor="w",
                     font=("Segoe UI", 9)).pack(side="left")
            e = tk.Entry(fr, width=32, bg=CARD2, fg=FG, insertbackground=FG, relief="flat",
                         font=("Segoe UI", 10))
            default = source.get(key, "3.5" if key == "version" else "")
            e.insert(0, str(default))
            e.pack(side="left", ipady=3)
            ents[key] = e
        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=14, pady=12)

        def save():
            new = {k: ents[k].get().strip() for _, k in fields}
            if not (new["id"] and new["ip"] and new["key"]):
                messagebox.showwarning("Required fields",
                                       "ID, IP and Local key are required.", parent=win)
                return
            if not new.get("name"):
                new["name"] = "Bulb"
            if not new.get("version"):
                new["version"] = "3.5"
            if idx is not None:
                self.bulbs[idx] = {**self.bulbs[idx], **new}
            else:
                self.bulbs.append(new)
            self._save_and_refresh()
            win.destroy()

        RoundedButton(bar, text="Save", width=100, height=30, radius=10, fill=ACCENT,
                      hover=ACCENT_HOVER, active=ACCENT_ACTIVE, fg="white",
                      command=save).pack(side="left")
        RoundedButton(bar, text="Cancel", width=100, height=30, radius=10,
                      command=win.destroy).pack(side="right")

    def _remove(self, idx):
        if 0 <= idx < len(self.bulbs):
            name = self.bulbs[idx].get("name", "this bulb")
            if messagebox.askyesno("Remove", f"Remove '{name}'?", parent=self):
                self.bulbs.pop(idx)
                self._save_and_refresh()

    def _scan(self):
        # the scan takes ~12s; run it on a thread so the window doesn't freeze
        self.config(cursor="watch")
        self.title("Bulbs - scanning the network...")

        def work():
            try:
                found = tinytuya.deviceScan(False, 12)
            except Exception:
                found = {}
            self.after(0, lambda: self._scan_done(found))

        threading.Thread(target=work, daemon=True).start()

    def _scan_done(self, found):
        if not self.winfo_exists():
            return
        self.config(cursor="")
        self.title("Bulbs")
        existing = {l.get("id") for l in self.bulbs}
        new = [v for v in found.values() if (v.get("gwId") or v.get("id")) not in existing]
        if not new:
            messagebox.showinfo("Scan network",
                                "No new bulb found.\n"
                                "(Already-configured ones don't show up. The local key must "
                                "be obtained with get_local_key.py.)", parent=self)
            return
        v = new[0]
        self._form(base={"id": v.get("gwId") or v.get("id"), "ip": v.get("ip", ""),
                         "version": str(v.get("version", "3.5")), "name": "New bulb"})

    def _save_and_refresh(self):
        save_bulbs(self.bulbs)
        self._render_list()
        self.app.reload_bulbs()


class DayNightWindow(tk.Toplevel):
    """Configures the day/night profiles (favorites), times and the night ramp."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Day / Night automatic")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        cfg = dict(app.prefs.get("day_night") or {})
        favs = [f.get("name", "?") for f in app.prefs.get("favorites", [])]

        if not favs:
            tk.Label(self, text="Save at least one Favorite first\n"
                                "(the '+ Save current as favorite' button).",
                     bg=BG, fg=AMBER, font=("Segoe UI", 10), justify="left").pack(
                padx=18, pady=18)
            RoundedButton(self, text="Close", width=90, height=30, radius=10,
                          command=self.destroy).pack(pady=(0, 16))
            return

        def in_list(v, default):
            return v if v in favs else default

        self.var_dfav = tk.StringVar(value=in_list(cfg.get("day_fav"), favs[0]))
        self.var_nfav = tk.StringVar(value=in_list(cfg.get("night_fav"), favs[-1]))
        self.e_dh = self._row("Day — favorite and start time:",
                              self.var_dfav, favs, cfg.get("day_time", "07:00"))
        self.e_nh = self._row("Night — favorite and start time:",
                              self.var_nfav, favs, cfg.get("night_time", "18:00"))

        fr = tk.Frame(self, bg=BG)
        fr.pack(fill="x", padx=16, pady=(12, 2))
        tk.Label(fr, text="From night onward, dim over", bg=BG, fg=FG,
                 font=("Segoe UI", 9)).pack(side="left")
        self.e_ramp = self._entry(fr, str(cfg.get("ramp_min", 120)), 5)
        tk.Label(fr, text="min, down to", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(
            side="left", padx=(6, 0))
        self.e_min = self._entry(fr, str(cfg.get("brightness_min", 10)), 4)
        tk.Label(fr, text="% brightness", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(
            side="left", padx=(6, 0))
        tk.Label(self, text="(at the night time the light applies the favorite and starts\n"
                            "dimming gradually, reaching the minimum at the end of that time)",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), justify="left").pack(
            anchor="w", padx=16, pady=(0, 4))

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=14)
        RoundedButton(bar, text="Save and enable", width=130, height=30, radius=10, fill=ACCENT,
                      hover=ACCENT_HOVER, active=ACCENT_ACTIVE, fg="white",
                      command=self._save).pack(side="left")
        RoundedButton(bar, text="Cancel", width=100, height=30, radius=10,
                      command=self.destroy).pack(side="right")

    def _entry(self, parent, value, w):
        e = tk.Entry(parent, width=w, bg=CARD2, fg=FG, insertbackground=FG, relief="flat",
                     justify="center", font=("Segoe UI", 10))
        e.insert(0, value)
        e.pack(side="left", ipady=2, padx=(6, 0))
        return e

    def _row(self, label, var, favs, time_str):
        tk.Label(self, text=label, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(
            anchor="w", padx=16, pady=(12, 2))
        fr = tk.Frame(self, bg=BG)
        fr.pack(fill="x", padx=16)
        om = tk.OptionMenu(fr, var, *favs)
        om.config(bg=CARD2, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
                  relief="flat", highlightthickness=0, bd=0, font=("Segoe UI", 9), width=16)
        om["menu"].config(bg=CARD2, fg=FG, activebackground=ACCENT, activeforeground="white")
        om.pack(side="left")
        return self._entry(fr, time_str, 7)

    def _save(self):
        cfg = self.app.prefs.setdefault("day_night", {})
        cfg["day_fav"] = self.var_dfav.get()
        cfg["night_fav"] = self.var_nfav.get()
        cfg["day_time"] = self.e_dh.get().strip() or "07:00"
        cfg["night_time"] = self.e_nh.get().strip() or "18:00"
        try:
            cfg["ramp_min"] = max(1, int(self.e_ramp.get()))
        except ValueError:
            cfg["ramp_min"] = 120
        try:
            cfg["brightness_min"] = max(1, min(100, int(self.e_min.get())))
        except ValueError:
            cfg["brightness_min"] = 10
        cfg["active"] = True
        save_prefs(self.app.prefs)
        self.app._dn_period = None
        self.app._reflect_day_night()
        self.app._dn_evaluate()
        self.destroy()


class ShortcutsWindow(tk.Toplevel):
    """Configures global shortcuts (key combos that work across all of Windows)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Global shortcuts")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        if not HOTKEYS_OK:
            tk.Label(self, text="Global shortcuts are only available on Windows.",
                     bg=BG, fg=AMBER, font=("Segoe UI", 10)).pack(padx=18, pady=18)
            RoundedButton(self, text="Close", width=90, height=30, radius=10,
                          command=self.destroy).pack(pady=(0, 16))
            return
        tk.Label(self, text="Shortcuts that work across all of Windows (even minimized).\n"
                            "Tick at least one modifier (Ctrl / Alt / Shift / Win).",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9), justify="left").pack(
            anchor="w", padx=16, pady=(14, 8))
        self.widgets = {}
        cfgs = app.prefs.get("shortcuts") or {}
        for action, label in SHORTCUT_ACTIONS:
            self._row(action, label, cfgs.get(action, {}))
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=14)
        RoundedButton(bar, text="Save", width=100, height=30, radius=10, fill=ACCENT,
                      hover=ACCENT_HOVER, active=ACCENT_ACTIVE, fg="white",
                      command=self._save).pack(side="left")
        RoundedButton(bar, text="Cancel", width=100, height=30, radius=10,
                      command=self.destroy).pack(side="right")

    def _check(self, parent, text, value):
        v = tk.BooleanVar(value=value)
        tk.Checkbutton(parent, text=text, variable=v, bg=BG, fg=FG, selectcolor=CARD2,
                       activebackground=BG, activeforeground=FG, font=("Segoe UI", 8),
                       highlightthickness=0, bd=0).pack(side="left")
        return v

    def _row(self, action, label, a):
        fr = tk.Frame(self, bg=BG)
        fr.pack(fill="x", padx=16, pady=3)
        tk.Label(fr, text=label, bg=BG, fg=FG, width=18, anchor="w",
                 font=("Segoe UI", 9)).pack(side="left")
        v_ctrl = self._check(fr, "Ctrl", a.get("ctrl", True))
        v_alt = self._check(fr, "Alt", a.get("alt", True))
        v_shift = self._check(fr, "Shift", a.get("shift", False))
        v_win = self._check(fr, "Win", a.get("win", False))
        v_key = tk.StringVar(value=a.get("key", "L"))
        om = tk.OptionMenu(fr, v_key, *SHORTCUT_KEYS)
        om.config(bg=CARD2, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
                  relief="flat", highlightthickness=0, bd=0, font=("Segoe UI", 9), width=4)
        om["menu"].config(bg=CARD2, fg=FG, activebackground=ACCENT, activeforeground="white")
        om.pack(side="left", padx=(8, 8))
        v_active = self._check(fr, "Active", a.get("active", False))
        self.widgets[action] = (v_ctrl, v_alt, v_shift, v_win, v_key, v_active)

    def _save(self):
        cfgs = self.app.prefs.setdefault("shortcuts", {})
        for action, (vc, va, vs, vw, vk, vat) in self.widgets.items():
            cfgs[action] = {"ctrl": vc.get(), "alt": va.get(), "shift": vs.get(),
                            "win": vw.get(), "key": vk.get(), "active": vat.get()}
        save_prefs(self.app.prefs)
        self.app._apply_shortcuts()
        self.destroy()


def _set_app_id():
    """On Windows, set a dedicated AppUserModelID so the taskbar uses the window
    icon (instead of the Python one)."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "faderaulas.tuyabulbcontroller")
    except Exception:
        pass


def main():
    _set_app_id()
    app = App()
    # "--tray": start straight into the tray (used for Windows autostart)
    if "--tray" in sys.argv and TRAY_OK and app.bulbs:
        app.after(150, app._on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
