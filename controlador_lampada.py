"""
Controlador grafico da lampada Intelbras EWS 410 (Tuya) pela rede local.

Le a configuracao de 'dispositivos.json' (id, ip, key, version) e fala com a
lampada 100% via LAN com tinytuya - sem nuvem, sem app, sem internet.

Rodar (ou usar o atalho da area de trabalho / "Abrir Controlador.bat"):
    .venv/Scripts/pythonw.exe controlador_lampada.py   (sem janela de console)
    .venv/Scripts/python.exe  controlador_lampada.py   (com console, util p/ debug)
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
from i18n import T, definir_idioma

try:                       # bandeja + captura de tela (opcional; vem embutido no .exe)
    import pystray
    from PIL import Image, ImageGrab
    TRAY_OK = True
except Exception:
    TRAY_OK = False

try:                       # ImageTk (anel de cores) — separado: se faltar so ele,
    from PIL import ImageTk  # ainda mantemos tray/ambiente e caimos no picker
    ANEL_OK = TRAY_OK
except Exception:
    ANEL_OK = False

if getattr(sys, "frozen", False):
    PASTA = os.path.dirname(sys.executable)        # .exe: config/prefs ficam ao lado
    RES = getattr(sys, "_MEIPASS", PASTA)          # recursos embutidos (icones)
else:
    PASTA = os.path.dirname(os.path.abspath(__file__))
    RES = PASTA
CONFIG = os.path.join(PASTA, "dispositivos.json")
PREFS = os.path.join(PASTA, "preferencias.json")
ICONE = os.path.join(RES, "icon.png")

# Data points (DPS) da EWS 410 - mapeamento Tuya padrao p/ lampada tipo B
DP_POWER = "20"
DP_MODE = "21"        # white | colour | scene | music
DP_BRIGHT = "22"      # 10..1000
DP_TEMP = "23"        # 0..1000 (0 = quente, 1000 = frio)
DP_COLOUR = "24"      # HSV hex: HHHH SSSS VVVV

BRILHO_MIN = 10
BRILHO_MAX = 1000

# Cores de presets (chave i18n -> RGB). A chave e' um ID estavel; o rotulo
# exibido vem de T(chave).
PRESETS = [
    ("cor_vermelho", (255, 0, 0)),
    ("cor_laranja", (255, 120, 0)),
    ("cor_amarelo", (255, 220, 0)),
    ("cor_verde", (0, 255, 0)),
    ("cor_ciano", (0, 255, 255)),
    ("cor_azul", (0, 80, 255)),
    ("cor_roxo", (150, 0, 255)),
    ("cor_rosa", (255, 0, 150)),
]

# Paleta do tema escuro moderno
BG = "#15161c"          # fundo da janela
CARD = "#1e2029"        # fundo dos cartoes
CARD2 = "#2c303d"       # realce sutil
SLIDER_TRACK = "#3b4156"  # trilha do slider (contraste com o cartao)
BTN = "#2b2e3b"         # botao base
BTN_HOVER = "#373b4c"   # hover
BTN_ACTIVE = "#434a60"  # pressionado
FG = "#e9eaf0"          # texto principal
MUTED = "#969cab"       # texto secundario
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
AMBER = "#d9a05b"       # aviso discreto (lampada offline)


def _gravar_json_atomico(caminho, dados):
    """Grava JSON de forma ATOMICA: escreve num arquivo temporario ao lado e troca
    pelo definitivo com os.replace (operacao atomica no Windows). Assim, se o
    processo morrer no meio da escrita (ex.: taskkill /F, queda de energia), o
    arquivo original continua intacto em vez de ficar truncado/corrompido."""
    tmp = f"{caminho}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, caminho)


def _preservar_corrompido(caminho):
    """Renomeia um arquivo de config com JSON invalido para *.corrompido, para nao
    perder os dados (ex.: a local key) caso a proxima gravacao o sobrescreva."""
    try:
        if os.path.exists(caminho) and os.path.getsize(caminho) > 0:
            os.replace(caminho, f"{caminho}.corrompido")
    except Exception:
        pass


def carregar_lampadas():
    """Le dispositivos.json -> lista de lampadas validas (pode ser vazia)."""
    try:
        with open(CONFIG, encoding="utf-8") as f:
            devs = json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        _preservar_corrompido(CONFIG)   # nao apaga: guarda copia recuperavel
        return []
    except Exception:
        return []                       # erro transitorio (arquivo travado etc.)
    if isinstance(devs, dict):
        devs = [devs]
    return [d for d in devs if d.get("id") and d.get("ip") and d.get("key")]


def salvar_lampadas(lampadas):
    """Salva a lista em dispositivos.json (e espelha no dist/ quando rodando do codigo)."""
    _gravar_json_atomico(CONFIG, lampadas)
    if not getattr(sys, "frozen", False):
        dist_cfg = os.path.join(PASTA, "dist", "dispositivos.json")
        if os.path.isdir(os.path.dirname(dist_cfg)):
            try:
                _gravar_json_atomico(dist_cfg, lampadas)
            except Exception:
                pass


SAT_MIN = 0.30   # saturacao minima p/ a cor realmente aparecer na lampada


def _passos(ini, fim, n=6):
    """Lista de n valores indo de 'ini' (exclusivo) ate 'fim' (inclusivo)."""
    return [round(ini + (fim - ini) * (k + 1) / n) for k in range(n)]


def cor_exibivel(rgb):
    """Ajusta a cor para a mais proxima que a lampada consegue exibir.
    Retorna (eh_branco, rgb_ajustado): cores quase sem saturacao viram 'branco'
    (a lampada nao mostra pastel/branco no modo cor); as demais tem a saturacao
    reforcada p/ aparecer com a cor certa."""
    r, g, b = (c / 255.0 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.12:
        return True, rgb
    r2, g2, b2 = colorsys.hsv_to_rgb(h, max(s, SAT_MIN), max(v, 0.15))
    return False, (int(r2 * 255), int(g2 * 255), int(b2 * 255))


def parse_hsv_componentes(s):
    """Hex de cor da Tuya (HHHHSSSSVVVV) -> (h, s, v) em 0..1."""
    try:
        h = int(s[0:4], 16) / 360.0     # 0..360
        sat = int(s[4:8], 16) / 1000.0  # 0..1000
        val = int(s[8:12], 16) / 1000.0  # 0..1000
        return h % 1.0, max(0.0, min(1.0, sat)), max(0.0, min(1.0, val))
    except Exception:
        return (0.0, 1.0, 1.0)


def parse_hsv_hex(s):
    """Converte o hex de cor da Tuya (HHHHSSSSVVVV) em RGB 0-255."""
    h, sat, val = parse_hsv_componentes(s)
    r, g, b = colorsys.hsv_to_rgb(h, sat, val)
    return int(r * 255), int(g * 255), int(b * 255)


def brilho_para_pct(raw):
    """Brilho cru da Tuya -> %. Usa a MESMA escala que o tinytuya usa para ESCREVER
    (set_brightness_percentage faz value_max*pct//100, sem offset). Ler com a formula
    antiga (raw-10)/990 fazia 45% voltar como 44% a cada round-trip."""
    try:
        return max(1, min(100, round(int(raw) / BRILHO_MAX * 100)))
    except Exception:
        return 1


# ---------- Cenas em movimento (geradores: rendem o atraso ate o proximo quadro) ----------
# Todas as cenas em movimento recebem a mesma assinatura (b, fase0=0.0, escala_v=1.0):
# 'fase0' defasa cada lampada quando rodam em grupo (cada uma mostra um tom diferente);
# 'escala_v' deixa a lampada mais fraca (ex.: teto, que ofusca). Sozinha: fase0=0, escala=1.
def cena_arcoiris(b, fase0=0.0, escala_v=1.0):
    """Cicla suavemente por todo o espectro de cores."""
    h = (fase0 * 0.13) % 1.0    # em grupo, cada lampada comeca num ponto diferente do espectro
    while True:
        b.set_hsv(h, 1.0, max(0.05, 1.0 * escala_v), nowait=True)
        h = (h + 0.03) % 1.0
        yield 0.30


def cena_vela(b, fase0=0.0, escala_v=1.0):
    """Bruxuleio quente imitando a chama de uma vela."""
    while True:
        h = random.uniform(25, 42) / 360.0   # laranja/amarelo
        v = random.uniform(0.45, 0.9)
        b.set_hsv(h, 0.85, max(0.05, v * escala_v), nowait=True)
        yield random.uniform(0.07, 0.16)


def cena_respirar(b, fase0=0.0, escala_v=1.0):
    """Brilho subindo e descendo devagar, em branco quente."""
    fase = fase0
    while True:
        v = 0.12 + 0.85 * (1 + math.sin(fase)) / 2
        b.set_hsv(38 / 360.0, 0.35, max(0.05, v * escala_v), nowait=True)
        fase += 0.22
        yield 0.08


# ---------- Cenas de clima (vivem melhor em grupo, mas servem tambem p/ uma so) ----------
# Recebem 'fase0' p/ defasar cada lampada: assim varias mostram tons diferentes
# ao mesmo tempo (e nao todas iguais), o que e o charme de usar varias juntas.
def cena_sensual(b, fase0=0.0, escala_v=1.0):
    """Flutua entre roxo, rosa, magenta e vermelho, com o brilho 'respirando'.
    Clima quente/intimista. 'escala_v' deixa a lampada mais fraca (ex.: teto)."""
    t = fase0
    while True:
        h = (330 + 45 * math.sin(t * 0.30)) % 360       # ~285..15: roxo->magenta->vermelho
        v = 0.30 + 0.55 * (1 + math.sin(t * 0.50)) / 2   # respiracao lenta do brilho
        b.set_hsv(h / 360.0, 0.95, max(0.05, v * escala_v), nowait=True)
        t += 0.13
        yield 0.10


def cena_aurora(b, fase0=0.0, escala_v=1.0):
    """Flutuacao fria e onirica: ciano, azul, violeta e magenta."""
    t = fase0
    while True:
        h = (260 + 65 * math.sin(t * 0.24)) % 360        # ~195..325
        v = 0.45 + 0.35 * (1 + math.sin(t * 0.38)) / 2
        b.set_hsv(h / 360.0, 0.85, max(0.05, v * escala_v), nowait=True)
        t += 0.11
        yield 0.11


def cena_festa(b, fase0=0.0, escala_v=1.0):
    """Cores vividas trocando rapido. Com a defasagem, cada lampada fica numa
    cor diferente ao mesmo tempo (sempre espalhadas pelo circulo de cores)."""
    h = (fase0 * 57.3) % 360       # cada lampada comeca num ponto diferente do circulo
    while True:
        b.set_hsv((h % 360) / 360.0, 1.0, max(0.05, 1.0 * escala_v), nowait=True)
        h += 14
        yield 0.28


# Cenas fixas (branco): (id_i18n, temp%, brilho%). O id e' identificador estavel;
# o rotulo exibido vem de T(id).
CENAS_FIXAS = [
    ("cena_leitura", 100, 100),
    ("cena_aconchego", 0, 45),
    ("cena_cinema", 0, 8),
]
# Cenas em movimento: (id_i18n, fabrica(bulb, fase0=0.0, escala_v=1.0) -> gerador).
# A mesma lista serve para UMA lampada (fase0=0, escala=1) e para o grupo inteiro
# (cada lampada recebe uma 'fase0' diferente, ficando defasada das outras).
CENAS_MOV = [
    ("cena_vela", cena_vela),
    ("cena_arcoiris", cena_arcoiris),
    ("cena_respirar", cena_respirar),
    ("cena_sensual", cena_sensual),
    ("cena_aurora", cena_aurora),
    ("cena_festa", cena_festa),
]

# Fator de brilho por lampada nas cenas de grupo (1.0 = normal). A lampada cujo
# nome contem a chave fica mais fraca -- a de teto ofusca demais no clima sensual.
# Facil de ajustar depois (ou virar config na interface).
ESCALA_BRILHO_GRUPO = {"teto": 0.25}


def escala_brilho_cfg(cfg):
    """Fator de brilho (0..1) de uma lampada nas cenas de grupo, escolhido pelo nome."""
    nome = (cfg.get("name") or "").lower()
    for chave, fator in ESCALA_BRILHO_GRUPO.items():
        if chave in nome:
            return fator
    return 1.0


def temp_para_rgb(temp_pct, brilho_pct=100):
    """Aproxima a cor do branco ajustavel para o quadrado de display:
    0% = quente (alaranjado), 100% = frio (branco azulado). Escurece com o brilho."""
    t = max(0, min(100, temp_pct)) / 100.0
    quente = (255, 140, 42)
    frio = (215, 230, 255)
    r = quente[0] + (frio[0] - quente[0]) * t
    g = quente[1] + (frio[1] - quente[1]) * t
    bl = quente[2] + (frio[2] - quente[2]) * t
    f = 0.25 + 0.75 * (max(1, min(100, brilho_pct)) / 100.0)
    return (int(r * f), int(g * f), int(bl * f))


def carregar_prefs():
    try:
        with open(PREFS, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        _preservar_corrompido(PREFS)   # nao apaga prefs corrompidas: guarda copia
        return {}
    except Exception:
        return {}


def salvar_prefs(p):
    # try/except: uma falha de I/O ao salvar prefs nao deve derrubar a acao da UI
    try:
        _gravar_json_atomico(PREFS, p)
    except Exception:
        pass


def construir_func_estado(estado):
    """Constroi uma func(bulb) que aplica um estado salvo (modo/brilho/temp/cor)."""
    modo = estado.get("modo", "white")
    brilho = int(estado.get("brilho", 100))
    if modo == "colour":
        cor = estado.get("cor", [255, 255, 255])
        # passa pelo mesmo ajuste do botao de cor: pastel/quase-branco vira branco
        # (a lampada nao exibe cor dessaturada), as demais ganham saturacao.
        eh_branco, ajust = cor_exibivel(tuple(cor))
        if eh_branco:
            def aplicar(b):
                b.set_mode("white")
                b.set_brightness_percentage(brilho)
            return aplicar

        def aplicar(b):
            r, g, bl = (c / 255.0 for c in ajust)
            h, s, _ = colorsys.rgb_to_hsv(r, g, bl)
            b.set_hsv(h, s, max(0.05, brilho / 100.0))
        return aplicar

    temp = int(estado.get("temp", 50))

    def aplicar(b):
        b.set_colourtemp_percentage(temp)
        b.set_brightness_percentage(brilho)
    return aplicar


class Controlador:
    """Acesso serializado a lampada via uma unica thread de trabalho."""

    # serializa a redescoberta de IP entre as varias lampadas: o find_device faz
    # broadcast UDP e da bind nas portas Tuya -- duas buscas ao mesmo tempo colidem.
    _scan_lock = threading.Lock()

    def __init__(self, cfg):
        self.cfg = cfg
        self.fila = queue.Queue()
        self.bulb = None
        self.on_status = None      # callback(cid, dps_dict)
        self.on_conexao = None     # callback(ok: bool, msg: str)
        self.on_online = None      # callback(cid, online: bool)
        self.on_ip = None          # callback(cid, novo_ip) -- IP mudou no DHCP
        self._ultimo_scan = 0.0    # cooldown da redescoberta de IP (monotonic)
        self._anim = None          # gerador de animacao ativo (ou None)
        self._anim_delay = 0.1     # atraso ate o proximo quadro
        self.fade = False          # transicao suave on/off
        self._lb = None            # ultimo brilho (%) aplicado/lido
        self._lt = None            # ultima temperatura (%)
        self._lc = None            # ultima cor (rgb)
        self._snapshot = None      # estado salvo antes de uma cena (p/ restaurar ao parar)
        threading.Thread(target=self._worker, daemon=True).start()

    def _conectar(self):
        ver = float(self.cfg.get("version") or 3.3)
        b = tinytuya.BulbDevice(self.cfg["id"], self.cfg["ip"], self.cfg["key"], version=ver)
        b.set_socketPersistent(True)
        b.set_socketTimeout(5)
        b.set_socketRetryLimit(1)
        self.bulb = b

    def _forcar_reconexao(self):
        """Fecha o socket atual e descarta o objeto bulb, forcando uma conexao TCP
        nova no proximo comando. NECESSARIO quando a lampada cai: como o socket e
        persistente, o tinytuya pode ficar preso num socket morto e continuar
        retornando erro mesmo DEPOIS que a lampada religa -- era o bug do 'fica
        offline pra sempre'. Recriar do zero garante que, quando a lampada volta,
        o proximo poll abre uma conexao limpa e detecta o online de verdade."""
        b = self.bulb
        self.bulb = None
        if b is None:
            return
        try:
            s = getattr(b, "socket", None)
            if s is not None:
                s.close()
        except Exception:
            pass
        try:
            b.socket = None
        except Exception:
            pass

    def _redescobrir_ip(self):
        """A lampada sumiu? O IP pode ter mudado: quando ela fica um tempo desligada,
        o lease de DHCP do roteador expira e ela costuma pegar OUTRO endereco ao
        religar -- mas o dispositivos.json guarda o IP antigo, entao o app fala no
        vazio e marca 'offline' pra sempre (reabrir nao adianta). Aqui fazemos um
        broadcast na LAN procurando o ID desta lampada e, se ela aparecer noutro IP,
        atualizamos e reconectamos. E a correcao 'de uma vez por todas'.

        Roda na worker (pode bloquear ~6s) com cooldown p/ nao escanear a cada poll."""
        agora = time.monotonic()
        if agora - self._ultimo_scan < 15:
            return
        self._ultimo_scan = agora
        cid = self.cfg.get("id")
        if not cid:
            return
        try:
            with Controlador._scan_lock:
                info = tinytuya.find_device(dev_id=cid)
        except Exception:
            return
        novo_ip = (info or {}).get("ip")
        if novo_ip and novo_ip != self.cfg.get("ip"):
            self.cfg["ip"] = novo_ip      # cfg e o MESMO dict de App.lampadas
            self._forcar_reconexao()      # proximo comando conecta no IP novo
            if self.on_ip:
                try:
                    self.on_ip(cid, novo_ip)   # UI persiste no dispositivos.json
                except Exception:
                    pass

    def _drenar(self):
        """Descarta respostas antigas no buffer do socket (ecos de comandos enviados
        com nowait pelo fade/animacoes), pra a proxima leitura pegar o estado atual."""
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

    def _notify_status(self, dps):
        # inclui o id de QUEM emitiu: a UI usa isso p/ nao pintar o estado de uma
        # lampada nos controles de outra durante uma troca de aba (corrida do after).
        if self.on_status:
            self.on_status(self.cfg.get("id"), dps)

    def _notify_online(self, online):
        if self.on_online:
            self.on_online(self.cfg.get("id"), online)

    def _worker(self):
        try:
            self._conectar()
            if self.on_conexao:
                self.on_conexao(True, T("status_conectado", ip=self.cfg['ip']))
        except Exception as e:
            if self.on_conexao:
                self.on_conexao(False, f"falha ao conectar: {e}")
            self._notify_online(False)
        while True:
            timeout = self._anim_delay if self._anim is not None else None
            try:
                acao, args = self.fila.get(timeout=timeout)
            except queue.Empty:
                # nenhum comando pendente: avanca um quadro da animacao
                try:
                    self._anim_delay = next(self._anim)
                except Exception:
                    self._anim = None
                continue

            if acao == "_sair":
                break

            if acao == "anim":
                self._anim = None
                if args is None:
                    # parar a cena sem restaurar (vai aplicar outra coisa em seguida,
                    # ou estamos so saindo): descarta o estado salvo
                    self._snapshot = None
                elif args == "restaurar":
                    # parar a cena e voltar ao estado de antes dela
                    if self._snapshot is not None:
                        try:
                            self._restaurar_estado(self._snapshot)
                        except Exception as e:
                            if self.on_conexao:
                                self.on_conexao(False, f"erro: {e}")
                        self._snapshot = None
                else:
                    # iniciar cena (args = fabrica(bulb) -> gerador). Antes de comecar,
                    # guarda o estado atual (so na 1a cena: trocar de cena preserva o
                    # snapshot original) para poder voltar a ele depois.
                    try:
                        if self.bulb is None:
                            self._conectar()
                        if self._snapshot is None:
                            self._snapshot = self._capturar_estado()
                        self.bulb.turn_on()
                        self._anim = args(self.bulb)
                        self._anim_delay = 0.05
                    except Exception as e:
                        if self.on_conexao:
                            self.on_conexao(False, f"erro: {e}")
                continue

            # qualquer comando manual (menos a leitura de status) interrompe a cena.
            # O usuario assumiu o controle: descarta o estado salvo da cena.
            if acao != "status":
                self._anim = None
                self._snapshot = None
            try:
                self._executar(acao, args)
            except Exception as e:
                if self.on_conexao:
                    self.on_conexao(False, f"erro: {e}")
                self._notify_online(False)
                # descarta o socket morto; o proximo comando reconecta do zero
                self._forcar_reconexao()
                self._redescobrir_ip()   # ou o IP mudou no DHCP -- procura na LAN

    def _executar(self, acao, args):
        b = self.bulb
        if b is None:
            self._conectar()
            b = self.bulb
        if acao == "status":
            self._drenar()
            resp = b.status()
            dps = resp.get("dps") if isinstance(resp, dict) else None
            if dps:
                self._sincronizar_ultimos(dps)
                self._notify_status(dps)
                self._notify_online(True)
            else:
                # respondeu sem dados / com erro -> tratamos como indisponivel.
                # forca reconexao: senao o socket persistente fica preso num estado
                # morto e nunca volta, mesmo depois que a lampada religa.
                self._notify_online(False)
                self._forcar_reconexao()
                self._redescobrir_ip()   # ou o IP mudou no DHCP -- procura na LAN
        elif acao == "power":
            b.turn_on() if args else b.turn_off()
        elif acao == "brilho":
            self._aplicar_num(b.set_brightness_percentage, self._lb, args, "_lb")
        elif acao == "brilho_direto":
            v = max(1, min(100, int(args)))
            b.set_brightness_percentage(v)
            self._lb = v
        elif acao == "temp":
            self._aplicar_num(b.set_colourtemp_percentage, self._lt, args, "_lt")
        elif acao == "branco":
            b.set_mode("white")
        elif acao == "cor":
            self._aplicar_cor_fade(b, args)
        elif acao == "cor_direto":
            r, g, bl = (int(c) for c in args)
            b.set_colour(r, g, bl)
            self._lc = (r, g, bl)
        elif acao == "hsv":
            # aplica H/S/V direto (anel + sliders de cor): respeita a saturacao
            # escolhida, sem o ajuste cor_exibivel (que e so p/ presets em RGB).
            h, s, v = args
            b.set_hsv(h, s, max(0.05, v))
            r, g, bl = colorsys.hsv_to_rgb(h, s, v)
            self._lc = (int(r * 255), int(g * 255), int(bl * 255))
        elif acao == "func":
            args(b)

    def _sincronizar_ultimos(self, dps):
        try:
            if DP_BRIGHT in dps:
                self._lb = brilho_para_pct(dps[DP_BRIGHT])
            if DP_TEMP in dps:
                self._lt = round(int(dps[DP_TEMP]) / 1000 * 100)
            if DP_COLOUR in dps and dps[DP_COLOUR]:
                self._lc = parse_hsv_hex(dps[DP_COLOUR])
        except Exception:
            pass

    def _aplicar_num(self, fn, atual, alvo, attr):
        alvo = max(1, min(100, int(alvo)))
        if self.fade and atual is not None and atual != alvo:
            passos = _passos(atual, alvo)
            for i, v in enumerate(passos):
                ultimo = (i == len(passos) - 1)
                fn(max(1, min(100, v)), nowait=not ultimo)
                if not ultimo:
                    time.sleep(0.05)
        else:
            fn(alvo)
        setattr(self, attr, alvo)

    def _aplicar_cor_fade(self, b, rgb):
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

    def _capturar_estado(self):
        """Le o estado real da lampada (na worker) e devolve um snapshot dele,
        usado para restaurar depois que uma cena para. None se nao conseguir ler."""
        try:
            self._drenar()
            resp = self.bulb.status()
            dps = resp.get("dps") if isinstance(resp, dict) else None
            if not dps:
                return None
            return {
                "power": bool(dps.get(DP_POWER, True)),
                "mode": dps.get(DP_MODE, "white"),
                "bright": dps.get(DP_BRIGHT),
                "temp": dps.get(DP_TEMP),
                "colour": dps.get(DP_COLOUR),
            }
        except Exception:
            return None

    def _restaurar_estado(self, snap):
        """Reaplica um snapshot capturado por _capturar_estado (roda na worker)."""
        if not snap:
            return
        if not snap.get("power"):
            self.bulb.turn_off()
            return
        self.bulb.turn_on()
        if snap.get("mode") == "colour" and snap.get("colour"):
            r, g, bl = parse_hsv_hex(snap["colour"])
            self.bulb.set_colour(r, g, bl)
            self._lc = (r, g, bl)
        else:
            self.bulb.set_mode("white")
            if snap.get("temp") is not None:
                t = round(int(snap["temp"]) / 1000 * 100)
                self.bulb.set_colourtemp_percentage(t)
                self._lt = t
            if snap.get("bright") is not None:
                pct = brilho_para_pct(snap["bright"])
                self.bulb.set_brightness_percentage(pct)
                self._lb = pct

    # --- API publica (enfileira) ---
    def pedir_status(self):
        self.fila.put(("status", None))

    def iniciar_cena(self, gerador):
        self.fila.put(("anim", gerador))

    def parar_cena(self, restaurar=True):
        # restaurar=True: volta ao estado de antes da cena. False: so para.
        self.fila.put(("anim", "restaurar" if restaurar else None))

    def aplicar_func(self, func):
        self.fila.put(("anim", None))
        self.fila.put(("func", func))

    def power(self, ligado):
        self.fila.put(("power", ligado))

    def brilho(self, pct):
        self.fila.put(("brilho", pct))

    def brilho_direto(self, pct):
        self.fila.put(("brilho_direto", pct))

    def temperatura(self, pct):
        self.fila.put(("temp", pct))

    def modo_branco(self):
        self.fila.put(("branco", None))

    def cor(self, rgb):
        self.fila.put(("cor", rgb))

    def cor_direto(self, rgb):
        self.fila.put(("cor_direto", rgb))

    def cor_hsv(self, h, s, v):
        self.fila.put(("hsv", (h, s, v)))

    def encerrar(self):
        self.fila.put(("_sair", None))


# =================== widgets customizados (visual moderno) ===================
def _pontos_arred(x1, y1, x2, y2, r):
    """Pontos de um retangulo de cantos arredondados (usar com smooth=True)."""
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


class RoundedButton(tk.Canvas):
    """Botao de cantos arredondados com feedback de hover e clique."""

    def __init__(self, parent, text="", command=None, width=120, height=38,
                 radius=11, fill=BTN, hover=BTN_HOVER, active=BTN_ACTIVE,
                 fg=FG, font=("Segoe UI", 10)):
        super().__init__(parent, width=width, height=height, bg=parent["bg"],
                         highlightthickness=0, bd=0)
        self.command = command
        self._fill, self._hover, self._active = fill, hover, active
        self._bw, self._bh = width, height
        self._shape = self.create_polygon(
            *_pontos_arred(1, 1, width - 1, height - 1, radius),
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
        dentro = 0 <= e.x <= self._bw and 0 <= e.y <= self._bh
        self._set(self._hover if dentro else self._fill)
        if dentro and self.command:
            self.command()

    def set_text(self, t):
        self.itemconfig(self._txt, text=t)

    def set_colors(self, fill, hover, active):
        self._fill, self._hover, self._active = fill, hover, active
        self._set(fill)


class ColorDot(tk.Canvas):
    """Bolinha de cor arredondada com contorno no hover."""

    def __init__(self, parent, rgb, command, size=30, radius=9):
        super().__init__(parent, width=size, height=size, bg=parent["bg"],
                         highlightthickness=0, bd=0)
        self.command = command
        self._shape = self.create_polygon(
            *_pontos_arred(2, 2, size - 2, size - 2, radius),
            smooth=True, splinesteps=24, fill="#%02x%02x%02x" % rgb,
            outline="", width=0)
        self.configure(cursor="hand2")
        self.bind("<Enter>", lambda e: self.itemconfig(self._shape, outline=FG, width=2))
        self.bind("<Leave>", lambda e: self.itemconfig(self._shape, outline="", width=0))
        self.bind("<ButtonRelease-1>", lambda e: self.command() if self.command else None)


class Swatch(tk.Canvas):
    """Quadrado arredondado que mostra a cor/branco atual."""

    def __init__(self, parent, w=66, h=42, radius=12):
        super().__init__(parent, width=w, height=h, bg=parent["bg"],
                         highlightthickness=0, bd=0)
        self._shape = self.create_polygon(
            *_pontos_arred(1, 1, w - 1, h - 1, radius),
            smooth=True, splinesteps=28, fill="#ffffff")

    def set(self, rgb):
        self.itemconfig(self._shape, fill="#%02x%02x%02x" % rgb)


class AnelMatiz(tk.Canvas):
    """Anel de matiz (hue) desenhado com PIL: clicar/arrastar escolhe a cor.
    Mostra so o matiz com saturacao/brilho plenos -- as cores que a lampada de fato
    exibe (sem pastel/branco). Saturacao e brilho vem dos sliders. Chama
    command(h) com h em 0..1. Requer PIL (ImageTk); sem ele, nao deve ser criado."""

    def __init__(self, parent, command=None, size=188, espessura=26):
        super().__init__(parent, width=size, height=size, bg=parent["bg"],
                         highlightthickness=0, bd=0)
        self.command = command
        self._size = size
        self._re = size / 2.0 - 2          # raio externo
        self._ri = self._re - espessura    # raio interno
        self._h = 0.0
        self._tkimg = ImageTk.PhotoImage(self._gerar_imagem())
        self.create_image(size // 2, size // 2, image=self._tkimg)
        # circulo central que mostra a cor atual + marcador do matiz no anel
        rc = self._ri - 7
        cx = size / 2.0
        self._centro = self.create_oval(cx - rc, cx - rc, cx + rc, cx + rc,
                                        fill="#ffffff", outline=CARD2, width=2)
        self._marc = self.create_oval(0, 0, 0, 0, fill="#ffffff",
                                      outline="#202028", width=2)
        self.configure(cursor="hand2")
        self.bind("<ButtonPress-1>", self._mexer)
        self.bind("<B1-Motion>", self._mexer)
        self._pos_marcador()

    def _gerar_imagem(self):
        size = self._size
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        px = img.load()
        c = size / 2.0
        re2, ri2 = self._re ** 2, self._ri ** 2
        for y in range(size):
            for x in range(size):
                dx, dy = x - c, y - c
                d2 = dx * dx + dy * dy
                if ri2 <= d2 <= re2:
                    h = (math.atan2(dy, dx) / 6.2831853) % 1.0
                    r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
                    px[x, y] = (int(r * 255), int(g * 255), int(b * 255), 255)
        return img

    def set_hue(self, h):
        self._h = h % 1.0
        self._pos_marcador()

    def set_cor_central(self, rgb):
        self.itemconfig(self._centro, fill="#%02x%02x%02x" % rgb)

    def _pos_marcador(self):
        ang = self._h * 6.2831853
        rmed = (self._re + self._ri) / 2.0
        c = self._size / 2.0
        mx, my = c + rmed * math.cos(ang), c + rmed * math.sin(ang)
        r = (self._re - self._ri) / 2.0 - 1
        self.coords(self._marc, mx - r, my - r, mx + r, my + r)

    def _mexer(self, e):
        c = self._size / 2.0
        self._h = (math.atan2(e.y - c, e.x - c) / 6.2831853) % 1.0
        self._pos_marcador()
        if self.command:
            self.command(self._h)


class Slider(tk.Canvas):
    """Slider horizontal moderno: trilha arredondada com contraste, parte
    preenchida em destaque e thumb redondo. Sincroniza com uma IntVar."""

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
        self.bind("<ButtonPress-1>", self._mover)
        self.bind("<B1-Motion>", self._mover)
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

    def _mover(self, e):
        w = self.winfo_width() or self._wpx
        x = min(max(e.x, self._pad), w - self._pad)
        rng = (self.to - self.from_) or 1
        val = round(self.from_ + (x - self._pad) / max(1, (w - 2 * self._pad)) * rng)
        val = max(self.from_, min(self.to, val))
        if val != self.var.get():
            self.var.set(val)
        if self.command:
            self.command(val)


# ---------- atalhos globais (Windows, via RegisterHotKey) ----------
HOTKEYS_OK = sys.platform == "win32"
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
_WM_HOTKEY, _WM_QUIT = 0x0312, 0x0012

ACOES_ATALHO = [
    ("toggle_power", "atalho_toggle_power"),
    ("mostrar", "atalho_mostrar"),
    ("padrao", "atalho_padrao"),
    ("parar_cena", "atalho_parar_cena"),
]
TECLAS_ATALHO = ([chr(c) for c in range(ord("A"), ord("Z") + 1)] +
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
    """Registra atalhos globais no Windows (RegisterHotKey) numa thread propria."""

    def __init__(self, on_trigger):
        self.on_trigger = on_trigger
        self._thread = None
        self._tid = None
        self._atalhos = []

    def aplicar(self, atalhos):
        if not HOTKEYS_OK:
            return
        self.parar()
        self._atalhos = atalhos
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def parar(self):
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
        registrados = []
        for i, (acao, mods, vk) in enumerate(self._atalhos):
            try:
                if u.RegisterHotKey(None, i + 1, mods | MOD_NOREPEAT, vk):
                    registrados.append(i + 1)
            except Exception:
                pass
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == _WM_HOTKEY:
                idx = int(msg.wParam) - 1
                if 0 <= idx < len(self._atalhos):
                    self.on_trigger(self._atalhos[idx][0])
        for hid in registrados:
            try:
                u.UnregisterHotKey(None, hid)
            except Exception:
                pass


# =============================== aplicacao ===============================
class _CtrlVazio:
    """Controlador no-op usado quando nenhuma lampada esta configurada."""
    on_status = on_conexao = on_online = None

    def __getattr__(self, _):
        return lambda *a, **k: None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self._evt_mostrar = None
        self._iniciar_instancia_unica()   # cria o evento cedo (reduz a corrida no boot)
        self.lampadas = carregar_lampadas()
        self.controladores = [Controlador(c) for c in self.lampadas]
        for c in self.controladores:
            c.on_ip = self._ip_redescoberto   # salva o IP novo se o DHCP trocar
        self.idx = 0
        self.ctrl = self.controladores[0] if self.controladores else _CtrlVazio()
        self._online_lamp = {}       # id da lampada -> online? (None = ainda desconhecido)
        self._falhas_online = {}     # id -> leituras ruins seguidas (debounce do offline)

        self._debounce_brilho = None
        self._debounce_temp = None
        self._debounce_cor = None
        self._cor_h = 0.0            # matiz atual (0..1) escolhido no anel
        self._sincronizando = False  # evita disparar comandos ao refletir status
        self._mute_ate = 0.0         # ignora polls por alguns seg apos uma acao do usuario
        self.prefs = carregar_prefs()
        definir_idioma(self.prefs.get("idioma", "pt"))
        self._fade = bool(self.prefs.get("fade"))
        for c in self.controladores:
            c.fade = self._fade
        self._tray = None
        self._tray_ativo = False
        self._timer_id = None
        self._timer_restante = 0
        self._dn_periodo = None    # 'dia' / 'noite' atual (agendador)
        self._dn_base_b = None     # brilho base da noite (p/ a rampa)
        self._dn_ultimo_alvo = None  # ultimo brilho de rampa enviado (evita re-envio)
        self._ambiente_ativo = False  # modo ambiente (ambilight)
        self._ambiente_gen = 0        # token: invalida a thread de ambiente anterior
        self._grupo_cenas = False    # cenas agem em todas as lampadas (nao so a ativa)
        self.btn_grupo_cenas = None  # botao do modo grupo (so existe com +1 lampada)
        self._tab_btns = []          # abas de lampada (p/ reordenar arrastando)
        self._cenas_ativas = {}      # id da lampada -> nome da cena (p/ destacar a ativa)
        self._btns_cena = {}         # nome da cena -> botao (p/ destacar a ativa)
        self._fav_btns = []          # botoes de favorito (p/ reordenar arrastando)

        self.title(T("titulo_app"))
        self.configure(bg=BG)
        self.resizable(False, False)
        try:
            self._icone = tk.PhotoImage(file=ICONE)
            self.iconphoto(True, self._icone)
        except Exception:
            pass
        self._bind_display(self.ctrl)
        self._montar_ui()

        pos = self.prefs.get("janela_pos")
        if pos:
            try:
                self.geometry(pos)   # restaura a posicao da ultima vez
            except Exception:
                pass

        if self.lampadas:
            self.after(300, self.ctrl.pedir_status)
            # NAO aplica o padrao ao abrir o app (preserva o estado atual da luz);
            # o padrao so entra quando a lampada volta do offline (interruptor religado).
        else:
            self._status(T("status_nenhuma_lampada_abrindo"), AMBER)
            self.after(500, self._abrir_config)
        self.after(7000, self._poll_status)    # checa estado/disponibilidade periodicamente
        self.after(1500, self._dn_loop)        # agendador dia/noite
        self.hotkeys = HotkeyManager(self._hotkey_trigger)
        self.after(1200, self._aplicar_atalhos)
        self.after(400, self._iniciar_tray)    # icone na bandeja sempre presente
        self.protocol("WM_DELETE_WINDOW", self._fechar)

    # ---------- construcao da UI ----------
    def _card(self, parent, titulo=None):
        outer = tk.Frame(parent, bg=CARD)
        outer.pack(fill="x", padx=6, pady=(0, 7))
        inner = tk.Frame(outer, bg=CARD)
        inner.pack(fill="x", padx=12, pady=8)
        if titulo:
            tk.Label(inner, text=titulo, bg=CARD, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 3))
        return outer, inner

    # ---------- multi-lampada ----------
    def _nome_ativo(self):
        if self.lampadas and 0 <= self.idx < len(self.lampadas):
            return self.lampadas[self.idx].get("name", T("lampada_padrao"))
        return T("sem_lampada")

    def _id_ativo(self):
        """ID da lampada selecionada (ou None). Usado p/ rastrear estado por lampada."""
        if self.lampadas and 0 <= self.idx < len(self.lampadas):
            return self.lampadas[self.idx].get("id")
        return None

    def _bind_display(self, ctrl):
        """Direciona os callbacks de status/conexao para o controlador exibido."""
        for c in self.controladores:
            c.on_status = c.on_conexao = c.on_online = None
        ctrl.on_status = self._status_recebido
        ctrl.on_conexao = self._conexao_mudou
        ctrl.on_online = self._online_mudou

    def _montar_seletor(self):
        for w in self.sel_frame.winfo_children():
            w.destroy()
        self._tab_btns = []
        if len(self.lampadas) > 1:
            tabs = tk.Frame(self.sel_frame, bg=CARD)
            tabs.pack(side="left")
            for i, lmp in enumerate(self.lampadas):
                # sem 'command': o clique/arrasto e tratado por _tornar_aba
                # (clique = selecionar; arrastar de lado = reordenar as lampadas)
                offline = self._online_lamp.get(lmp.get("id")) is False
                rotulo = lmp.get("name", T("lampada_numerada", n=i + 1))
                if offline:
                    rotulo = "⚠ " + rotulo   # marca a lampada que caiu da rede
                b = RoundedButton(tabs, text=rotulo,
                                  width=96, height=26, radius=9)
                b.pack(side="left", padx=(0, 4))
                self._tab_btns.append(b)
                self._tornar_aba(b, i)
                if i == self.idx:
                    b.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
                elif offline:
                    b.set_colors(OFF, OFF_HOVER, OFF_ACTIVE)
        RoundedButton(self.sel_frame, text=T("btn_lampadas_engrenagem"), width=108, height=26, radius=9,
                      command=self._abrir_config).pack(side="right")

    def _tornar_aba(self, btn, i):
        """Faz a aba da lampada responder a clique (selecionar) e a arrasto lateral
        (reordenar). O arrasto so 'conta' depois de um limiar, p/ um clique normal
        nao virar reordenacao por acidente."""
        estado = {"x0": 0, "arrastou": False}

        def press(e):
            estado["x0"] = e.x_root
            estado["arrastou"] = False

        def motion(e):
            if not estado["arrastou"] and abs(e.x_root - estado["x0"]) > 8:
                estado["arrastou"] = True
                self._status(T("status_arraste_reposicionar"), MUTED)

        def release(e):
            # after_idle: sai deste handler antes de _montar_seletor destruir 'btn'
            if estado["arrastou"]:
                destino = self._aba_no_ponto(e.x_root)
                if destino is not None and destino != i:
                    self.after_idle(lambda: self._mover_lampada(i, destino))
                else:
                    self._status(T("status_lampada_atual", nome=self._nome_ativo()))
            else:
                self.after_idle(lambda: self._selecionar_lampada(i))

        btn.bind("<ButtonPress-1>", press, add="+")
        btn.bind("<B1-Motion>", motion, add="+")
        btn.bind("<ButtonRelease-1>", release, add="+")

    def _aba_no_ponto(self, x_root):
        """Indice da aba cujo centro esta mais perto da posicao horizontal do mouse."""
        melhor, melhor_d = None, None
        for j, b in enumerate(self._tab_btns):
            try:
                centro = b.winfo_rootx() + b.winfo_width() / 2
            except Exception:
                continue
            d = abs(x_root - centro)
            if melhor_d is None or d < melhor_d:
                melhor_d, melhor = d, j
        return melhor

    def _mover_lampada(self, origem, destino):
        """Reposiciona a lampada na ordem e persiste no JSON. Reordena lampadas e
        controladores juntos (controladores[i] <-> lampadas[i]) e mantem
        selecionada a mesma lampada de antes."""
        n = len(self.lampadas)
        if not (0 <= origem < n) or origem == destino:
            return
        destino = max(0, min(n - 1, destino))
        id_sel = self.lampadas[self.idx].get("id") if 0 <= self.idx < n else None
        self.lampadas.insert(destino, self.lampadas.pop(origem))
        self.controladores.insert(destino, self.controladores.pop(origem))
        self.idx = next((k for k, l in enumerate(self.lampadas)
                         if l.get("id") == id_sel), self.idx)
        salvar_lampadas(self.lampadas)
        self.lbl_titulo.config(text=self._nome_ativo())
        self._montar_seletor()
        self._status(T("status_ordem_lampadas"), OK)

    def _montar_cenas(self):
        """(Re)constroi o painel de cenas. Com mais de uma lampada aparece o
        botao 'aplicar em todas', que faz os botoes de cena agirem no grupo."""
        for w in self.cenas_frame.winfo_children():
            w.destroy()
        f = self.cenas_frame
        if len(self.controladores) > 1:
            self.btn_grupo_cenas = RoundedButton(
                f, text="", width=250, height=28, radius=9,
                command=self._toggle_grupo_cenas)
            self.btn_grupo_cenas.pack(anchor="w", pady=(0, 8))
            self._refletir_grupo_cenas()
        else:
            self._grupo_cenas = False
            self.btn_grupo_cenas = None
        self._btns_cena = {}
        tk.Label(f, text=T("lbl_fixas"), bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 3))
        gfix = tk.Frame(f, bg=CARD)
        gfix.pack(fill="x")
        for cid, temp, bri in CENAS_FIXAS:
            b = RoundedButton(gfix, text=T(cid), width=88, height=32, radius=10,
                              command=lambda n=cid, t=temp, br=bri: self._cena_fixa(n, t, br))
            b.pack(side="left", expand=True, fill="x", padx=2)
            self._btns_cena[cid] = b
        tk.Label(f, text=T("lbl_em_movimento"), bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 3))
        linha = None
        for i, (cid, fab) in enumerate(CENAS_MOV):
            if i % 3 == 0:
                linha = tk.Frame(f, bg=CARD)
                linha.pack(fill="x")
            b = RoundedButton(linha, text=T(cid), width=88, height=32, radius=10,
                              command=lambda n=cid, g=fab: self._cena_mov(n, g))
            b.pack(side="left", expand=True, fill="x", padx=2, pady=2)
            self._btns_cena[cid] = b
        RoundedButton(f, text=T("btn_parar_cena"), width=110, height=28, radius=9,
                      fill=STOP, hover=STOP_HOVER, active=STOP_HOVER,
                      command=self._parar_cena).pack(anchor="w", pady=(8, 0))
        self._refletir_cena_ativa()

    def _selecionar_lampada(self, idx):
        if idx == self.idx or not (0 <= idx < len(self.controladores)):
            return
        # so o ambiente (ambilight) acompanha a selecao; a cena NAO para ao trocar
        # de aba -- assim da p/ gerenciar cada lampada sem interromper as outras.
        self._parar_efeitos_ativos(parar_cena=False)
        self.idx = idx
        self.ctrl = self.controladores[idx]
        self._bind_display(self.ctrl)
        self.lbl_titulo.config(text=self._nome_ativo())
        self._montar_seletor()
        self._refletir_cena_ativa()      # destaca a cena (se houver) da nova lampada
        self._atualizar_aviso_online()   # aviso offline reflete a nova lampada
        self._status(T("status_lampada_atual", nome=self._nome_ativo()))
        self.ctrl.pedir_status()

    def _parar_efeitos_ativos(self, parar_cena=True):
        """Desliga o modo ambiente (sempre) e, se pedido, a cena da lampada ativa."""
        if self._ambiente_ativo:
            self._ambiente_ativo = False
            self._refletir_ambiente()
        if parar_cena:
            try:
                self.ctrl.parar_cena(restaurar=False)
            except Exception:
                pass

    def _abrir_config(self):
        ConfigWindow(self)

    def recarregar_lampadas(self):
        self._parar_efeitos_ativos()
        id_atual = self.lampadas[self.idx].get("id") if (
            self.lampadas and 0 <= self.idx < len(self.lampadas)) else None
        for c in self.controladores:
            try:
                c.encerrar()
            except Exception:
                pass
        self.lampadas = carregar_lampadas()
        self.controladores = [Controlador(c) for c in self.lampadas]
        for c in self.controladores:
            c.fade = self._fade
            c.on_ip = self._ip_redescoberto
        # descarta estado (cena/online) de lampadas que nao existem mais
        ids = {l.get("id") for l in self.lampadas}
        for d in (self._cenas_ativas, self._online_lamp, self._falhas_online):
            for k in [k for k in d if k not in ids]:
                del d[k]
        # preserva a lampada selecionada se ela ainda existir
        self.idx = next((i for i, l in enumerate(self.lampadas)
                         if l.get("id") == id_atual), 0)
        self.ctrl = self.controladores[self.idx] if self.controladores else _CtrlVazio()
        self._bind_display(self.ctrl)
        self.lbl_titulo.config(text=self._nome_ativo())
        self._montar_seletor()
        self._montar_cenas()
        if self.controladores:
            self.ctrl.pedir_status()
            self._status(T("status_config_atualizada"), OK)
        else:
            self._status(T("status_nenhuma_lampada_config"), AMBER)

    def _montar_ui(self):
        tk.Frame(self, bg=BG, height=8).pack()  # respiro no topo

        corpo = tk.Frame(self, bg=BG)
        corpo.pack(fill="both", expand=True, padx=6)
        esq = tk.Frame(corpo, bg=BG)
        esq.pack(side="left", anchor="n")
        dirc = tk.Frame(corpo, bg=BG)
        dirc.pack(side="left", anchor="n")

        # ===================== COLUNA ESQUERDA =====================
        # Cabecalho
        _, cab = self._card(esq)
        topo = tk.Frame(cab, bg=CARD)
        topo.pack(fill="x")
        self.lbl_titulo = tk.Label(topo, text=self._nome_ativo(), bg=CARD, fg=FG,
                                   font=("Segoe UI Semibold", 16))
        self.lbl_titulo.pack(side="left")
        self.lbl_status = tk.Label(topo, text=T("status_conectando"), bg=CARD, fg=MUTED,
                                   font=("Segoe UI", 8))
        self.lbl_status.pack(side="right", pady=(7, 0))
        # seletor de lampadas + engrenagem de configuracao
        self.sel_frame = tk.Frame(cab, bg=CARD)
        self.sel_frame.pack(fill="x", pady=(6, 0))
        self._montar_seletor()
        linha_power = tk.Frame(cab, bg=CARD)
        linha_power.pack(fill="x", pady=(8, 0))
        self.var_power = tk.BooleanVar(value=True)
        self.btn_power = RoundedButton(linha_power, text=T("btn_ligada"), command=self._toggle_power,
                                       width=180, height=44, radius=13, fill=ACCENT,
                                       hover=ACCENT_HOVER, active=ACCENT_ACTIVE, fg="white",
                                       font=("Segoe UI Semibold", 12))
        self.btn_power.pack(side="left")
        self.swatch = Swatch(linha_power)
        self.swatch.pack(side="right")
        # aviso discreto (so aparece quando a lampada esta inacessivel)
        self.lbl_aviso = tk.Label(cab, text="", bg=CARD, fg=AMBER, anchor="w",
                                  justify="left", font=("Segoe UI", 9))

        # Modo (segmentado)
        _, cmodo = self._card(esq, T("card_modo"))
        seg = tk.Frame(cmodo, bg=CARD)
        seg.pack(fill="x")
        self.var_modo = tk.StringVar(value="white")
        self.btn_branco = RoundedButton(seg, text=T("btn_branco"), width=132, height=32, radius=10,
                                        command=lambda: self._selecionar_modo("white"))
        self.btn_branco.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_cor = RoundedButton(seg, text=T("btn_cor"), width=132, height=32, radius=10,
                                     command=lambda: self._selecionar_modo("colour"))
        self.btn_cor.pack(side="left", expand=True, fill="x", padx=(4, 0))

        # Brilho
        _, cbri = self._card(esq)
        self.lbl_brilho = tk.Label(cbri, text=T("lbl_brilho", pct=100), bg=CARD, fg=FG,
                                   font=("Segoe UI", 10))
        self.lbl_brilho.pack(anchor="w")
        self.var_brilho = tk.IntVar(value=100)
        self.sld_brilho = Slider(cbri, self.var_brilho, from_=1, to=100, width=276,
                                 command=self._brilho_mudou)
        self.sld_brilho.pack(fill="x", pady=(6, 0))

        # Temperatura (so no modo branco)
        self.card_temp, ctmp = self._card(esq)
        self.lbl_temp = tk.Label(ctmp, text=T("lbl_temperatura", pct=50),
                                 bg=CARD, fg=FG, font=("Segoe UI", 10))
        self.lbl_temp.pack(anchor="w")
        self.var_temp = tk.IntVar(value=50)
        self.sld_temp = Slider(ctmp, self.var_temp, from_=0, to=100, width=276,
                               command=self._temp_mudou)
        self.sld_temp.pack(fill="x", pady=(6, 0))

        # Saturacao (so no modo cor) — quao viva e a cor
        self.card_sat, csat = self._card(esq)
        self.lbl_sat = tk.Label(csat, text=T("lbl_saturacao", pct=100),
                                bg=CARD, fg=FG, font=("Segoe UI", 10))
        self.lbl_sat.pack(anchor="w")
        self.var_sat = tk.IntVar(value=100)
        self.sld_sat = Slider(csat, self.var_sat, from_=0, to=100, width=276,
                              command=self._sat_mudou)
        self.sld_sat.pack(fill="x", pady=(6, 0))

        # Cores: presets + anel de matiz (fiel ao que a lampada exibe)
        self.card_cores, ccor = self._card(esq, T("card_cores"))
        grade = tk.Frame(ccor, bg=CARD)
        grade.pack(fill="x")
        for chave, rgb in PRESETS:
            ColorDot(grade, rgb, command=lambda c=rgb: self._aplicar_cor(c)).pack(
                side="left", expand=True)
        self.anel = None
        if ANEL_OK:   # anel precisa do PIL/ImageTk (embutido no .exe)
            try:
                self.anel = AnelMatiz(ccor, command=self._anel_mudou)
                self.anel.pack(pady=(10, 0))
            except Exception:
                self.anel = None   # ImageTk indisponivel em runtime -> cai no picker
        if self.anel is None:
            RoundedButton(ccor, text=T("btn_escolher_cor"), width=140, height=30, radius=10,
                          command=self._escolher_cor).pack(anchor="w", pady=(8, 0))

        # Dia / Noite automatico
        _, cdn = self._card(esq, T("card_dia_noite"))
        linha_dn = tk.Frame(cdn, bg=CARD)
        linha_dn.pack(fill="x")
        self.btn_dn = RoundedButton(linha_dn, text="", width=130, height=30, radius=10,
                                    command=self._toggle_dia_noite)
        self.btn_dn.pack(side="left")
        RoundedButton(linha_dn, text=T("btn_configurar"), width=120, height=30, radius=10,
                      command=self._abrir_dia_noite).pack(side="right")
        self.lbl_dn = tk.Label(cdn, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.lbl_dn.pack(anchor="w", pady=(6, 0))
        self._refletir_dia_noite()

        # ===================== COLUNA DIREITA =====================
        # Cenas (agem na lampada ativa ou em todas, conforme "aplicar em todas")
        _, ccenas = self._card(dirc, T("card_cenas"))
        self.cenas_frame = tk.Frame(ccenas, bg=CARD)
        self.cenas_frame.pack(fill="x")
        self._montar_cenas()

        # Modo Ambiente (Ambilight)
        _, camb = self._card(dirc, T("card_modo_ambiente"))
        self.btn_ambiente = RoundedButton(camb, text="", width=160, height=30, radius=10,
                                          command=self._toggle_ambiente)
        self.btn_ambiente.pack(anchor="w")
        tk.Label(camb, text=T("desc_modo_ambiente"),
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 0))
        self._refletir_ambiente()

        # Favoritos
        _, cfav = self._card(dirc, T("card_favoritos"))
        self.fav_frame = tk.Frame(cfav, bg=CARD)
        self.fav_frame.pack(fill="x")
        RoundedButton(cfav, text=T("btn_salvar_favorito"), width=250, height=30, radius=10,
                      command=self._salvar_favorito).pack(anchor="w", pady=(8, 0))
        self._render_favoritos()

        # Timer para desligar
        _, ctim = self._card(dirc, T("card_timer"))
        gtim = tk.Frame(ctim, bg=CARD)
        gtim.pack(fill="x")
        for mins in (15, 30, 60):
            RoundedButton(gtim, text=T("btn_timer_min", mins=mins), width=70, height=30, radius=10,
                          command=lambda mm=mins: self._set_timer(mm)).pack(
                side="left", expand=True, fill="x", padx=2)
        custom = tk.Frame(ctim, bg=CARD)
        custom.pack(fill="x", pady=(6, 0))
        tk.Label(custom, text=T("lbl_personalizado"), bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        self.ent_timer = tk.Entry(custom, width=5, bg=CARD2, fg=FG, insertbackground=FG,
                                  relief="flat", justify="center", font=("Segoe UI", 10))
        self.ent_timer.pack(side="left", padx=6, ipady=3)
        self.ent_timer.bind("<Return>", lambda e: self._timer_personalizado())
        tk.Label(custom, text=T("lbl_min"), bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        RoundedButton(custom, text=T("btn_ligar"), width=66, height=28, radius=9,
                      command=self._timer_personalizado).pack(side="right")
        rodap_tim = tk.Frame(ctim, bg=CARD)
        rodap_tim.pack(fill="x", pady=(8, 0))
        RoundedButton(rodap_tim, text=T("btn_cancelar"), width=110, height=28, radius=9,
                      fill=STOP, hover=STOP_HOVER, active=STOP_HOVER,
                      command=self._cancelar_timer).pack(side="left")
        self.lbl_timer = tk.Label(rodap_tim, text=T("timer_vazio"), bg=CARD, fg=MUTED, font=("Segoe UI", 10))
        self.lbl_timer.pack(side="right")

        # Estado padrao
        _, cpad = self._card(dirc, T("card_estado_padrao"))
        linha_pad = tk.Frame(cpad, bg=CARD)
        linha_pad.pack(fill="x")
        RoundedButton(linha_pad, text=T("btn_salvar_atual"), width=120, height=30, radius=10,
                      command=self._salvar_padrao).pack(side="left", padx=(0, 6))
        RoundedButton(linha_pad, text=T("btn_aplicar"), width=96, height=30, radius=10,
                      command=self._aplicar_padrao).pack(side="left")
        self.btn_ao_abrir = RoundedButton(cpad, text="", width=250, height=28, radius=9,
                                          command=self._toggle_ao_abrir)
        self.btn_ao_abrir.pack(anchor="w", pady=(8, 0))
        self._refletir_ao_abrir()

        # Rodape (abaixo das duas colunas)
        rod = tk.Frame(self, bg=BG)
        rod.pack(fill="x", padx=12, pady=(2, 10))
        RoundedButton(rod, text=T("btn_atualizar_estado"), width=140, height=30, radius=10,
                      command=lambda: self.ctrl.pedir_status()).pack(side="left")
        self.btn_fade = RoundedButton(rod, text="", width=160, height=30, radius=10,
                                      command=self._toggle_fade)
        self.btn_fade.pack(side="left", padx=(8, 0))
        self._refletir_fade()
        RoundedButton(rod, text=T("btn_atalhos"), width=110, height=30, radius=10,
                      command=self._abrir_atalhos).pack(side="right")

        self._selecionar_modo("white", enviar=False)
        self._atualizar_visibilidade_modo()
        self._atualizar_swatch_branco()

    # ---------- helpers de estado visual ----------
    def _marcar_acao(self):
        """Apos uma acao do usuario, ignora o poll por alguns segundos para a
        leitura periodica nao 'voltar' o menu/sliders ao estado anterior."""
        self._mute_ate = time.monotonic() + 3.0

    def _status(self, msg, cor=MUTED):
        self.lbl_status.config(text=msg, fg=cor)

    def _refletir_power(self, ligado):
        self.btn_power.set_text(T("btn_ligada") if ligado else T("btn_desligada"))
        if ligado:
            self.btn_power.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
        else:
            self.btn_power.set_colors(OFF, OFF_HOVER, OFF_ACTIVE)

    def _refletir_ligada(self):
        """Marca a UI como ligada. Ajustar brilho/cor/temp/modo numa lampada apagada
        acende ela no hardware (a Tuya liga ao receber o comando); sem isto o botao
        continuaria mostrando DESLIGADA e era preciso ligar e desligar de novo para
        apagar de fato."""
        if not self.var_power.get():
            self.var_power.set(True)
            self._refletir_power(True)

    def _set_modo_ui(self, modo):
        if modo == "white":
            self.btn_branco.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
            self.btn_cor.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)
        else:
            self.btn_cor.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
            self.btn_branco.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)

    def _refletir_ao_abrir(self):
        on = bool(self.prefs.get("aplicar_ao_abrir"))
        self.btn_ao_abrir.set_text(("●  " if on else "○  ") + T("btn_aplicar_ao_ligar"))
        if on:
            self.btn_ao_abrir.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
        else:
            self.btn_ao_abrir.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)

    def _atualizar_visibilidade_modo(self):
        # branco -> slider de temperatura; cor -> slider de saturacao
        if self.var_modo.get() == "white":
            self.card_sat.pack_forget()
            self.card_temp.pack(fill="x", padx=6, pady=(0, 7), before=self.card_cores)
        else:
            self.card_temp.pack_forget()
            self.card_sat.pack(fill="x", padx=6, pady=(0, 7), before=self.card_cores)

    def _atualizar_swatch_branco(self):
        self.swatch.set(temp_para_rgb(int(self.var_temp.get()), int(self.var_brilho.get())))

    # ---------- callbacks de UI ----------
    def _toggle_power(self):
        self._marcar_acao()
        self._limpar_cena_ativa()
        novo = not self.var_power.get()
        self.var_power.set(novo)
        self._refletir_power(novo)
        self.ctrl.power(novo)

    def _selecionar_modo(self, modo, enviar=True):
        self.var_modo.set(modo)
        self._set_modo_ui(modo)
        self._atualizar_visibilidade_modo()
        if not enviar or self._sincronizando:
            return
        if modo == "white":
            self._marcar_acao()
            self._refletir_ligada()
            self._limpar_cena_ativa()
            self.ctrl.modo_branco()
            self._atualizar_swatch_branco()
        else:
            self._cor_mudou()   # aplica o H/S/V atuais (anel + sliders)

    def _brilho_mudou(self, _=None):
        if self._sincronizando:
            return
        pct = int(float(self.var_brilho.get()))
        self.lbl_brilho.config(text=T("lbl_brilho", pct=pct))
        if self.var_modo.get() == "colour":
            self._cor_mudou()        # em cor, o brilho e o V (valor) do HSV
            return
        self._marcar_acao()
        self._refletir_ligada()
        self._limpar_cena_ativa()
        self._atualizar_swatch_branco()
        if self._debounce_brilho:
            self.after_cancel(self._debounce_brilho)
        self._debounce_brilho = self.after(220, lambda: self.ctrl.brilho(pct))

    def _temp_mudou(self, _=None):
        if self._sincronizando:
            return
        self._marcar_acao()
        self._refletir_ligada()
        self._limpar_cena_ativa()
        pct = int(float(self.var_temp.get()))
        self.lbl_temp.config(text=T("lbl_temperatura", pct=pct))
        self._atualizar_swatch_branco()
        if self._debounce_temp:
            self.after_cancel(self._debounce_temp)
        self._debounce_temp = self.after(220, lambda: self.ctrl.temperatura(pct))

    def _sat_mudou(self, _=None):
        if self._sincronizando:
            return
        self._cor_mudou()

    def _anel_mudou(self, h):
        """Callback do anel: novo matiz. Entra no modo cor se preciso e aplica."""
        self._cor_h = h
        if self.var_modo.get() != "colour":
            self.var_modo.set("colour")
            self._set_modo_ui("colour")
            self._atualizar_visibilidade_modo()
        self._cor_mudou()

    def _cor_mudou(self):
        """Aplica a cor atual (matiz do anel + saturacao + brilho dos sliders) na
        lampada selecionada, com debounce. Atualiza o swatch e o centro do anel."""
        self._marcar_acao()
        self._refletir_ligada()
        self._limpar_cena_ativa()
        h = self._cor_h
        s = max(0.0, min(1.0, int(self.var_sat.get()) / 100.0))
        v = max(0.01, min(1.0, int(self.var_brilho.get()) / 100.0))
        self.lbl_sat.config(text=T("lbl_saturacao", pct=int(self.var_sat.get())))
        rgb = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, s, v))
        self.swatch.set(rgb)
        if self.anel:
            self.anel.set_cor_central(rgb)
        if self._debounce_cor:
            self.after_cancel(self._debounce_cor)
        self._debounce_cor = self.after(180, lambda: self.ctrl.cor_hsv(h, s, v))

    def _escolher_cor(self):
        rgb, _ = colorchooser.askcolor(color=self._cor_atual_hex(), parent=self,
                                       title=T("titulo_escolher_cor"))
        if rgb:
            self._aplicar_cor(tuple(int(c) for c in rgb))

    def _aplicar_cor(self, rgb, trocar_modo=True):
        """Aplica uma cor RGB (preset/picker). Pastel/quase-branco vira branco; as
        demais alimentam o estado HSV (matiz+saturacao), mantendo o brilho atual."""
        self._marcar_acao()
        self._refletir_ligada()
        self._limpar_cena_ativa()
        eh_branco, ajust = cor_exibivel(rgb)
        if eh_branco:
            self.var_modo.set("white")
            self._set_modo_ui("white")
            self._atualizar_visibilidade_modo()
            self.ctrl.modo_branco()
            self._atualizar_swatch_branco()
            self._status(T("status_cor_muito_clara"), MUTED)
            return
        r, g, b = (c / 255.0 for c in ajust)
        h, s, _v = colorsys.rgb_to_hsv(r, g, b)
        self._sincronizando = True
        try:
            self._cor_h = h
            self.var_sat.set(round(s * 100))   # presets entram com sua saturacao
            if self.anel:
                self.anel.set_hue(h)
            if trocar_modo:
                self.var_modo.set("colour")
                self._set_modo_ui("colour")
            self._atualizar_visibilidade_modo()
        finally:
            self._sincronizando = False
        self._cor_mudou()   # mantem o brilho (V) atual do slider

    def _toggle_fade(self):
        self._fade = not self._fade
        self.prefs["fade"] = self._fade
        salvar_prefs(self.prefs)
        for c in self.controladores:
            c.fade = self._fade
        self._refletir_fade()

    def _refletir_fade(self):
        on = self._fade
        self.btn_fade.set_text(("●  " if on else "○  ") + T("btn_transicao_suave"))
        if on:
            self.btn_fade.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
        else:
            self.btn_fade.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)

    def _cor_atual_hex(self):
        return "#%02x%02x%02x" % self._cor_atual_rgb()

    def _cor_atual_rgb(self):
        h = self.swatch.itemcget(self.swatch._shape, "fill").lstrip("#")
        if len(h) == 6:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        return (255, 255, 255)

    # ---------- cenas (uma lampada ou todas) ----------
    def _toggle_grupo_cenas(self):
        self._grupo_cenas = not self._grupo_cenas
        self._refletir_grupo_cenas()

    def _refletir_grupo_cenas(self):
        if not self.btn_grupo_cenas:
            return
        on = self._grupo_cenas
        self.btn_grupo_cenas.set_text(
            ("●  " if on else "○  ") + T("btn_aplicar_em_todas"))
        if on:
            self.btn_grupo_cenas.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
        else:
            self.btn_grupo_cenas.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)

    def _refletir_cena_ativa(self):
        """Destaca (azul) o botao da cena ativa NA LAMPADA SELECIONADA; os demais
        voltam ao normal. A cena ativa e rastreada por lampada (`_cenas_ativas`),
        entao trocar de aba mostra o que cada uma esta tocando."""
        ativa = self._cenas_ativas.get(self._id_ativo())
        for nome, b in self._btns_cena.items():
            if nome == ativa:
                b.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
            else:
                b.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)

    def _marcar_cena_ativa(self, nome, alvos):
        """Marca a cena 'nome' como ativa nas lampadas alvo (lista de (pos, ctrl))."""
        for _, c in alvos:
            cid = c.cfg.get("id")
            if cid:
                self._cenas_ativas[cid] = nome
        self._refletir_cena_ativa()

    def _limpar_cena_ativa(self):
        """Tira o destaque de cena da lampada SELECIONADA (uma acao manual nela
        cancela/substitui a cena; as outras lampadas seguem como estao)."""
        cid = self._id_ativo()
        if cid in self._cenas_ativas:
            del self._cenas_ativas[cid]
            self._refletir_cena_ativa()

    def _alvos_cena(self):
        """Controladores que recebem a cena: todos (modo grupo, com +1 lampada) ou
        apenas o selecionado. Retorna lista de (posicao, controlador) -- a posicao
        defasa cada lampada nas cenas em movimento."""
        if self._grupo_cenas and len(self.controladores) > 1:
            return list(enumerate(self.controladores))
        if self.controladores:
            return [(0, self.ctrl)]
        return []

    def _cena_fixa(self, nome, temp, brilho):
        self._marcar_acao()
        self._sincronizando = True
        try:
            self.var_modo.set("white")
            self._set_modo_ui("white")
            self.var_brilho.set(brilho)
            self.lbl_brilho.config(text=T("lbl_brilho", pct=brilho))
            self.var_temp.set(temp)
            self.lbl_temp.config(text=T("lbl_temperatura", pct=temp))
            self.var_power.set(True)
            self._refletir_power(True)
            self._atualizar_swatch_branco()
            self._atualizar_visibilidade_modo()
        finally:
            self._sincronizando = False
        func = construir_func_estado({"modo": "white", "temp": temp, "brilho": brilho})
        alvos = self._alvos_cena()
        for _, c in alvos:
            c.aplicar_func(func)
        self._marcar_cena_ativa(nome, alvos)   # fixa: so destaca (nao "volta ao anterior")
        if len(alvos) > 1:
            self._status(T("status_grupo_cena_n", nome=T(nome), n=len(alvos)))
        else:
            self._status(T("status_cena", nome=T(nome)))

    def _cena_mov(self, nome, fabrica, offset=2.0):
        """Inicia uma cena em movimento. No modo grupo roda em todas as lampadas,
        defasando cada uma (fase0) e enfraquecendo a de teto; sozinha usa fase 0
        e brilho cheio."""
        self._marcar_acao()
        alvos = self._alvos_cena()
        grupo = len(alvos) > 1
        for pos, (_, c) in enumerate(alvos):
            fase = pos * offset if grupo else 0.0
            ev = escala_brilho_cfg(c.cfg) if grupo else 1.0
            c.iniciar_cena(lambda b, f=fase, e=ev: fabrica(b, f, e))
        self.var_power.set(True)
        self._refletir_power(True)
        self._marcar_cena_ativa(nome, alvos)
        if grupo:
            self._status(T("status_grupo_cena_n", nome=T(nome), n=len(alvos)), ACCENT)
        else:
            self._status(T("status_cena_movimento", nome=T(nome)), ACCENT)

    def _parar_cena(self):
        # para TODA lampada com cena ativa -- inclusive as que continuaram tocando
        # depois de o "aplicar em todas" ter sido desligado (senao ficariam orfas,
        # animando para sempre sem como parar)
        ids = set(self._cenas_ativas) | {c.cfg.get("id") for _, c in self._alvos_cena()}
        paradas = 0
        for c in self.controladores:
            if c.cfg.get("id") in ids:
                c.parar_cena()   # volta cada lampada ao estado de antes da cena
                self._cenas_ativas.pop(c.cfg.get("id"), None)
                paradas += 1
        self._refletir_cena_ativa()
        self._status(T("status_cenas_paradas") if paradas > 1 else T("status_cena_parada"))
        # reflete na UI o estado restaurado da lampada selecionada
        if self.controladores:
            self.ctrl.pedir_status()

    def _estado_atual(self):
        modo = self.var_modo.get()
        est = {"modo": modo, "brilho": int(self.var_brilho.get())}
        if modo == "colour":
            est["cor"] = list(self._cor_atual_rgb())
        else:
            est["temp"] = int(self.var_temp.get())
        return est

    def _salvar_padrao(self):
        self.prefs["padrao"] = self._estado_atual()
        salvar_prefs(self.prefs)
        self._status(T("status_padrao_salvo"), OK)

    def _aplicar_estado(self, est, msg=None, todas=False):
        """Reflete um estado salvo (padrao/favorito) na UI e aplica na lampada.
        Com todas=True aplica em todas as lampadas (usado pelo dia/noite)."""
        self._marcar_acao()
        self._limpar_cena_ativa()
        self._sincronizando = True
        try:
            modo = est.get("modo", "white")
            self.var_modo.set(modo)
            self._set_modo_ui(modo)
            self.var_brilho.set(int(est.get("brilho", 100)))
            self.lbl_brilho.config(text=T("lbl_brilho", pct=int(est.get('brilho', 100))))
            if modo == "colour" and est.get("cor"):
                # alimenta o estado HSV (anel + saturacao) a partir da cor salva
                r, g, b = (c / 255.0 for c in est["cor"])
                h, s, _v = colorsys.rgb_to_hsv(r, g, b)
                self._cor_h = h
                self.var_sat.set(round(s * 100))
                self.lbl_sat.config(
                    text=T("lbl_saturacao", pct=int(self.var_sat.get())))
                if self.anel:
                    self.anel.set_hue(h)
                self.swatch.set(tuple(est["cor"]))
            else:
                self.var_temp.set(int(est.get("temp", 50)))
                self.lbl_temp.config(
                    text=T("lbl_temperatura", pct=int(est.get('temp', 50))))
                self._atualizar_swatch_branco()
            self.var_power.set(True)
            self._refletir_power(True)
            self._atualizar_visibilidade_modo()
        finally:
            self._sincronizando = False
        func = construir_func_estado(est)
        if todas:
            for c in self.controladores:
                c.aplicar_func(func)
        else:
            self.ctrl.aplicar_func(func)
        if msg:
            self._status(msg, OK)

    def _aplicar_padrao(self):
        est = self.prefs.get("padrao")
        if not est:
            messagebox.showinfo(T("msg_estado_padrao_titulo"),
                                T("msg_estado_padrao_corpo"))
            return
        self._aplicar_estado(est, T("status_padrao_aplicado"))

    def _toggle_ao_abrir(self):
        self.prefs["aplicar_ao_abrir"] = not bool(self.prefs.get("aplicar_ao_abrir"))
        salvar_prefs(self.prefs)
        self._refletir_ao_abrir()

    # ---------- favoritos ----------
    def _render_favoritos(self):
        for w in self.fav_frame.winfo_children():
            w.destroy()
        self._fav_btns = []
        favs = self.prefs.get("favoritos", [])
        if not favs:
            tk.Label(self.fav_frame, text=T("fav_nenhum"), bg=CARD, fg=MUTED,
                     font=("Segoe UI", 9)).pack(anchor="w")
            return
        for i, f in enumerate(favs):
            row = tk.Frame(self.fav_frame, bg=CARD)
            row.pack(fill="x", pady=2)
            # sem 'command': clique aplica, arrastar p/ cima/baixo reordena (ver _tornar_fav)
            btn = RoundedButton(row, text=f.get("nome", T("fav_nome_padrao")),
                                width=210, height=28, radius=9)
            btn.pack(side="left", expand=True, fill="x")
            self._fav_btns.append(btn)
            self._tornar_fav_arrastavel(btn, i)
            RoundedButton(row, text=T("fav_botao_excluir"), width=30, height=28, radius=9,
                          fill=STOP, hover=STOP_HOVER, active=STOP_HOVER,
                          command=lambda idx=i: self._excluir_favorito(idx)).pack(
                side="right", padx=(6, 0))

    def _tornar_fav_arrastavel(self, btn, i):
        """Clique aplica o favorito; arrasto vertical reordena (igual as abas)."""
        estado = {"y0": 0, "arrastou": False}

        def press(e):
            estado["y0"] = e.y_root
            estado["arrastou"] = False

        def motion(e):
            if not estado["arrastou"] and abs(e.y_root - estado["y0"]) > 8:
                estado["arrastou"] = True
                self._status(T("status_arraste_reordenar_favorito"), MUTED)

        def release(e):
            if estado["arrastou"]:
                destino = self._fav_no_ponto(e.y_root)
                if destino is not None and destino != i:
                    # after_idle: sai do handler antes de _render_favoritos destruir 'btn'
                    self.after_idle(lambda: self._mover_favorito(i, destino))
            else:
                favs = self.prefs.get("favoritos", [])
                if 0 <= i < len(favs):
                    self._aplicar_estado(favs[i].get("estado", {}), T("status_favorito_aplicado"))

        btn.bind("<ButtonPress-1>", press, add="+")
        btn.bind("<B1-Motion>", motion, add="+")
        btn.bind("<ButtonRelease-1>", release, add="+")

    def _fav_no_ponto(self, y_root):
        """Indice do favorito cujo centro esta mais perto da posicao vertical do mouse."""
        melhor, melhor_d = None, None
        for j, b in enumerate(self._fav_btns):
            try:
                centro = b.winfo_rooty() + b.winfo_height() / 2
            except Exception:
                continue
            d = abs(y_root - centro)
            if melhor_d is None or d < melhor_d:
                melhor_d, melhor = d, j
        return melhor

    def _mover_favorito(self, origem, destino):
        favs = self.prefs.get("favoritos", [])
        n = len(favs)
        if not (0 <= origem < n) or origem == destino:
            return
        destino = max(0, min(n - 1, destino))
        favs.insert(destino, favs.pop(origem))
        salvar_prefs(self.prefs)
        self._render_favoritos()
        self._status(T("status_ordem_favoritos"), OK)

    def _salvar_favorito(self):
        nome = simpledialog.askstring(T("dlg_novo_favorito_titulo"),
                                      T("dlg_novo_favorito_prompt"), parent=self)
        if not nome or not nome.strip():
            return
        self.prefs.setdefault("favoritos", []).append(
            {"nome": nome.strip(), "estado": self._estado_atual()})
        salvar_prefs(self.prefs)
        self._render_favoritos()
        self._status(T("status_favorito_salvo", nome=nome.strip()), OK)

    def _excluir_favorito(self, idx):
        favs = self.prefs.get("favoritos", [])
        if 0 <= idx < len(favs):
            nome = favs[idx].get("nome", T("fav_nome_padrao"))
            if messagebox.askyesno(T("msg_excluir_favorito_titulo"),
                                    T("msg_excluir_favorito_corpo", nome=nome),
                                    parent=self):
                favs.pop(idx)
                salvar_prefs(self.prefs)
                self._render_favoritos()
                self._status(T("status_favorito_excluido"))

    # ---------- timer para desligar ----------
    def _set_timer(self, minutos):
        self._cancelar_timer(silencioso=True)
        self._timer_restante = minutos * 60
        self._status(T("status_timer_ligado", minutos=minutos), ACCENT)
        self._tick_timer()

    def _tick_timer(self):
        if self._timer_restante <= 0:
            self._timer_id = None
            self.lbl_timer.config(text=T("timer_vazio"))
            self._ambiente_ativo = False           # para o ambilight se estiver ligado
            self._refletir_ambiente()
            self._cenas_ativas.clear()             # tira o destaque de cena de todas
            self._refletir_cena_ativa()
            for c in self.controladores:           # o timer desliga TODAS as lampadas
                c.parar_cena(restaurar=False)      # vai desligar; nao adianta restaurar
                c.power(False)
            self.var_power.set(False)
            self._refletir_power(False)
            self._status(T("status_desligada_timer"), OK)
            return
        m, s = divmod(self._timer_restante, 60)
        self.lbl_timer.config(text=T("timer_contagem", m=m, s=s))
        self._timer_restante -= 1
        self._timer_id = self.after(1000, self._tick_timer)

    def _cancelar_timer(self, silencioso=False):
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        self._timer_restante = 0
        self.lbl_timer.config(text=T("timer_vazio"))
        if not silencioso:
            self._status(T("status_timer_cancelado"))

    def _timer_personalizado(self):
        try:
            mins = int(self.ent_timer.get().strip())
        except ValueError:
            mins = 0
        if mins > 0:
            self._set_timer(mins)
        else:
            self._status(T("status_numero_invalido"), WARN)

    # ---------- dia / noite (agendamento automatico) ----------
    def _refletir_dia_noite(self):
        on = bool((self.prefs.get("dia_noite") or {}).get("ativo"))
        self.btn_dn.set_text(("●  " if on else "○  ") + T("btn_automatico"))
        if on:
            self.btn_dn.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
        else:
            self.btn_dn.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)
        self._dn_atualizar_label()

    def _toggle_dia_noite(self):
        cfg = self.prefs.setdefault("dia_noite", {})
        if not cfg.get("ativo") and not (cfg.get("dia_fav") and cfg.get("noite_fav")):
            messagebox.showinfo(T("msg_dia_noite_titulo"),
                                T("msg_dia_noite_corpo"), parent=self)
            return
        cfg["ativo"] = not cfg.get("ativo")
        salvar_prefs(self.prefs)
        self._dn_periodo = None
        self._refletir_dia_noite()
        if cfg["ativo"]:
            self._dn_avaliar()

    def _abrir_dia_noite(self):
        DiaNoiteWindow(self)

    # ---------- atalhos globais ----------
    def _hotkey_trigger(self, acao):
        self.after(0, lambda: self._executar_atalho(acao))

    def _executar_atalho(self, acao):
        if acao == "toggle_power":
            self._toggle_power()
        elif acao == "mostrar":
            if self.winfo_viewable():
                self._fechar()                       # esconde na bandeja
            else:
                self.deiconify(); self.lift(); self.focus_force()
        elif acao == "padrao":
            self._aplicar_padrao()
        elif acao == "parar_cena":
            self._parar_cena()

    def _montar_lista_atalhos(self):
        lst = []
        cfgs = self.prefs.get("atalhos") or {}
        for acao, _ in ACOES_ATALHO:
            a = cfgs.get(acao)
            if not (a and a.get("ativo") and a.get("key")):
                continue
            mods = ((MOD_CONTROL if a.get("ctrl") else 0) | (MOD_ALT if a.get("alt") else 0) |
                    (MOD_SHIFT if a.get("shift") else 0) | (MOD_WIN if a.get("win") else 0))
            vk = _key_to_vk(a["key"])
            if mods and vk:   # exige pelo menos um modificador
                lst.append((acao, mods, vk))
        return lst

    def _aplicar_atalhos(self):
        self.hotkeys.aplicar(self._montar_lista_atalhos())

    def _abrir_atalhos(self):
        AtalhosWindow(self)

    # ---------- modo ambiente (ambilight) ----------
    def _refletir_ambiente(self):
        on = self._ambiente_ativo
        self.btn_ambiente.set_text(("●  " if on else "○  ") + T("btn_modo_ambiente"))
        if on:
            self.btn_ambiente.set_colors(ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
        else:
            self.btn_ambiente.set_colors(BTN, BTN_HOVER, BTN_ACTIVE)

    def _toggle_ambiente(self):
        if self._ambiente_ativo:
            self._ambiente_ativo = False
            self._status(T("status_ambiente_desligado"))
        elif not TRAY_OK:
            messagebox.showinfo(T("msg_modo_ambiente_titulo"),
                                T("msg_modo_ambiente_corpo"),
                                parent=self)
            return
        else:
            self._ambiente_ativo = True
            self._ambiente_gen += 1          # invalida qualquer loop de ambiente antigo
            gen = self._ambiente_gen
            ctrl = self.ctrl                 # fixa a lampada-alvo desta sessao
            self._marcar_acao()
            self._refletir_ligada()
            self._limpar_cena_ativa()
            self.var_modo.set("colour")
            self._set_modo_ui("colour")
            self._atualizar_visibilidade_modo()
            self._status(T("status_ambiente_ligado"), ACCENT)
            threading.Thread(target=lambda: self._loop_ambiente(ctrl, gen),
                             daemon=True).start()
        self._refletir_ambiente()

    def _loop_ambiente(self, ctrl, gen):
        ult = None
        # 'gen' garante que so a sessao de ambiente mais recente fique ativa; 'ctrl'
        # e' a lampada-alvo fixada no inicio (nao le self.ctrl, que pode mudar de aba)
        while self._ambiente_ativo and gen == self._ambiente_gen:
            try:
                px = list(ImageGrab.grab().resize((48, 27)).getdata())
                # media circular do matiz ponderada por saturacao*valor:
                # pixels vivos dominam; branco/cinza/UI quase nao contam
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
                if wsum > 0.02 * n:       # ha cor relevante na tela
                    hue = (math.atan2(sy, sx) / 6.2831853) % 1.0
                    rr, gg, bb = colorsys.hsv_to_rgb(hue, 0.9, val)
                else:                      # tela neutra -> branco quente suave
                    rr, gg, bb = colorsys.hsv_to_rgb(0.09, 0.25, val)
                cor = [int(rr * 255), int(gg * 255), int(bb * 255)]
                if ult:                    # suaviza p/ reduzir flicker
                    cor = [int(cor[i] * 0.6 + ult[i] * 0.4) for i in range(3)]
                ult = cor
                c = tuple(cor)
                ctrl.cor_direto(c)
                if self.winfo_exists():   # evita agendar num Tk ja destruido (ao sair)
                    self.after(0, lambda x=c: self.swatch.set(x))
            except Exception:
                pass
            time.sleep(0.3)

    def _fav_por_nome(self, nome):
        for f in self.prefs.get("favoritos", []):
            if f.get("nome") == nome:
                return f.get("estado")
        return None

    @staticmethod
    def _hhmm(s):
        """Converte 'HH:MM' em minutos do dia (0..1439). Retorna None se invalido."""
        try:
            h, m = str(s).split(":")
            h, m = int(h), int(m)
            if 0 <= h < 24 and 0 <= m < 60:
                return h * 60 + m
        except Exception:
            pass
        return None

    def _dn_loop(self):
        self.after(60000, self._dn_loop)
        self._dn_avaliar()

    def _dn_avaliar(self):
        cfg = self.prefs.get("dia_noite") or {}
        if not cfg.get("ativo") or not self.controladores:
            self._dn_atualizar_label()
            return
        agora = datetime.datetime.now()
        nm = agora.hour * 60 + agora.minute
        ds = self._hhmm(cfg.get("dia_hora", "07:00"))
        ns = self._hhmm(cfg.get("noite_hora", "18:00"))
        if ds is None:
            ds = 7 * 60
        if ns is None:
            ns = 18 * 60
        # suporta a janela do "dia" que cruza a meia-noite (ex.: dia 20:00, noite 06:00)
        if ds <= ns:
            ehdia = ds <= nm < ns
        else:
            ehdia = nm >= ds or nm < ns
        periodo = "dia" if ehdia else "noite"
        if periodo != self._dn_periodo:
            self._dn_periodo = periodo
            self._dn_ultimo_alvo = None
            nome = cfg.get("dia_fav") if periodo == "dia" else cfg.get("noite_fav")
            fav = self._fav_por_nome(nome)
            if fav:
                self._aplicar_estado(dict(fav), todas=True)   # dia/noite em todas
            self._dn_base_b = int((fav or {}).get("brilho", 100))
        if periodo == "noite":
            self._dn_rampa(cfg, nm, ns)
        self._dn_atualizar_label()

    def _dn_rampa(self, cfg, nm, ns):
        rampa = max(1, int(cfg.get("rampa_min", 120)))
        minb = max(1, min(100, int(cfg.get("brilho_min", 10))))
        base = self._dn_base_b if self._dn_base_b is not None else 100
        decorrido = nm - ns if nm >= ns else nm + (1440 - ns)
        frac = min(1.0, decorrido / rampa)
        alvo = max(1, min(100, round(base + (minb - base) * frac)))
        # so envia quando o ALVO calculado muda (nao reage ao arredondamento do poll)
        if alvo != self._dn_ultimo_alvo:
            self._dn_ultimo_alvo = alvo
            self._marcar_acao()
            self.var_brilho.set(alvo)
            self.lbl_brilho.config(text=T("lbl_brilho", pct=alvo))
            if self.var_modo.get() == "white":
                self._atualizar_swatch_branco()
            for c in self.controladores:        # rampa noturna em todas as lampadas
                c.brilho_direto(alvo)            # direto, sem fade (a rampa ja e gradual)

    def _dn_atualizar_label(self):
        cfg = self.prefs.get("dia_noite") or {}
        if not cfg.get("ativo"):
            self.lbl_dn.config(text=T("dn_desligado"))
            return
        if self._dn_periodo == "dia":
            periodo = T("dn_periodo_dia")
        elif self._dn_periodo == "noite":
            periodo = T("dn_periodo_noite")
        else:
            periodo = T("dn_periodo_indefinido")
        self.lbl_dn.config(text=T("dn_agora", periodo=periodo))

    # ---------- callbacks do controlador (rodam na thread worker) ----------
    def _status_recebido(self, cid, dps):
        self.after(0, lambda: self._aplicar_status(cid, dps))

    def _conexao_mudou(self, ok, msg):
        # so mostra mensagens de conexao bem-sucedida; falhas ficam pro aviso discreto
        if ok and msg:
            self.after(0, lambda: self._status(msg, OK))

    def _online_mudou(self, cid, online):
        self.after(0, lambda: self._set_online(cid, online))

    def _ip_redescoberto(self, cid, novo_ip):
        # vem da worker thread -> volta pra main thread antes de mexer em arquivo/UI
        self.after(0, lambda: self._salvar_ip(cid, novo_ip))

    def _salvar_ip(self, cid, novo_ip):
        """Persiste no dispositivos.json o IP que a worker redescobriu, pra proxima
        abertura ja nascer com o endereco certo."""
        mudou = False
        for l in self.lampadas:
            if l.get("id") == cid and l.get("ip") != novo_ip:
                l["ip"] = novo_ip
                mudou = True
        if mudou:
            try:
                salvar_lampadas(self.lampadas)
            except Exception:
                pass

    def _set_online(self, cid, online):
        """Rastreia online POR LAMPADA (id do emissor). Antes era uma flag global:
        com varias lampadas, trocar de aba ou um blip de rede disparava uma falsa
        transicao offline->online e REAPLICAVA o estado padrao (bug do 'voltou pra 44')."""
        if cid is None:
            return
        anterior = self._online_lamp.get(cid)
        if online:
            self._falhas_online[cid] = 0
            self._online_lamp[cid] = True
            # so reaplica o padrao se a PROPRIA lampada selecionada acabou de voltar
            if anterior is False and cid == self._id_ativo():
                self.after(800, self._ao_ligar_lampada)
        else:
            # exige 2 leituras ruins seguidas p/ marcar offline (filtra blip de 1 poll)
            n = self._falhas_online.get(cid, 0) + 1
            self._falhas_online[cid] = n
            if n >= 2:
                self._online_lamp[cid] = False
        # se o online/offline mudou de fato, repinta o seletor (aba marca '⚠ ' offline)
        if self._online_lamp.get(cid) is not anterior and len(self.lampadas) > 1:
            self._montar_seletor()
        self._atualizar_aviso_online()

    def _atualizar_aviso_online(self):
        """Mostra/esconde o aviso de offline conforme a lampada selecionada E
        reflete isso no botao de power. Sem isto o botao continuava mostrando
        'LIGADA' numa lampada que nao responde -- era o engano do 'aparece
        ligada mas nao esta' (lampada caiu da Wi-Fi / fora da rede)."""
        if self._online_lamp.get(self._id_ativo()) is False:
            self.lbl_aviso.config(text=T("aviso_offline"))
            self.lbl_aviso.pack(fill="x", pady=(8, 0))
            # botao nao afirma ligada/desligada: vira "SEM CONEXAO" em cinza
            self.btn_power.set_text(T("btn_offline"))
            self.btn_power.set_colors(OFF, OFF_HOVER, OFF_ACTIVE)
        else:
            self.lbl_aviso.pack_forget()
            # de volta online: botao volta a refletir o estado real conhecido
            self._refletir_power(bool(self.var_power.get()))

    def _ao_ligar_lampada(self):
        """Quando a lampada volta do offline (interruptor religado): aplica o
        perfil dia/noite, se ativo, ou o estado padrao (se configurado)."""
        if not self.controladores:
            return
        if (self.prefs.get("dia_noite") or {}).get("ativo"):
            self._dn_periodo = None
            self._dn_avaliar()
        elif self.prefs.get("aplicar_ao_abrir") and self.prefs.get("padrao"):
            self._aplicar_estado(self.prefs["padrao"], T("status_padrao_aplicado"))

    def _poll_status(self):
        if self.controladores:
            self.ctrl.pedir_status()
        self.after(7000, self._poll_status)

    def _aplicar_status(self, cid, dps):
        if cid != self._id_ativo():
            return   # status de outra lampada (corrida ao trocar de aba): ignora
        if time.monotonic() < self._mute_ate:
            return   # acao recente do usuario: nao deixa o poll sobrescrever a UI
        self._sincronizando = True
        try:
            if DP_POWER in dps:
                lig = bool(dps[DP_POWER])
                self.var_power.set(lig)
                self._refletir_power(lig)
            modo = self.var_modo.get()   # se o status nao trouxer o modo, mantem o atual
            if DP_MODE in dps:
                modo = "colour" if dps[DP_MODE] == "colour" else "white"
                self.var_modo.set(modo)
                self._set_modo_ui(modo)
            if modo == "colour":
                # em cor, brilho/saturacao/matiz vem do DP_COLOUR (HSV) -- NAO do
                # DP_BRIGHT, que guarda o brilho do modo branco e nao acompanha a cor
                # (era o bug do slider mostrar 45% com a luz noutra intensidade).
                if dps.get(DP_COLOUR):
                    h, s, v = parse_hsv_componentes(dps[DP_COLOUR])
                    self._cor_h = h
                    vp, sp = max(1, round(v * 100)), round(s * 100)
                    cur_b = int(self.var_brilho.get())
                    # em cor o fio nao desce abaixo de ~5%; se o usuario deixou o
                    # slider no fundo (1-5%), nao "puxe" para 5 sozinho (evita o salto)
                    if abs(vp - cur_b) > 1 and not (vp <= 5 and cur_b <= 5):
                        self.var_brilho.set(vp)
                        self.lbl_brilho.config(text=T("lbl_brilho", pct=vp))
                    if abs(sp - int(self.var_sat.get())) > 1:
                        self.var_sat.set(sp)
                    self.lbl_sat.config(
                        text=T("lbl_saturacao", pct=int(self.var_sat.get())))
                    rgb = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, s, v))
                    self.swatch.set(rgb)
                    if self.anel:
                        self.anel.set_hue(h)
                        self.anel.set_cor_central(rgb)
            else:
                if DP_BRIGHT in dps:
                    pct = brilho_para_pct(dps[DP_BRIGHT])
                    # zona morta de 1%: ignora o ±1 de arredondamento ida-e-volta
                    if abs(pct - int(self.var_brilho.get())) > 1:
                        self.var_brilho.set(pct)
                        self.lbl_brilho.config(text=T("lbl_brilho", pct=pct))
                if DP_TEMP in dps:
                    pct = round(int(dps[DP_TEMP]) / 1000 * 100)
                    if abs(pct - int(self.var_temp.get())) > 1:
                        self.var_temp.set(pct)
                        self.lbl_temp.config(text=T("lbl_temperatura", pct=pct))
                self._atualizar_swatch_branco()
            self._atualizar_visibilidade_modo()
        finally:
            self._sincronizando = False

    # ---------- instancia unica ----------
    def _iniciar_instancia_unica(self):
        """Cria o evento nomeado e uma thread que fica esperando o sinal de uma
        segunda instancia; quando recebe, traz esta janela para frente."""
        if os.name != "nt":
            return
        try:
            k = _config_k32()
            # evento auto-reset (volta sozinho para "nao sinalizado" apos liberar)
            self._evt_mostrar = k.CreateEventW(None, False, False, _NOME_EVENTO)
            if not self._evt_mostrar:
                return

            def _esperar():
                INFINITE = 0xFFFFFFFF
                WAIT_OBJECT_0 = 0
                while True:
                    if k.WaitForSingleObject(self._evt_mostrar, INFINITE) == WAIT_OBJECT_0:
                        # volta para a thread da UI para mexer na janela com seguranca
                        self.after(0, self._mostrar_janela)
                    else:
                        break

            threading.Thread(target=_esperar, daemon=True).start()
        except Exception:
            pass

    def _mostrar_janela(self):
        """Restaura a janela (mesmo vinda da bandeja) e a traz para o topo."""
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(250, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    # ---------- bandeja do sistema / fechar ----------
    def _criar_tray(self):
        img = Image.open(ICONE)
        menu = pystray.Menu(
            pystray.MenuItem(T("tray_mostrar"), lambda i, it: self.after(0, self.deiconify), default=True),
            pystray.MenuItem(T("tray_ligar_desligar"), lambda i, it: self.after(0, self._toggle_power)),
            pystray.MenuItem(T("tray_sair"), lambda i, it: self.after(0, self._sair)),
        )
        return pystray.Icon("ews410", img, T("tray_tooltip"), menu)

    def _salvar_pos(self):
        try:
            self.prefs["janela_pos"] = f"+{self.winfo_x()}+{self.winfo_y()}"
            salvar_prefs(self.prefs)
        except Exception:
            pass

    def _iniciar_tray(self):
        """Cria o icone da bandeja (fica sempre presente enquanto o app roda)."""
        if not TRAY_OK or self._tray_ativo:
            return
        try:
            self._tray = self._criar_tray()
            self._tray_ativo = True
            threading.Thread(target=self._tray.run, daemon=True).start()
        except Exception:
            pass

    def _fechar(self):
        # fechar a janela apenas esconde para a bandeja (nao encerra)
        self._salvar_pos()
        if TRAY_OK:
            self._iniciar_tray()
            self.withdraw()
        else:
            self._sair()

    def _sair(self):
        self._salvar_pos()
        self._ambiente_ativo = False
        try:
            self.hotkeys.parar()
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
        for c in self.controladores:
            try:
                c.encerrar()
            except Exception:
                pass
        self.destroy()


class ConfigWindow(tk.Toplevel):
    """Janela para adicionar / editar / remover lampadas (sem mexer no JSON)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(T("titulo_config"))
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        self.lampadas = [dict(l) for l in carregar_lampadas()]  # copia editavel

        topo = tk.Frame(self, bg=BG)
        topo.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(topo, text=T("cfg_lampadas_configuradas"), bg=BG, fg=FG,
                 font=("Segoe UI Semibold", 13)).pack(side="left")
        # seletor de idioma (PT / EN): so salva e pede reinicio (nao aplica ao vivo)
        idioma_fr = tk.Frame(topo, bg=BG)
        idioma_fr.pack(side="right")
        tk.Label(idioma_fr, text=T("idioma_label"), bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 6))
        self.var_idioma = tk.StringVar(value=self.app.prefs.get("idioma", "pt"))
        om = tk.OptionMenu(idioma_fr, self.var_idioma, "pt", "en",
                           command=self._trocar_idioma)
        om.config(bg=CARD2, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
                  relief="flat", highlightthickness=0, bd=0, font=("Segoe UI", 9), width=4)
        om["menu"].config(bg=CARD2, fg=FG, activebackground=ACCENT, activeforeground="white")
        om.pack(side="left")
        self.lista = tk.Frame(self, bg=BG)
        self.lista.pack(fill="x", padx=14)
        acoes = tk.Frame(self, bg=BG)
        acoes.pack(fill="x", padx=14, pady=12)
        RoundedButton(acoes, text=T("cfg_btn_adicionar"), width=110, height=30, radius=10, fill=ACCENT,
                      hover=ACCENT_HOVER, active=ACCENT_ACTIVE, fg="white",
                      command=lambda: self._form()).pack(side="left", padx=(0, 6))
        RoundedButton(acoes, text=T("cfg_btn_buscar"), width=130, height=30, radius=10,
                      command=self._buscar).pack(side="left")
        RoundedButton(acoes, text=T("cfg_btn_fechar"), width=90, height=30, radius=10,
                      command=self.destroy).pack(side="right")
        self._render_lista()

    def _trocar_idioma(self, novo):
        """Salva o idioma escolhido e avisa para reiniciar (nao aplica ao vivo)."""
        self.app.prefs["idioma"] = novo
        salvar_prefs(self.app.prefs)
        messagebox.showinfo(T("msg_idioma_titulo"), T("msg_idioma_corpo"), parent=self)

    def _render_lista(self):
        for w in self.lista.winfo_children():
            w.destroy()
        if not self.lampadas:
            tk.Label(self.lista, text=T("cfg_lista_vazia"),
                     bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=4)
            return
        for i, l in enumerate(self.lampadas):
            row = tk.Frame(self.lista, bg=CARD)
            row.pack(fill="x", pady=3)
            inner = tk.Frame(row, bg=CARD)
            inner.pack(fill="x", padx=10, pady=8)
            tk.Label(inner, text=T("cfg_linha_lampada",
                                   nome=l.get('name', T("cfg_sem_nome")),
                                   ip=l.get('ip', T("cfg_ip_desconhecido"))),
                     bg=CARD, fg=FG, font=("Segoe UI", 10)).pack(side="left")
            RoundedButton(inner, text=T("fav_botao_excluir"), width=30, height=26, radius=8, fill=STOP,
                          hover=STOP_HOVER, active=STOP_HOVER,
                          command=lambda x=i: self._remover(x)).pack(side="right")
            RoundedButton(inner, text=T("cfg_btn_editar"), width=70, height=26, radius=8,
                          command=lambda x=i: self._form(x)).pack(side="right", padx=(0, 6))

    def _form(self, idx=None, base=None):
        origem = self.lampadas[idx] if idx is not None else (base or {})
        win = tk.Toplevel(self)
        win.title(T("titulo_editar_lampada") if idx is not None else T("nova_lampada"))
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self)
        campos = [(T("form_campo_nome"), "name"), (T("form_campo_id"), "id"),
                  (T("form_campo_ip"), "ip"), (T("form_campo_key"), "key"),
                  (T("form_campo_versao"), "version")]
        ents = {}
        for rotulo, chave in campos:
            fr = tk.Frame(win, bg=BG)
            fr.pack(fill="x", padx=14, pady=4)
            tk.Label(fr, text=rotulo, bg=BG, fg=MUTED, width=22, anchor="w",
                     font=("Segoe UI", 9)).pack(side="left")
            e = tk.Entry(fr, width=32, bg=CARD2, fg=FG, insertbackground=FG, relief="flat",
                         font=("Segoe UI", 10))
            padrao = origem.get(chave, "3.5" if chave == "version" else "")
            e.insert(0, str(padrao))
            e.pack(side="left", ipady=3)
            ents[chave] = e
        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=14, pady=12)

        def salvar():
            novo = {k: ents[k].get().strip() for _, k in campos}
            if not (novo["id"] and novo["ip"] and novo["key"]):
                messagebox.showwarning(T("msg_campos_obrigatorios_titulo"),
                                       T("msg_campos_obrigatorios_corpo"), parent=win)
                return
            if not novo.get("name"):
                novo["name"] = T("lampada_padrao")
            if not novo.get("version"):
                novo["version"] = "3.5"
            if idx is not None:
                self.lampadas[idx] = {**self.lampadas[idx], **novo}
            else:
                self.lampadas.append(novo)
            self._salvar_e_atualizar()
            win.destroy()

        RoundedButton(bar, text=T("form_btn_salvar"), width=100, height=30, radius=10, fill=ACCENT,
                      hover=ACCENT_HOVER, active=ACCENT_ACTIVE, fg="white",
                      command=salvar).pack(side="left")
        RoundedButton(bar, text=T("btn_cancelar"), width=100, height=30, radius=10,
                      command=win.destroy).pack(side="right")

    def _remover(self, idx):
        if 0 <= idx < len(self.lampadas):
            nome = self.lampadas[idx].get("name", T("remover_lampada_padrao"))
            if messagebox.askyesno(T("msg_remover_titulo"),
                                   T("msg_remover_corpo", nome=nome), parent=self):
                self.lampadas.pop(idx)
                self._salvar_e_atualizar()

    def _buscar(self):
        # o scan demora ~12s; roda numa thread pra nao congelar a janela
        self.config(cursor="watch")
        self.title(T("titulo_config_buscando"))

        def trabalho():
            try:
                achados = tinytuya.deviceScan(False, 12)
            except Exception:
                achados = {}
            self.after(0, lambda: self._buscar_concluido(achados))

        threading.Thread(target=trabalho, daemon=True).start()

    def _buscar_concluido(self, achados):
        if not self.winfo_exists():
            return
        self.config(cursor="")
        self.title(T("titulo_config"))
        ja = {l.get("id") for l in self.lampadas}
        novos = [v for v in achados.values() if (v.get("gwId") or v.get("id")) not in ja]
        if not novos:
            messagebox.showinfo(T("msg_buscar_titulo"),
                                T("msg_buscar_corpo"), parent=self)
            return
        v = novos[0]
        self._form(base={"id": v.get("gwId") or v.get("id"), "ip": v.get("ip", ""),
                         "version": str(v.get("version", "3.5")), "name": T("nova_lampada")})

    def _salvar_e_atualizar(self):
        salvar_lampadas(self.lampadas)
        self._render_lista()
        self.app.recarregar_lampadas()


class DiaNoiteWindow(tk.Toplevel):
    """Configura os perfis de dia/noite (favoritos), horarios e a rampa noturna."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(T("titulo_dia_noite"))
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        cfg = dict(app.prefs.get("dia_noite") or {})
        favs = [f.get("nome", T("dn_fav_desconhecido")) for f in app.prefs.get("favoritos", [])]

        if not favs:
            tk.Label(self, text=T("dn_sem_favoritos"),
                     bg=BG, fg=AMBER, font=("Segoe UI", 10), justify="left").pack(
                padx=18, pady=18)
            RoundedButton(self, text=T("dn_btn_fechar"), width=90, height=30, radius=10,
                          command=self.destroy).pack(pady=(0, 16))
            return

        def na_lista(v, padrao):
            return v if v in favs else padrao

        self.var_dfav = tk.StringVar(value=na_lista(cfg.get("dia_fav"), favs[0]))
        self.var_nfav = tk.StringVar(value=na_lista(cfg.get("noite_fav"), favs[-1]))
        self.e_dh = self._linha(T("dn_linha_dia"),
                                self.var_dfav, favs, cfg.get("dia_hora", "07:00"))
        self.e_nh = self._linha(T("dn_linha_noite"),
                                self.var_nfav, favs, cfg.get("noite_hora", "18:00"))

        fr = tk.Frame(self, bg=BG)
        fr.pack(fill="x", padx=16, pady=(12, 2))
        tk.Label(fr, text=T("dn_rampa_inicio"), bg=BG, fg=FG,
                 font=("Segoe UI", 9)).pack(side="left")
        self.e_rampa = self._entry(fr, str(cfg.get("rampa_min", 120)), 5)
        tk.Label(fr, text=T("dn_rampa_ate"), bg=BG, fg=FG, font=("Segoe UI", 9)).pack(
            side="left", padx=(6, 0))
        self.e_min = self._entry(fr, str(cfg.get("brilho_min", 10)), 4)
        tk.Label(fr, text=T("dn_rampa_brilho"), bg=BG, fg=FG, font=("Segoe UI", 9)).pack(
            side="left", padx=(6, 0))
        tk.Label(self, text=T("dn_rampa_explicacao"),
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), justify="left").pack(
            anchor="w", padx=16, pady=(0, 4))

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=14)
        RoundedButton(bar, text=T("dn_btn_salvar_ativar"), width=130, height=30, radius=10, fill=ACCENT,
                      hover=ACCENT_HOVER, active=ACCENT_ACTIVE, fg="white",
                      command=self._salvar).pack(side="left")
        RoundedButton(bar, text=T("btn_cancelar"), width=100, height=30, radius=10,
                      command=self.destroy).pack(side="right")

    def _entry(self, parent, valor, w):
        e = tk.Entry(parent, width=w, bg=CARD2, fg=FG, insertbackground=FG, relief="flat",
                     justify="center", font=("Segoe UI", 10))
        e.insert(0, valor)
        e.pack(side="left", ipady=2, padx=(6, 0))
        return e

    def _linha(self, rotulo, var, favs, hora):
        tk.Label(self, text=rotulo, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(
            anchor="w", padx=16, pady=(12, 2))
        fr = tk.Frame(self, bg=BG)
        fr.pack(fill="x", padx=16)
        om = tk.OptionMenu(fr, var, *favs)
        om.config(bg=CARD2, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
                  relief="flat", highlightthickness=0, bd=0, font=("Segoe UI", 9), width=16)
        om["menu"].config(bg=CARD2, fg=FG, activebackground=ACCENT, activeforeground="white")
        om.pack(side="left")
        return self._entry(fr, hora, 7)

    def _salvar(self):
        cfg = self.app.prefs.setdefault("dia_noite", {})
        cfg["dia_fav"] = self.var_dfav.get()
        cfg["noite_fav"] = self.var_nfav.get()
        dh = self.e_dh.get().strip()
        nh = self.e_nh.get().strip()
        # so aceita HH:MM valido; senao mantem o padrao (evita "00:00" silencioso)
        cfg["dia_hora"] = dh if self.app._hhmm(dh) is not None else "07:00"
        cfg["noite_hora"] = nh if self.app._hhmm(nh) is not None else "18:00"
        try:
            cfg["rampa_min"] = max(1, int(self.e_rampa.get()))
        except ValueError:
            cfg["rampa_min"] = 120
        try:
            cfg["brilho_min"] = max(1, min(100, int(self.e_min.get())))
        except ValueError:
            cfg["brilho_min"] = 10
        cfg["ativo"] = True
        salvar_prefs(self.app.prefs)
        self.app._dn_periodo = None
        self.app._refletir_dia_noite()
        self.app._dn_avaliar()
        self.destroy()


class AtalhosWindow(tk.Toplevel):
    """Configura atalhos globais (combinacoes de teclas que funcionam em todo o Windows)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(T("titulo_atalhos"))
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        if not HOTKEYS_OK:
            tk.Label(self, text=T("atalhos_so_windows"),
                     bg=BG, fg=AMBER, font=("Segoe UI", 10)).pack(padx=18, pady=18)
            RoundedButton(self, text=T("atalhos_btn_fechar"), width=90, height=30, radius=10,
                          command=self.destroy).pack(pady=(0, 16))
            return
        tk.Label(self, text=T("atalhos_explicacao"),
                 bg=BG, fg=MUTED, font=("Segoe UI", 9), justify="left").pack(
            anchor="w", padx=16, pady=(14, 8))
        self.widgets = {}
        cfgs = app.prefs.get("atalhos") or {}
        for acao, rotulo in ACOES_ATALHO:
            self._linha(acao, rotulo, cfgs.get(acao, {}))
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=16, pady=14)
        RoundedButton(bar, text=T("atalhos_btn_salvar"), width=100, height=30, radius=10, fill=ACCENT,
                      hover=ACCENT_HOVER, active=ACCENT_ACTIVE, fg="white",
                      command=self._salvar).pack(side="left")
        RoundedButton(bar, text=T("btn_cancelar"), width=100, height=30, radius=10,
                      command=self.destroy).pack(side="right")

    def _check(self, parent, texto, valor):
        v = tk.BooleanVar(value=valor)
        tk.Checkbutton(parent, text=texto, variable=v, bg=BG, fg=FG, selectcolor=CARD2,
                       activebackground=BG, activeforeground=FG, font=("Segoe UI", 8),
                       highlightthickness=0, bd=0).pack(side="left")
        return v

    def _linha(self, acao, rotulo, a):
        fr = tk.Frame(self, bg=BG)
        fr.pack(fill="x", padx=16, pady=3)
        tk.Label(fr, text=T(rotulo), bg=BG, fg=FG, width=18, anchor="w",
                 font=("Segoe UI", 9)).pack(side="left")
        v_ctrl = self._check(fr, T("atalhos_chk_ctrl"), a.get("ctrl", True))
        v_alt = self._check(fr, T("atalhos_chk_alt"), a.get("alt", True))
        v_shift = self._check(fr, T("atalhos_chk_shift"), a.get("shift", False))
        v_win = self._check(fr, T("atalhos_chk_win"), a.get("win", False))
        v_key = tk.StringVar(value=a.get("key", "L"))
        om = tk.OptionMenu(fr, v_key, *TECLAS_ATALHO)
        om.config(bg=CARD2, fg=FG, activebackground=BTN_HOVER, activeforeground=FG,
                  relief="flat", highlightthickness=0, bd=0, font=("Segoe UI", 9), width=4)
        om["menu"].config(bg=CARD2, fg=FG, activebackground=ACCENT, activeforeground="white")
        om.pack(side="left", padx=(8, 8))
        v_ativo = self._check(fr, T("atalhos_chk_ativo"), a.get("ativo", False))
        self.widgets[acao] = (v_ctrl, v_alt, v_shift, v_win, v_key, v_ativo)

    def _salvar(self):
        cfgs = self.app.prefs.setdefault("atalhos", {})
        for acao, (vc, va, vs, vw, vk, vat) in self.widgets.items():
            cfgs[acao] = {"ctrl": vc.get(), "alt": va.get(), "shift": vs.get(),
                          "win": vw.get(), "key": vk.get(), "ativo": vat.get()}
        salvar_prefs(self.app.prefs)
        self.app._aplicar_atalhos()
        self.destroy()


# ---------- instancia unica (Windows) ----------
# Garante que so exista UM processo do app. A 2a instancia detecta a 1a via um
# "mutex nomeado" (uma trava com nome, compartilhada entre processos) e, em vez
# de abrir outra janela, sinaliza a 1a para aparecer (caso esteja na bandeja).
_NOME_MUTEX = "joao.controlador.lampada.ews410.mutex"
_NOME_EVENTO = "joao.controlador.lampada.ews410.evento_mostrar"
_mutex_instancia = None   # mantem o handle do mutex vivo enquanto o app roda


def _config_k32():
    """Carrega o kernel32 e declara os tipos das funcoes usadas. Em Windows 64
    bits isso e' ESSENCIAL: sem definir restype=HANDLE, o ctypes assume int de
    32 bits e trunca os handles de 64 bits -> tudo falha sem dar erro."""
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateMutexW.restype = wintypes.HANDLE
    k.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateEventW.restype = wintypes.HANDLE
    k.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k.OpenEventW.restype = wintypes.HANDLE
    k.SetEvent.argtypes = [wintypes.HANDLE]
    k.SetEvent.restype = wintypes.BOOL
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.WaitForSingleObject.restype = wintypes.DWORD
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.CloseHandle.restype = wintypes.BOOL
    return k


def _ja_existe_instancia():
    """Retorna True se ja' ha' outra instancia rodando (e nesse caso sinaliza a
    instancia existente para trazer a janela a' frente). Fora do Windows nao
    aplica trava (retorna False = pode abrir)."""
    if os.name != "nt":
        return False
    global _mutex_instancia
    try:
        k = _config_k32()
        ERROR_ALREADY_EXISTS = 183
        # CreateMutexW cria a trava se nao existir; se ja' existir, devolve um
        # handle para a mesma trava e marca ERROR_ALREADY_EXISTS.
        _mutex_instancia = k.CreateMutexW(None, False, _NOME_MUTEX)
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            EVENT_MODIFY_STATE = 0x0002
            h = k.OpenEventW(EVENT_MODIFY_STATE, False, _NOME_EVENTO)
            if h:
                k.SetEvent(h)        # acorda a 1a instancia -> ela aparece
                k.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def _definir_appid():
    """No Windows, define um AppUserModelID proprio para a barra de tarefas usar
    o icone da janela (e nao o do Python)."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "joao.controlador.lampada.ews410")
    except Exception:
        pass


def main():
    # instancia unica: se ja' ha' uma rodando, ela e' trazida a' frente e saimos
    if _ja_existe_instancia():
        return
    _definir_appid()
    app = App()
    # "--tray": inicia direto minimizado na bandeja (usado no autostart do Windows)
    if "--tray" in sys.argv and TRAY_OK and app.lampadas:
        app.after(150, app._fechar)
    app.mainloop()


if __name__ == "__main__":
    main()
