# CLAUDE.md

Orientações para o Claude Code (claude.ai/code) ao trabalhar neste repositório.

## O que é

App de desktop (Windows-first) para controlar lâmpadas Wi-Fi Tuya **100% pela LAN**, via
`tinytuya` — sem nuvem, sem app do fabricante, sem internet após o setup inicial.
UI em Tkinter com tema escuro e widgets desenhados à mão sobre `tk.Canvas`.
Testado numa Intelbras EWS 410 (Izy Smart); funciona com a maioria das lâmpadas Tuya tipo B.

A **UI é bilíngue (PT/EN)** via `i18n.py`; os **identificadores do código são em português**
(o projeto cresceu PT-first). Trocar idioma na UI aplica ao **reiniciar**.

## Comandos

```powershell
# Ambiente
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# Rodar (sem console / com console para debug)
.venv\Scripts\pythonw.exe controlador_lampada.py     # ou run.bat
.venv\Scripts\python.exe  controlador_lampada.py

# Obter a local key de cada lâmpada (gera/atualiza dispositivos.json)
.venv\Scripts\python.exe obter_chave.py

# Gerar os ícones (icon.png / icon.ico)
.venv\Scripts\python.exe gerar_icone.py

# Build do .exe standalone (resultado em dist/)
.venv\Scripts\python.exe -m pip install pyinstaller==6.20.0
.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --onefile `
  --name "Tuya Bulb Controller" --icon icon.ico `
  --add-data "icon.png;." --add-data "icon.ico;." controlador_lampada.py
```

Não há testes nem lint — é um único script (`controlador_lampada.py`, ~2200 linhas) mais
`i18n.py` e utilitários. O `.exe` oficial é montado pelo **GitHub Actions**
(`.github/workflows/release.yml`) ao dar push numa tag `v*`, com atestado de proveniência
assinado. O `i18n.py` é importado estaticamente, então o PyInstaller o empacota sozinho
(não precisa `--add-data`).

Rebuild do `.exe`: feche o `.exe` em execução antes (o arquivo onefile fica travado).

## Arquitetura

Toda a aplicação está em `controlador_lampada.py`. As peças que exigem ler vários trechos juntos:

- **Modelo de threads.** Cada lâmpada tem um `Controlador` com uma `queue.Queue` e **uma única
  worker thread** que serializa todo acesso ao socket Tuya. A UI Tkinter roda na main thread e
  nunca toca no socket direto — ela só enfileira comandos (`power`, `brilho`, `temp`, `cor`,
  `func`, `anim`, `status`...). Callbacks vindos da worker (`on_status`, `on_conexao`,
  `on_online`, `on_ip`) voltam à UI sempre via `self.after(0, ...)`. Ao mexer em I/O da lâmpada,
  mantenha esse contrato: nada de chamadas tinytuya fora da worker. **`on_status`/`on_online`
  carregam o `id` da lâmpada emissora** (1º argumento): a UI roteia por esse id para não pintar o
  estado de uma lâmpada nos controles de outra durante uma troca de aba (corrida do `after`).

- **Estado por lâmpada (id).** Vários estados são rastreados por `id` da lâmpada, não globalmente:
  `_cenas_ativas` (cena destacada), `_online_lamp`/`_falhas_online` (online + debounce de 2 falhas
  para filtrar blip de rede). Usar uma flag **global** aqui foi o bug do "voltou pra 44" — uma
  falsa transição offline→online reaplicava o estado padrão.

- **Disponibilidade, reconexão e redescoberta de IP (a parte sensível).** `on_online`/`_set_online`
  detectam a lâmpada caindo (desligada na parede) e voltando. Quando a worker vê a lâmpada
  indisponível (status sem dados OU exceção), ela faz duas coisas, **nesta ordem**:
  1. `_forcar_reconexao()` — fecha o socket e zera `self.bulb`. O socket do tinytuya é
     **persistente** (`set_socketPersistent(True)`); sem isso ele fica preso num socket morto e
     **nunca volta**, mesmo depois da lâmpada religar (reabrir o app não resolvia).
  2. `_redescobrir_ip()` — faz `tinytuya.find_device(dev_id=...)` por broadcast na LAN (cooldown de
     15s; `Controlador._scan_lock` serializa entre lâmpadas). Se a lâmpada aparecer **noutro IP**
     (o DHCP costuma dar outro endereço quando ela fica um tempo desligada), atualiza `cfg["ip"]`,
     reconecta e chama `on_ip` → `App._salvar_ip` persiste no `dispositivos.json`. É a correção do
     "fica offline pra sempre mesmo ligada". `cfg` é o **mesmo dict** de `App.lampadas`.

  Quando a lâmpada **volta** online, `_ao_ligar_lampada` aplica o perfil dia/noite (se ativo) ou o
  estado padrão (se `aplicar_ao_abrir`). O padrão **não** é aplicado na abertura do app — só nessa
  transição offline→online.

- **Conversão de brilho (gotcha — não "consertar" de volta).** O tinytuya ESCREVE brilho como
  `value_max * pct // 100` (escala 0..1000, sem offset). Logo a LEITURA tem que ser
  `round(raw / 1000 * 100)` — é o que `brilho_para_pct()` faz. A fórmula `(raw-10)/990*100`
  parecia certa (faixa física 10..1000), mas não casava com a escrita e fazia 45% voltar como 44%
  a cada round-trip.

