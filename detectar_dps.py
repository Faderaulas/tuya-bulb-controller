"""
Detecta todos os DPs disponíveis em cada lâmpada configurada no dispositivos.json.

Útil para descobrir DPs além do conjunto padrão Tipo B (20-28), como o DP 33
(power_memory) que em alguns modelos controla o comportamento ao religar.

Rodar:
    .venv\Scripts\python.exe detectar_dps.py
"""
import json
import os
import sys
import time

import tinytuya

PASTA = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(PASTA, "dispositivos.json")

# Se não achar ao lado do script, tenta em dist\ (onde o .exe guarda os JSONs)
if not os.path.exists(CONFIG):
    CONFIG = os.path.join(PASTA, "dist", "dispositivos.json")

if not os.path.exists(CONFIG):
    print("dispositivos.json não encontrado. Rode obter_chave.py primeiro.")
    sys.exit(1)

with open(CONFIG, encoding="utf-8") as f:
    lampadas = json.load(f)

if not lampadas:
    print("Nenhuma lâmpada configurada.")
    sys.exit(1)

for lmp in lampadas:
    nome = lmp.get("name", lmp.get("id"))
    ip = lmp.get("ip")
    dev_id = lmp.get("id")
    key = lmp.get("key")
    ver = float(lmp.get("version") or 3.3)

    print(f"\n=== {nome} ({ip}) ===")

    b = tinytuya.BulbDevice(dev_id, ip, key, version=ver)
    b.set_socketTimeout(6)
    b.set_socketRetryLimit(1)

    # Leitura inicial de status
    print("Lendo status atual...")
    resp = b.status()
    if not resp or "dps" not in resp:
        print("  Não foi possível ler o status (lâmpada offline?)")
        continue

    dps_atuais = resp["dps"]
    print(f"  DPs do status padrão: {sorted(int(k) for k in dps_atuais)}")
    for k, v in sorted(dps_atuais.items(), key=lambda x: int(x[0])):
        print(f"    DP {k:>3}: {v!r}")

    # Varredura de DPs extras (o tinytuya vai consultar faixas além de 20-28)
    print("\nVarredura de DPs disponíveis (pode demorar ~10s)...")
    try:
        todos = b.detect_available_dps()
    except Exception as e:
        print(f"  Erro na varredura: {e}")
        todos = {}

    dps_extras = {k: v for k, v in todos.items() if k not in dps_atuais}
    if dps_extras:
        print(f"  DPs extras encontrados: {sorted(int(k) for k in dps_extras)}")
        for k, v in sorted(dps_extras.items(), key=lambda x: int(x[0])):
            print(f"    DP {k:>3}: {v!r}")

        # Leitura detalhada dos extras
        print("\n  Lendo valores dos DPs extras...")
        time.sleep(0.5)
        resp2 = b.status()
        if resp2 and "dps" in resp2:
            for k in sorted(dps_extras.keys(), key=int):
                val = resp2["dps"].get(k)
                print(f"    DP {k:>3} = {val!r}")
    else:
        print("  Nenhum DP extra encontrado além do conjunto padrão.")

    # Verificação específica do DP 33 (power_memory em alguns modelos Tuya)
    print()
    dp33 = (todos or dps_atuais).get("33")
    if dp33 is not None:
        print(f"  DP 33 encontrado (power_memory?): {dp33!r}")
        print("  → Este DP pode controlar o comportamento ao religar a lâmpada.")
        print("    True  = lembra o último estado (memória)")
        print("    False = volta ao padrão de fábrica")
    else:
        print("  DP 33 não encontrado nesta lâmpada.")

    b.close()

print("\nPronto.")
