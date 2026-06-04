"""Gera icon.ico (256px) a partir de icon.png usando so o Tkinter (sem Pillow).
512px e reduzido por subsample exato (/2). O PNG resultante e embutido num .ico
(formato ICO aceita payload PNG no Windows Vista+)."""
import os
import struct
import tkinter as tk

PASTA = os.path.dirname(os.path.abspath(__file__))
PNG = os.path.join(PASTA, "icon.png")
ICO = os.path.join(PASTA, "icon.ico")

root = tk.Tk()
root.withdraw()
img = tk.PhotoImage(file=PNG)
fator = max(1, img.width() // 256)
peq = img.subsample(fator) if fator > 1 else img

tmp = os.path.join(PASTA, "_icon_tmp.png")
peq.write(tmp, format="png")
with open(tmp, "rb") as f:
    png = f.read()
os.remove(tmp)

w, h = peq.width(), peq.height()
wb = 0 if w >= 256 else w   # 256 e representado como 0 no formato ICO
hb = 0 if h >= 256 else h

ico = struct.pack("<HHH", 0, 1, 1)                                  # ICONDIR
ico += struct.pack("<BBBBHHII", wb, hb, 0, 0, 1, 32, len(png), 22)  # ICONDIRENTRY
ico += png
with open(ICO, "wb") as f:
    f.write(ico)

print(f"icon.ico gerado: {w}x{h}, {len(png)} bytes de PNG")
root.destroy()
