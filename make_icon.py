"""Generate icon.ico (256px) from icon.png using only Tkinter (no Pillow).
A 512px source is downscaled by an exact subsample (/2). The resulting PNG is
embedded into an .ico (the ICO format accepts a PNG payload on Windows Vista+)."""
import os
import struct
import tkinter as tk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PNG = os.path.join(BASE_DIR, "icon.png")
ICO = os.path.join(BASE_DIR, "icon.ico")

root = tk.Tk()
root.withdraw()
img = tk.PhotoImage(file=PNG)
factor = max(1, img.width() // 256)
small = img.subsample(factor) if factor > 1 else img

tmp = os.path.join(BASE_DIR, "_icon_tmp.png")
small.write(tmp, format="png")
with open(tmp, "rb") as f:
    png = f.read()
os.remove(tmp)

w, h = small.width(), small.height()
wb = 0 if w >= 256 else w   # 256 is represented as 0 in the ICO format
hb = 0 if h >= 256 else h

ico = struct.pack("<HHH", 0, 1, 1)                                  # ICONDIR
ico += struct.pack("<BBBBHHII", wb, hb, 0, 0, 1, 32, len(png), 22)  # ICONDIRENTRY
ico += png
with open(ICO, "wb") as f:
    f.write(ico)

print(f"icon.ico generated: {w}x{h}, {len(png)} bytes of PNG")
root.destroy()
