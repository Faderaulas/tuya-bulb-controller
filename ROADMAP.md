# Roadmap — Controle da Lâmpada EWS 410

Histórico do que foi feito e o que está planejado. Atualizado conforme o projeto evolui.

---

## ✅ Concluído

### Base / conexão
- [x] Ambiente Python isolado (`.venv`) com `tinytuya` (instalada seguindo o protocolo de segurança: versões fixas, quarentena de 7 dias, só wheels).
- [x] Extração da **local key** via nuvem Tuya (`obter_chave.py`) — credenciais digitadas localmente, nunca no chat.
- [x] Descoberta de IP/versão na rede (scan LAN). Lâmpada: protocolo **3.5**, controle **100% local**.
- [x] Resolvido o vínculo de app: Izy Smart (OEM) não extrai key → caminho via **Smart Life** (nuvem). Documentado nas memórias do projeto.

### Aplicativo (interface)
- [x] Controlador gráfico (Tkinter): liga/desliga, modo branco/cor, brilho, temperatura, seletor de cor + presets.
- [x] **Cenas fixas** (Leitura, Aconchego, Cinema) e **em movimento** (Vela, Arco-íris, Respirar).
- [x] **Estado padrão** ("ligar sempre em X") + opção "aplicar ao abrir".
- [x] **Favoritos**: salvar o setup atual com nome, aplicar e excluir.
- [x] **Timer para desligar** (15/30/60 min + **campo personalizado** + contagem regressiva).
- [x] **Transição suave (fade)** — toggle ON/OFF; brilho/temperatura/cor mudam de forma gradual.
- [x] **Cor exibível** — cores que a lâmpada não consegue mostrar são ajustadas para a mais próxima (saturação reforçada; cores quase brancas viram modo branco).
- [x] **Dia/Noite automático** — favorito de dia e de noite, com horários; à noite a luz faz **rampa de escurecimento gradual** até um brilho mínimo. Tudo configurável pela interface.
- [x] Correção do "bug visual" do menu (o poll periódico voltava o modo após Aplicar) — agora o poll é ignorado por alguns segundos após cada ação do usuário.
- [x] **Atalhos globais** — registrar combinações de teclas (Ctrl/Alt/Shift/Win) que funcionam em todo o Windows, mesmo minimizado (Ligar/Desligar, Mostrar/ocultar, Aplicar padrão, Parar cena). Via API do Windows, sem dependência nova.
- [x] **Modo Ambiente (Ambilight)** — a luz acompanha a cor predominante da tela (~3 fps, leve no PC). Usa o Pillow (captura de tela), sem dependência nova. Extração por **matiz dominante ponderado por saturação** (ignora o branco/cinza da UI; antes a média da tela toda "puxava" o tom).
- [x] **Padrão ao ligar a lâmpada** — o estado padrão agora só é aplicado quando a lâmpada **volta do offline** (interruptor religado), não toda vez que o app abre (que preservava o estado atual).
- [x] Correções de estabilidade de leitura: drenar buffer do socket antes de ler (ecos de `nowait`), brilho direto na rampa dia/noite, e zona morta de 1% no poll.
- [x] Visual moderno: **duas colunas**, botões arredondados com hover/clique, **sliders com contraste**.
- [x] Quadrado de cor reflete o branco quente↔frio.
- [x] **Aviso discreto** quando a lâmpada está offline (sem energia no interruptor).
- [x] **Bandeja do sistema**: fechar a janela minimiza pra bandeja (menu Mostrar / Ligar-Desligar / Sair).
- [x] **Instância única**: abrir o app de novo (duplo-clique/atalho/autostart) traz a janela que já está aberta pra frente (restaura da bandeja) em vez de abrir uma 2ª cópia. Via mutex + evento nomeados do Windows (`ctypes`), sem dependência nova.
- [x] **Lembrar posição** da janela.
- [x] Ícone próprio (janela + barra de tarefas, via AppUserModelID) — atualizado para o ícone "clean" (quadrado arredondado, cantos transparentes).

### Multi-lâmpada + configuração
- [x] Suporte a **várias lâmpadas** (seletor no topo; pronto pra quando a 2ª for adicionada).
- [x] **Configuração pela interface** (botão ⚙ Lâmpadas): adicionar / editar / remover lâmpadas e "Buscar na rede", sem editar JSON na mão.

### Empacotamento
- [x] **`.exe`** standalone (PyInstaller, onefile, ícone embutido) em `dist/`.
- [x] Atalho na área de trabalho + **autostart** ao ligar o PC (inicia na bandeja com `--tray`).
- [x] `obter_chave.py` sincroniza a config com o `dist/` automaticamente.
- [x] Organização da pasta + `README.md`.

### Open source (concluído)
- [x] **Fork em inglês publicado:** [github.com/Faderaulas/tuya-bulb-controller](https://github.com/Faderaulas/tuya-bulb-controller) — público, MIT, assinado Faderaulas, sem credenciais nem menção a Claude.
- [x] Tradução total (código + textos + docs), README com screenshots, LICENSE, `.gitignore`, `requirements.txt`.
- [x] **Release v1.0.0** com `.exe` buildado pelo **GitHub Actions** + **atestação de proveniência assinada** (binário verificável via `gh attestation verify`).
- [x] Correção do "candle/rainbow para após alguns segundos" (era o bug M3 do poll) — confirmado nos testes.

> Não feito (opcional, baixa prioridade): instalador `setup.exe` (Inno Setup) — redundante com a Release.

---

## 💡 Backlog / ideias futuras (não priorizadas)

- [ ] Grupo "Todas as lâmpadas" no seletor (comandar várias de uma vez).
- [ ] **Modo Música:** lâmpada reage ao áudio do PC (precisa de lib de captura de áudio).
- [ ] **Comandos por voz (offline):** reconhecimento de voz local (ex.: **Vosk** + modelo PT-BR ~50MB + captura de microfone) para comandos como "ligar luz", "luz vermelha", "modo cinema". Tudo no PC, sem nuvem.
- [ ] Modo circadiano automático ao longo do dia inteiro (não só dia/noite).
- [ ] Conta-gotas de cor (pegar cor de qualquer ponto da tela / de uma foto).
- [ ] Auto-update do app.

---

## 📝 Notas técnicas

- **Reextrair a local key** (após reparear uma lâmpada): `obter_chave.py` (atualiza `dispositivos.json` e o `dist/`).
- **Recompilar o `.exe`:** comando no `README.md`. ⚠️ Fechar o `.exe` antes (senão trava o arquivo); a pasta `build/` é intermediária e pode ser apagada.
- **Protocolo de segurança ao instalar pacotes** (global, em `~/.claude/CLAUDE.md`): listar versões + quarentena de 7 dias + confirmação antes de instalar. Vale pras dependências de fases futuras (ex.: captura de áudio do Modo Música, Inno Setup).
