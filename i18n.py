"""
Textos da interface em portugues e ingles (i18n).

Um unico codigo-fonte serve os dois idiomas: a logica do app fica em
controlador_lampada.py e todo texto visivel ao usuario vem daqui, via T("chave").
O idioma e' lido das preferencias na inicializacao (definir_idioma).
"""

IDIOMA = "pt"   # idioma atual; trocado por definir_idioma() na inicializacao

TEXTOS = {
    "pt": {
        # --- presets de cor (PRESETS, linhas 62-71) ---
        "cor_vermelho": "Vermelho",
        "cor_laranja": "Laranja",
        "cor_amarelo": "Amarelo",
        "cor_verde": "Verde",
        "cor_ciano": "Ciano",
        "cor_azul": "Azul",
        "cor_roxo": "Roxo",
        "cor_rosa": "Rosa",

        # --- nomes de cenas fixas (CENAS_FIXAS, linhas 266-270) ---
        "cena_leitura": "Leitura",
        "cena_aconchego": "Aconchego",
        "cena_cinema": "Cinema",

        # --- nomes de cenas em movimento (CENAS_MOV, linhas 274-281) ---
        "cena_vela": "Vela",
        "cena_arcoiris": "Arco-íris",
        "cena_respirar": "Respirar",
        "cena_sensual": "Sensual",
        "cena_aurora": "Aurora",
        "cena_festa": "Festa",

        # --- nomes/rotulos de acoes de atalho (ACOES_ATALHO, linhas 860-865) ---
        "atalho_toggle_power": "Ligar / Desligar",
        "atalho_mostrar": "Mostrar / ocultar janela",
        "atalho_padrao": "Aplicar estado padrão",
        "atalho_parar_cena": "Parar cena",

        # --- nomes default de lampada ---
        "lampada_padrao": "Lâmpada",
        "sem_lampada": "Sem lâmpada",
        "lampada_numerada": "Lâmpada {n}",
        "nova_lampada": "Nova lâmpada",

        # --- titulos de janela ---
        "titulo_app": "Controle de Lâmpadas",
        "titulo_config": "Lâmpadas",
        "titulo_config_buscando": "Lâmpadas — buscando na rede...",
        "titulo_editar_lampada": "Editar lâmpada",
        "titulo_dia_noite": "Dia / Noite automático",
        "titulo_atalhos": "Atalhos globais",
        "tray_tooltip": "Controle EWS 410",

        # --- status (lbl_status) ---
        "status_conectando": "conectando...",
        "status_conectado": "conectado ({ip})",
        "status_nenhuma_lampada_abrindo": "nenhuma lâmpada — abrindo configuração...",
        "status_arraste_reposicionar": "arraste para reposicionar a lâmpada",
        "status_lampada_atual": "lâmpada: {nome}",
        "status_ordem_lampadas": "ordem das lâmpadas atualizada",
        "status_config_atualizada": "configuração atualizada",
        "status_nenhuma_lampada_config": "nenhuma lâmpada configurada",
        "status_cor_muito_clara": "cor muito clara — exibida como branco",
        "status_grupo_cena_n": "grupo: {nome} ({n} lâmpadas)",
        "status_cena": "cena: {nome}",
        "status_cena_movimento": "cena: {nome} (movimento)",
        "status_cenas_paradas": "cenas paradas (todas)",
        "status_cena_parada": "cena parada",
        "status_padrao_salvo": "padrão salvo",
        "status_padrao_aplicado": "padrão aplicado",
        "status_favorito_aplicado": "favorito aplicado",
        "status_arraste_reordenar_favorito": "arraste para reordenar o favorito",
        "status_ordem_favoritos": "ordem dos favoritos atualizada",
        "status_favorito_salvo": "favorito '{nome}' salvo",
        "status_favorito_excluido": "favorito excluído",
        "status_timer_ligado": "timer de {minutos} min ligado",
        "status_desligada_timer": "desligada pelo timer",
        "status_timer_cancelado": "timer cancelado",
        "status_numero_invalido": "digite um número de minutos válido",
        "status_ambiente_desligado": "modo ambiente desligado",
        "status_ambiente_ligado": "modo ambiente ligado",

        # --- labels/botoes da UI principal ---
        "btn_lampadas_engrenagem": "⚙ Lâmpadas",
        "lbl_fixas": "FIXAS",
        "lbl_em_movimento": "EM MOVIMENTO",
        "btn_parar_cena": "Parar cena",
        "card_modo": "MODO",
        "btn_branco": "Branco",
        "btn_cor": "Cor",
        "lbl_brilho": "Brilho — {pct}%",
        "lbl_temperatura": "Temperatura — {pct}%   (quente ↔ frio)",
        "lbl_saturacao": "Saturação — {pct}%   (lavada ↔ viva)",
        "card_cores": "CORES",
        "btn_escolher_cor": "Escolher cor...",
        "titulo_escolher_cor": "Escolher cor",
        "card_dia_noite": "DIA / NOITE (AUTOMÁTICO)",
        "btn_configurar": "Configurar...",
        "card_cenas": "CENAS",
        "card_modo_ambiente": "MODO AMBIENTE (TELA)",
        "desc_modo_ambiente": "a luz acompanha a cor predominante da tela",
        "card_favoritos": "FAVORITOS",
        "btn_salvar_favorito": "+  Salvar atual como favorito",
        "card_timer": "TIMER PARA DESLIGAR",
        "btn_timer_min": "{mins} min",
        "lbl_personalizado": "Personalizado:",
        "lbl_min": "min",
        "btn_ligar": "Ligar",
        "btn_cancelar": "Cancelar",
        "card_estado_padrao": "ESTADO PADRÃO",
        "btn_salvar_atual": "Salvar atual",
        "btn_aplicar": "Aplicar",
        "btn_atualizar_estado": "Atualizar estado",
        "btn_atalhos": "⌨ Atalhos",

        # --- botoes com prefixo on/off (●/○) ---
        "btn_aplicar_ao_ligar": "Aplicar ao ligar a lâmpada",
        "btn_transicao_suave": "Transição suave",
        "btn_aplicar_em_todas": "Aplicar em todas as lâmpadas",
        "btn_automatico": "Automático",
        "btn_modo_ambiente": "Modo Ambiente",

        # --- estados do botao de power ---
        "btn_ligada": "LIGADA",
        "btn_desligada": "DESLIGADA",

        # --- timer/label ---
        "timer_vazio": "—",
        "timer_contagem": "⏱ {m:02d}:{s:02d}",

        # --- dia/noite label ---
        "dn_desligado": "desligado",
        "dn_agora": "agora: {periodo}",
        "dn_periodo_dia": "dia",
        "dn_periodo_noite": "noite",
        "dn_periodo_indefinido": "—",

        # --- aviso offline ---
        "aviso_offline": "⚠  Lâmpada offline — ligue no interruptor para usar",

        # --- favoritos ---
        "fav_nenhum": "(nenhum favorito salvo)",
        "fav_nome_padrao": "favorito",
        "fav_botao_excluir": "✕",

        # --- messageboxes / dialogs ---
        "msg_estado_padrao_titulo": "Estado padrão",
        "msg_estado_padrao_corpo": "Nenhum estado padrão salvo ainda.\nAjuste a luz como quiser e clique em 'Salvar atual'.",
        "dlg_novo_favorito_titulo": "Novo favorito",
        "dlg_novo_favorito_prompt": "Nome do favorito:",
        "msg_excluir_favorito_titulo": "Excluir favorito",
        "msg_excluir_favorito_corpo": "Excluir o favorito '{nome}'?",
        "msg_dia_noite_titulo": "Dia / Noite",
        "msg_dia_noite_corpo": "Configure primeiro: clique em 'Configurar...' e escolha um favorito para o dia e outro para a noite.",
        "msg_modo_ambiente_titulo": "Modo Ambiente",
        "msg_modo_ambiente_corpo": "Captura de tela (Pillow) indisponível nesta versão.",

        # --- bandeja (tray) ---
        "tray_mostrar": "Mostrar",
        "tray_ligar_desligar": "Ligar / Desligar",
        "tray_sair": "Sair",

        # --- ConfigWindow ---
        "cfg_lampadas_configuradas": "Lâmpadas configuradas",
        "cfg_btn_adicionar": "+ Adicionar",
        "cfg_btn_buscar": "Buscar na rede",
        "cfg_btn_fechar": "Fechar",
        "cfg_lista_vazia": "(nenhuma — clique em Adicionar ou Buscar na rede)",
        "cfg_linha_lampada": "{nome}   —   {ip}",
        "cfg_sem_nome": "(sem nome)",
        "cfg_ip_desconhecido": "?",
        "cfg_btn_editar": "Editar",

        # --- formulario de lampada ---
        "form_campo_nome": "Nome",
        "form_campo_id": "ID (Device ID)",
        "form_campo_ip": "IP na rede",
        "form_campo_key": "Local key",
        "form_campo_versao": "Versão (3.3 / 3.4 / 3.5)",
        "form_btn_salvar": "Salvar",
        "msg_campos_obrigatorios_titulo": "Campos obrigatórios",
        "msg_campos_obrigatorios_corpo": "ID, IP e Local key são obrigatórios.",
        "msg_remover_titulo": "Remover",
        "msg_remover_corpo": "Remover '{nome}'?",
        "remover_lampada_padrao": "essa lâmpada",
        "msg_buscar_titulo": "Buscar na rede",
        "msg_buscar_corpo": "Nenhuma lâmpada nova encontrada.\n(As já configuradas não aparecem. A local key precisa ser obtida pelo obter_chave.py.)",

        # --- DiaNoiteWindow ---
        "dn_sem_favoritos": "Salve ao menos um Favorito antes\n(botão '+ Salvar atual como favorito').",
        "dn_btn_fechar": "Fechar",
        "dn_linha_dia": "Dia — favorito e horário de início:",
        "dn_linha_noite": "Noite — favorito e horário de início:",
        "dn_rampa_inicio": "A partir da noite, escurece em",
        "dn_rampa_ate": "min, até",
        "dn_rampa_brilho": "% de brilho",
        "dn_rampa_explicacao": "(no horário da noite a luz aplica o favorito e já começa a\nescurecer aos poucos, chegando ao mínimo ao fim desse tempo)",
        "dn_btn_salvar_ativar": "Salvar e ativar",
        "dn_fav_desconhecido": "?",

        # --- AtalhosWindow ---
        "atalhos_so_windows": "Atalhos globais disponíveis apenas no Windows.",
        "atalhos_btn_fechar": "Fechar",
        "atalhos_explicacao": "Atalhos que funcionam em todo o Windows (mesmo minimizado).\nMarque ao menos um modificador (Ctrl / Alt / Shift / Win).",
        "atalhos_btn_salvar": "Salvar",
        "atalhos_chk_ctrl": "Ctrl",
        "atalhos_chk_alt": "Alt",
        "atalhos_chk_shift": "Shift",
        "atalhos_chk_win": "Win",
        "atalhos_chk_ativo": "Ativo",

        # --- seletor de idioma ---
        "idioma_label": "Idioma:",
        "msg_idioma_titulo": "Idioma",
        "msg_idioma_corpo": "Reinicie o app para aplicar o novo idioma.",
    },
    "en": {
        "cor_vermelho": "Red",
        "cor_laranja": "Orange",
        "cor_amarelo": "Yellow",
        "cor_verde": "Green",
        "cor_ciano": "Cyan",
        "cor_azul": "Blue",
        "cor_roxo": "Purple",
        "cor_rosa": "Pink",

        "cena_leitura": "Reading",
        "cena_aconchego": "Cozy",
        "cena_cinema": "Cinema",

        "cena_vela": "Candle",
        "cena_arcoiris": "Rainbow",
        "cena_respirar": "Breathe",
        "cena_sensual": "Sensual",
        "cena_aurora": "Aurora",
        "cena_festa": "Party",

        "atalho_toggle_power": "Turn On / Off",
        "atalho_mostrar": "Show / hide window",
        "atalho_padrao": "Apply default state",
        "atalho_parar_cena": "Stop scene",

        "lampada_padrao": "Bulb",
        "sem_lampada": "No bulb",
        "lampada_numerada": "Bulb {n}",
        "nova_lampada": "New bulb",

        "titulo_app": "Bulb Control",
        "titulo_config": "Bulbs",
        "titulo_config_buscando": "Bulbs — scanning the network...",
        "titulo_editar_lampada": "Edit bulb",
        "titulo_dia_noite": "Day / Night automatic",
        "titulo_atalhos": "Global shortcuts",
        "tray_tooltip": "EWS 410 Control",

        "status_conectando": "connecting...",
        "status_conectado": "connected ({ip})",
        "status_nenhuma_lampada_abrindo": "no bulb — opening settings...",
        "status_arraste_reposicionar": "drag to reposition the bulb",
        "status_lampada_atual": "bulb: {nome}",
        "status_ordem_lampadas": "bulb order updated",
        "status_config_atualizada": "settings updated",
        "status_nenhuma_lampada_config": "no bulb configured",
        "status_cor_muito_clara": "color too light — shown as white",
        "status_grupo_cena_n": "group: {nome} ({n} bulbs)",
        "status_cena": "scene: {nome}",
        "status_cena_movimento": "scene: {nome} (motion)",
        "status_cenas_paradas": "scenes stopped (all)",
        "status_cena_parada": "scene stopped",
        "status_padrao_salvo": "default saved",
        "status_padrao_aplicado": "default applied",
        "status_favorito_aplicado": "favorite applied",
        "status_arraste_reordenar_favorito": "drag to reorder the favorite",
        "status_ordem_favoritos": "favorites order updated",
        "status_favorito_salvo": "favorite '{nome}' saved",
        "status_favorito_excluido": "favorite deleted",
        "status_timer_ligado": "{minutos} min timer started",
        "status_desligada_timer": "turned off by timer",
        "status_timer_cancelado": "timer canceled",
        "status_numero_invalido": "enter a valid number of minutes",
        "status_ambiente_desligado": "ambient mode off",
        "status_ambiente_ligado": "ambient mode on",

        "btn_lampadas_engrenagem": "⚙ Bulbs",
        "lbl_fixas": "STATIC",
        "lbl_em_movimento": "ANIMATED",
        "btn_parar_cena": "Stop scene",
        "card_modo": "MODE",
        "btn_branco": "White",
        "btn_cor": "Color",
        "lbl_brilho": "Brightness — {pct}%",
        "lbl_temperatura": "Temperature — {pct}%   (warm ↔ cool)",
        "lbl_saturacao": "Saturation — {pct}%   (washed ↔ vivid)",
        "card_cores": "COLORS",
        "btn_escolher_cor": "Pick a color...",
        "titulo_escolher_cor": "Pick a color",
        "card_dia_noite": "DAY / NIGHT (AUTOMATIC)",
        "btn_configurar": "Configure...",
        "card_cenas": "SCENES",
        "card_modo_ambiente": "AMBIENT MODE (SCREEN)",
        "desc_modo_ambiente": "the light follows the dominant color of the screen",
        "card_favoritos": "FAVORITES",
        "btn_salvar_favorito": "+  Save current as favorite",
        "card_timer": "OFF TIMER",
        "btn_timer_min": "{mins} min",
        "lbl_personalizado": "Custom:",
        "lbl_min": "min",
        "btn_ligar": "Start",
        "btn_cancelar": "Cancel",
        "card_estado_padrao": "DEFAULT STATE",
        "btn_salvar_atual": "Save current",
        "btn_aplicar": "Apply",
        "btn_atualizar_estado": "Refresh state",
        "btn_atalhos": "⌨ Shortcuts",

        "btn_aplicar_ao_ligar": "Apply when the bulb turns on",
        "btn_transicao_suave": "Smooth transition",
        "btn_aplicar_em_todas": "Apply to all bulbs",
        "btn_automatico": "Automatic",
        "btn_modo_ambiente": "Ambient Mode",

        "btn_ligada": "ON",
        "btn_desligada": "OFF",

        "timer_vazio": "—",
        "timer_contagem": "⏱ {m:02d}:{s:02d}",

        "dn_desligado": "off",
        "dn_agora": "now: {periodo}",
        "dn_periodo_dia": "day",
        "dn_periodo_noite": "night",
        "dn_periodo_indefinido": "—",

        "aviso_offline": "⚠  Bulb offline — turn it on at the wall switch to use it",

        "fav_nenhum": "(no favorites saved)",
        "fav_nome_padrao": "favorite",
        "fav_botao_excluir": "✕",

        "msg_estado_padrao_titulo": "Default state",
        "msg_estado_padrao_corpo": "No default state saved yet.\nAdjust the light as you like and click 'Save current'.",
        "dlg_novo_favorito_titulo": "New favorite",
        "dlg_novo_favorito_prompt": "Favorite name:",
        "msg_excluir_favorito_titulo": "Delete favorite",
        "msg_excluir_favorito_corpo": "Delete the favorite '{nome}'?",
        "msg_dia_noite_titulo": "Day / Night",
        "msg_dia_noite_corpo": "Set it up first: click 'Configure...' and choose a favorite for day and another for night.",
        "msg_modo_ambiente_titulo": "Ambient Mode",
        "msg_modo_ambiente_corpo": "Screen capture (Pillow) is unavailable in this version.",

        "tray_mostrar": "Show",
        "tray_ligar_desligar": "Turn On / Off",
        "tray_sair": "Quit",

        "cfg_lampadas_configuradas": "Configured bulbs",
        "cfg_btn_adicionar": "+ Add",
        "cfg_btn_buscar": "Scan the network",
        "cfg_btn_fechar": "Close",
        "cfg_lista_vazia": "(none — click Add or Scan the network)",
        "cfg_linha_lampada": "{nome}   —   {ip}",
        "cfg_sem_nome": "(no name)",
        "cfg_ip_desconhecido": "?",
        "cfg_btn_editar": "Edit",

        "form_campo_nome": "Name",
        "form_campo_id": "ID (Device ID)",
        "form_campo_ip": "Network IP",
        "form_campo_key": "Local key",
        "form_campo_versao": "Version (3.3 / 3.4 / 3.5)",
        "form_btn_salvar": "Save",
        "msg_campos_obrigatorios_titulo": "Required fields",
        "msg_campos_obrigatorios_corpo": "ID, IP and Local key are required.",
        "msg_remover_titulo": "Remove",
        "msg_remover_corpo": "Remove '{nome}'?",
        "remover_lampada_padrao": "this bulb",
        "msg_buscar_titulo": "Scan the network",
        "msg_buscar_corpo": "No new bulb found.\n(Already configured ones do not appear. The local key must be obtained via obter_chave.py.)",

        "dn_sem_favoritos": "Save at least one Favorite first\n(button '+  Save current as favorite').",
        "dn_btn_fechar": "Close",
        "dn_linha_dia": "Day — favorite and start time:",
        "dn_linha_noite": "Night — favorite and start time:",
        "dn_rampa_inicio": "Starting at night, dim over",
        "dn_rampa_ate": "min, down to",
        "dn_rampa_brilho": "% brightness",
        "dn_rampa_explicacao": "(at the night time the light applies the favorite and starts\ndimming gradually, reaching the minimum at the end of that period)",
        "dn_btn_salvar_ativar": "Save and activate",
        "dn_fav_desconhecido": "?",

        "atalhos_so_windows": "Global shortcuts available only on Windows.",
        "atalhos_btn_fechar": "Close",
        "atalhos_explicacao": "Shortcuts that work across Windows (even when minimized).\nCheck at least one modifier (Ctrl / Alt / Shift / Win).",
        "atalhos_btn_salvar": "Save",
        "atalhos_chk_ctrl": "Ctrl",
        "atalhos_chk_alt": "Alt",
        "atalhos_chk_shift": "Shift",
        "atalhos_chk_win": "Win",
        "atalhos_chk_ativo": "Active",

        "idioma_label": "Language:",
        "msg_idioma_titulo": "Language",
        "msg_idioma_corpo": "Restart the app to apply the new language.",
    },
}


def definir_idioma(idioma):
    """Define o idioma atual (cai no portugues se for um valor desconhecido)."""
    global IDIOMA
    IDIOMA = idioma if idioma in TEXTOS else "pt"


def T(chave, **kw):
    """Texto traduzido no idioma atual. Aceita parametros nomeados para interpolar
    (ex.: T('brilho_pct', brilho=80)). Se faltar a traducao, cai no portugues e,
    em ultimo caso, devolve a propria chave -- nunca quebra a UI."""
    s = TEXTOS.get(IDIOMA, {}).get(chave)
    if s is None:
        s = TEXTOS.get("pt", {}).get(chave, chave)
    try:
        return s.format(**kw) if kw else s
    except Exception:
        return s
