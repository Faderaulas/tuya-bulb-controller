"""
Busca os dispositivos vinculados ao projeto Tuya e extrai a local key.

As credenciais sao digitadas por VOCE na hora (o Access Secret fica oculto).
Nada e enviado para fora nem gravado: o Access ID/Secret so e usado nesta
consulta unica a nuvem Tuya. Tambem aceita variaveis de ambiente como atalho:
    TUYA_KEY / TUYA_SECRET / TUYA_REGION

Salva os dados necessarios para controle LOCAL em 'dispositivos.json'
(id, nome, local key, versao do protocolo, ip se disponivel).
O Access Secret NAO e salvo.
"""
import os
import json
import sys
import getpass
import tinytuya

key = os.environ.get("TUYA_KEY")
secret = os.environ.get("TUYA_SECRET")
region = os.environ.get("TUYA_REGION")

# Pede interativamente o que nao veio por variavel de ambiente.
if not key:
    key = input("Access ID / Client ID: ").strip()
if not secret:
    secret = getpass.getpass("Access Secret / Client Secret (oculto): ").strip()
if not region:
    region = (input("Regiao [Enter = us / Western America]: ").strip() or "us")

if not key or not secret:
    print("ERRO: Access ID e Access Secret sao obrigatorios.")
    sys.exit(1)

print(f"Conectando na nuvem Tuya (regiao={region})...")
cloud = tinytuya.Cloud(apiRegion=region, apiKey=key, apiSecret=secret)

devices = cloud.getdevices(verbose=False)

if not isinstance(devices, list):
    print("Resposta inesperada da nuvem:")
    print(json.dumps(devices, indent=2, ensure_ascii=False))
    sys.exit(1)

print(f"\n{len(devices)} dispositivo(s) encontrado(s):\n")

saida = []
for d in devices:
    item = {
        "id": d.get("id"),
        "name": d.get("name"),
        "key": d.get("key"),          # <-- local key
        "version": d.get("version"),  # versao do protocolo (3.3 / 3.4 / 3.5)
        "ip": d.get("ip", ""),
        "category": d.get("category"),
        "product_name": d.get("product_name"),
    }
    saida.append(item)
    # Mostra a local key parcialmente mascarada no log
    lk = item["key"] or ""
    lk_mask = (lk[:4] + "..." + lk[-2:]) if len(lk) > 6 else "(vazia)"
    print(f"  - {item['name']}")
    print(f"      id:      {item['id']}")
    print(f"      version: {item['version']}")
    print(f"      ip:      {item['ip'] or '(descobrir via scan LAN)'}")
    print(f"      key:     {lk_mask}  (salva completa em dispositivos.json)")
    print()

# Completa IP e versao do protocolo via scan na rede local (a nuvem nao traz isso)
print("Procurando os dispositivos na rede local (scan)...")
try:
    achados = tinytuya.deviceScan(False, 18)
except Exception as e:
    achados = {}
    print(f"  (scan falhou: {e})")

por_id = {v.get("gwId") or v.get("id"): v for v in achados.values()}
for item in saida:
    info = por_id.get(item["id"])
    if info:
        item["ip"] = info.get("ip", item["ip"])
        item["version"] = info.get("version", item["version"])
        print(f"  {item['name']}: ip={item['ip']} version={item['version']}")
    else:
        print(f"  {item['name']}: nao apareceu no scan (confira se esta na mesma rede)")

base = os.path.dirname(__file__)
caminho = os.path.join(base, "dispositivos.json")
with open(caminho, "w", encoding="utf-8") as f:
    json.dump(saida, f, indent=2, ensure_ascii=False)
print("Salvo em dispositivos.json")

# Mantem o .exe em sincronia: copia pra dist/ se a pasta existir
dist = os.path.join(base, "dist")
if os.path.isdir(dist):
    import shutil
    shutil.copy(caminho, os.path.join(dist, "dispositivos.json"))
    print("Tambem atualizado em dist/dispositivos.json (usado pelo .exe)")
