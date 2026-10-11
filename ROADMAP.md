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

### Estabilidade e desempenho (11/10/2026)
Revisão geral motivada por "a lâmpada fica ligada um bom tempo até o app conseguir alterar ela".
Detalhes de cada mecanismo no `CLAUDE.md` (seção Arquitetura).

- [x] **Vazamento de threads na redescoberta de IP** — cada lâmpada offline abria uma thread de scan (18s) a cada 15s, todas atrás do mesmo lock. Depois de 2,5 dias com as lâmpadas desligadas na parede o `.exe` tinha **4.694 threads e 906 MB reservados**. Agora há **uma** thread de busca compartilhada, com scans de 5s para todas as lâmpadas (medido: 11–13 threads estáveis).
- [x] **Lâmpada que volta com IP novo** — era achada em ~40s (esperava a vez na fila de scans); agora em ~5s *(simulador)*.
- [x] **Comando perdido em silêncio** — o `tinytuya` devolve um dicionário de erro em vez de exceção, e ninguém olhava. O clique feito enquanto a lâmpada ainda voltava para a rede sumia. Agora a falha é detectada e o comando é **reenviado sozinho** se a lâmpada responder em até 15s.
- [x] **Transição suave + lâmpada offline** — cada degrau do fade esperava o próprio timeout (~30s de fila parada por clique). Agora uma única leitura decide (~3s).
- [x] **Timeout de socket** 5s → 3s e poll de lâmpada offline 5s → 3s.
- [x] **Fila "só o mais recente"** — pedidos repetidos de status/brilho/temperatura/cor são pulados em favor do mais novo. O modo ambiente acumulava quadros atrás de uma lâmpada lenta ("desligar" levava 10,5s → 1,1s *no simulador*).
- [x] **Reafirmação desfazia a própria ação** (regressão de 10/07/2026) — o app anotava como "intenção" o estado *antigo* da interface; segundos depois o favorito, a cena fixa e o estado padrão voltavam sozinhos, e a cena em movimento era cancelada.
- [x] **Rampa noturna não reacende** lâmpada apagada pelo app (mexer no brilho acende a lâmpada). *Não exercitado no simulador.*
- [x] **Cenas em movimento** usam sempre a conexão atual (antes ficavam presas numa conexão antiga depois de uma queda).
- [x] **Comandos de voz removidos** — implementados em 10/07/2026 (Vosk, "ei lâmpada") e nunca usados. Pesavam: o `numpy` reservava ~350 MB só de ser importado e o `.exe` tinha 48,8 MB (**24,6 MB** sem eles; memória reservada ao abrir 411 MB → **48 MB**). O código ficou guardado no branch local `arquivo/comandos-de-voz`.

#### ⏳ Pendente: teste com as lâmpadas reais
Tudo acima foi validado num **simulador de lâmpada** e num teste somente-leitura na rede (as três estavam desligadas na parede). Falta conferir com o hardware:

- [ ] Ligar uma lâmpada no interruptor: o app sai de "SEM CONEXÃO" poucos segundos depois de ela entrar no Wi-Fi?
- [ ] Clicar em algo logo que ela acender, antes de o app reconectar: o comando chega sozinho?
- [ ] Aplicar um favorito e uma cena e esperar ~15s: continuam aplicados (não voltam atrás)?
- [ ] Depois de 1–2 dias aberto: o Gerenciador de Tarefas mostra as threads na casa das dezenas?
- [ ] O IP salvo da **Teto** recusava conexão em 11/10 (parece estar com outro aparelho): ela é redescoberta sozinha ao ligar?

---

## 💡 Backlog / ideias futuras (não priorizadas)

- [ ] Grupo "Todas as lâmpadas" no seletor (comandar várias de uma vez).
- [ ] **Modo Música:** lâmpada reage ao áudio do PC (precisa de lib de captura de áudio).
- ~~**Comandos por voz (offline)**~~ — feito em 10/07/2026 e **removido em 11/10/2026** por não ser usado (ver "Estabilidade e desempenho"). Não reintroduzir sem pedido; o código está no branch `arquivo/comandos-de-voz`.
- [ ] Modo circadiano automático ao longo do dia inteiro (não só dia/noite).
- [ ] Conta-gotas de cor (pegar cor de qualquer ponto da tela / de uma foto).
- [ ] Auto-update do app.

### Achados da revisão de 11/10/2026 (mudam comportamento — decidir antes de fazer)
- [ ] **"Aplicar ao ligar" só vale para a lâmpada da aba selecionada** — as outras voltam do offline sem receber o estado padrão (`_set_online` só chama `_ao_ligar_lampada` quando `cid == _id_ativo()`).
- [ ] **A virada dia/noite acende todas as lâmpadas**, inclusive as apagadas pelo app (`_aplicar_estado(..., todas=True)` sempre liga).
- [ ] **Reservar IP fixo por MAC no roteador** para as três lâmpadas — elimina de vez a troca de IP pelo DHCP (a redescoberta vira só rede de segurança).
- [ ] **Trazer o simulador de lâmpada para o repo como teste** — hoje não há testes; a técnica está descrita no `CLAUDE.md`.

---

## 📝 Notas técnicas

- **Reextrair a local key** (após reparear uma lâmpada): `obter_chave.py` (atualiza `dispositivos.json` e o `dist/`).
- **Recompilar o `.exe`:** comando no `README.md`. ⚠️ Fechar o `.exe` antes (senão trava o arquivo); a pasta `build/` é intermediária e pode ser apagada.
- **O `.venv` deve ter só o que está no `requirements.txt`** (+ PyInstaller). Pacote extra instalado pode ir parar dentro do `.exe` mesmo sem o app usar: com o `numpy` no venv, o PyInstaller o embutia via Pillow (+10 MB).
- **Protocolo de segurança ao instalar pacotes** (global, em `~/.claude/CLAUDE.md`): listar versões + quarentena de 7 dias + confirmação antes de instalar. Vale pras dependências de fases futuras (ex.: captura de áudio do Modo Música, Inno Setup).
