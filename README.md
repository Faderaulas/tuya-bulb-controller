# Tuya Bulb Controller

A clean desktop app to control **Tuya Wi-Fi smart bulbs** entirely over your
**local network** — no cloud, no vendor app, no internet required after setup.

Tested on an **Intelbras EWS 410 (Izy Smart)**, but it works with most Tuya
Wi-Fi colour bulbs (Smart Life / Tuya Smart compatible).

Built with Python + Tkinter + [tinytuya](https://github.com/jasonacox/tinytuya).
By **Faderaulas** · MIT License.

---

## Features

- 🎨 **Color & white** — color picker, presets, brightness and warm↔cool temperature
- 🌈 **Scenes** — static (Reading / Cozy / Movie) and animated (Candle / Rainbow / Breathe)
- ⭐ **Favorites** — save any setup with a name, apply or delete with one click
- ⏱️ **Sleep timer** — 15/30/60 min or a custom value
- 🌗 **Day / Night automatic** — a day favorite and a night favorite, with a gradual
  night dimming ramp down to a minimum brightness
- 🎬 **Ambient mode (Ambilight)** — the light follows your screen's dominant color
- ⌨️ **Global hotkeys** — key combos that work anywhere in Windows, even minimized
- 🟢 **System tray** — closing the window hides it to the tray; the app keeps running
- 💡 **Default state** — apply a saved state automatically when the bulb is powered back on
- 🔦 **Multi-bulb** — control several bulbs with a selector; add/edit/remove them in-app
- 🌙 Modern dark UI, smooth-transition (fade) toggle, remembers its window position

Everything runs **locally over the LAN** — the only cloud step is a one-time
extraction of each bulb's *local key*.

---

## Requirements

- Windows (the tray, global hotkeys and `.exe` build are Windows-specific; the core
  control works cross-platform)
- Python 3.10+ (only needed to run from source or build the `.exe`)
- A Tuya / Smart Life Wi-Fi bulb on the **same 2.4 GHz network** as your PC

---

## Setup

### 1. Install the dependencies

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Get your bulb's local key

Tuya bulbs are controlled locally with a per-device **local key**. To obtain it:

1. Create a free Cloud project at **https://developer.tuya.com** (Cloud → Development).
2. Link your **Smart Life / Tuya Smart** app account: in the project, go to
   **Devices → Link App Account** and scan the QR code with the app
   (the data center / region must match your account).
3. Copy the project's **Access ID** and **Access Secret**.
4. Run the helper (you type the credentials locally — nothing is uploaded or stored):

```bash
.venv\Scripts\python.exe get_local_key.py
```

It writes a **`devices.json`** with each bulb's `id`, `ip`, `key` and `version`.

> Note: OEM-branded apps (like Intelbras Izy Smart) usually can't be linked to the
> Tuya developer console. If so, re-pair the bulb in the official **Smart Life** app
> and link that account instead.

Alternatively, copy `devices.json.example` to `devices.json` and fill it in by hand,
or use the in-app **⚙ Bulbs → Scan network** button to discover IP/version
(you still need the local key from the step above).

### 3. Run

```bash
.venv\Scripts\pythonw.exe bulb_controller.py
```

(or `python bulb_controller.py` to keep a console for debugging).

---

## Build a standalone `.exe`

```bash
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --onefile ^
  --name "Tuya Bulb Controller" --icon icon.ico ^
  --add-data "icon.png;." --add-data "icon.ico;." bulb_controller.py
```

The result is in `dist/`. Put a `devices.json` next to the `.exe`.
Run with `--tray` to start minimized in the system tray (handy for Windows startup).

> Rebuild tip: close the running `.exe` first (otherwise the file is locked).
> The `build/` folder is just intermediate output — safe to delete.

---

## Configuration files (created at runtime, not committed)

- **`devices.json`** — your bulbs (`id`, `ip`, `key`, `version`). Contains the local
  key, so it's **gitignored**. Each user/device has its own.
- **`preferences.json`** — favorites, default state, day/night, shortcuts, window position.

---

## Notes

- The bulb keeps working in the Smart Life app at the same time as this app — they
  stay in sync.
- The **local key changes** whenever you re-pair the bulb in an app — re-run
  `get_local_key.py` if that happens.
- Ambient mode samples the screen at ~3 fps (downscaled) — very light on the CPU.

---

## License

MIT — see [LICENSE](LICENSE). Made by **Faderaulas**.