- **Cenas em movimento** são geradores Python (`cena_arcoiris`/`cena_vela`/`cena_respirar`/
  `cena_sensual`/`cena_aurora`/`cena_festa`) que dão `yield` no delay até o próximo quadro. A
  worker, quando a fila está vazia, usa esse delay como timeout do `queue.get` e avança um quadro
  por vez. Qualquer comando manual (exceto `status`) cancela a cena. Todas têm a assinatura
  `(b, fase0=0.0, escala_v=1.0)`: `fase0` defasa cada lâmpada quando rodam em **grupo**; `escala_v`
  enfraquece a lâmpada (ex.: teto, via `escala_brilho_cfg`).

- **Cenas: individual × grupo.** A lista única `CENAS_MOV` serve aos dois casos. `_alvos_cena()`
  decide os alvos: só a lâmpada ativa, ou **todas** quando "Aplicar em todas as lâmpadas"
  (`_grupo_cenas`) está ligado — esse botão só aparece com 2+ lâmpadas.

- **DPS (Data Points).** O protocolo Tuya expõe estado por números: `DP_POWER="20"`,
  `DP_MODE="21"`, `DP_BRIGHT="22"`, `DP_TEMP="23"`, `DP_COLOUR="24"`. Mapeamento de lâmpada
  colorida "tipo B". Brilho/temperatura no fio vão de 10..1000 / 0..1000; a UI trabalha em
  percentual e converte nas duas pontas.

- **Sincronização UI ↔ lâmpada (a parte sutil).** Um poll periódico (`_poll_status`, ~7s) lê o
  estado real e reflete na UI. Para o poll não "desfazer" uma ação recém-feita há dois mecanismos:
  `_marcar_acao()` seta `_mute_ate` (ignora polls por ~3s) e a flag `_sincronizando` evita disparar
  comandos enquanto a UI é atualizada a partir do status. Sliders usam debounce
  (`_debounce_brilho`/`_debounce_temp`, ~220ms). Há zonas mortas de 1% para absorver o jitter de
  arredondamento do round-trip. Mexer num desses sem entender os outros costuma criar loops de
  feedback (UI piscando / valores revertendo).

- **Color handling.** A lâmpada não mostra pastel/branco em modo cor: `cor_exibivel()` empurra
  cores quase dessaturadas para o modo "white" e reforça a saturação das demais. `parse_hsv_hex()`
  / `parse_hsv_componentes()` leem o hex Tuya `HHHHSSSSVVVV` (RGB / componentes H,S,V). Em modo
  cor a UI trabalha em H/S/V (anel `AnelMatiz` gerado com PIL/`ImageTk` define o H, sliders definem
  V e S) e **lê brilho/saturação do `DP_COLOUR`, NÃO do `DP_BRIGHT`** (este guarda o brilho do modo
  branco). O anel é opcional: `ANEL_OK` (`from PIL import ImageTk`). O **modo ambiente (ambilight)**
  roda numa thread própria (`_loop_ambiente`), amostra a tela a ~3fps via `ImageGrab`, e calcula a
  cor dominante por **média circular de hue ponderada por saturação×valor**.

- **Internacionalização (`i18n.py`).** `TEXTOS = {"pt": {...}, "en": {...}}` (mesmas chaves nos dois
  idiomas); `definir_idioma(idioma)` é chamado no `__init__` após carregar as prefs; `T(chave, **kw)`
  resolve o texto com fallback pro PT e pra própria chave (nunca quebra a UI). IDs estáveis: cenas,
  presets e ações de atalho guardam a **chave i18n** como identificador (não o texto traduzido), e
  o texto exibido é `T(chave)`. Trocar idioma salva `prefs["idioma"]` e pede reinício (não remonta
  a UI ao vivo).

- **Específicos de Windows** (degradam graciosamente fora do Windows): bandeja (`pystray`),
  hotkeys globais via `RegisterHotKey` numa thread dedicada (`HotkeyManager`), `ImageGrab`,
  AppUserModelID para o ícone na taskbar, e **instância única** via mutex nomeado (a 2ª instância
  sinaliza a 1ª para aparecer em vez de abrir outra janela). `pystray`/`PIL` são opcionais —
  `TRAY_OK` indica se estão disponíveis (no `.exe` vêm embutidos).

## Persistência

Dois arquivos JSON **criados em runtime e não versionados** (estão no `.gitignore`):

- **`dispositivos.json`** — lista de lâmpadas (`id`, `ip`, `key`, `version`, `name`). Contém a
  **local key** (dado sensível), por isso é gitignored e nunca deve ser commitado.
  `dispositivos.json.example` é o template. Gerado/atualizado por `obter_chave.py`; também é
  reescrito em runtime quando a auto-redescoberta corrige um IP.
- **`preferencias.json`** — favoritos, estado padrão, dia/noite, atalhos, idioma, posição da janela.

No `.exe` (`sys.frozen`), os JSONs ficam **ao lado do executável** e os ícones vêm de
`sys._MEIPASS`. Rodando do código-fonte, `salvar_lampadas`/`obter_chave.py` **espelham** o
`dispositivos.json` para `dist\` (se a pasta existir), para manter o `.exe` em sincronia.

## Convenções

- **Identificadores, strings de código e comentários em português** (sem acentos nos
  identificadores). A **UI** é bilíngue via `i18n.py` — textos novos da UI vão como chave no
  `i18n.py` (PT + EN) e são usados via `T(...)`, nunca hardcoded.
- Paleta de cores e fontes são constantes no topo do arquivo (`BG`, `CARD`, `ACCENT`, ...).
- Widgets custom (`RoundedButton`, `Slider`, `ColorDot`, `Swatch`) são `tk.Canvas` desenhados à
  mão; reuse-os em vez de widgets nativos para manter o visual consistente.
- Versões de dependências são **fixas** (`==`) em `requirements.txt` — mantenha pinado.
