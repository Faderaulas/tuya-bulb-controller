"""
Fetches the devices linked to your Tuya IoT project and extracts their local key.

You type the credentials yourself at runtime (the Access Secret is hidden).
Nothing is sent anywhere or stored: the Access ID/Secret is only used for this
single query to the Tuya Cloud. Environment variables are accepted as a shortcut:
    TUYA_KEY / TUYA_SECRET / TUYA_REGION

Saves what's needed for LOCAL control into 'devices.json'
(id, name, local key, protocol version, ip if available).
The Access Secret is NOT saved.

How to get the Access ID/Secret: create a free Cloud project at
https://developer.tuya.com, link your Smart Life / Tuya app account (via the QR
code under Devices -> Link App Account), and copy the project's Access ID and
Access Secret. The region matches your app account's data center (us/eu/cn/in).
"""
import os
import json
import sys
import getpass
import tinytuya

key = os.environ.get("TUYA_KEY")
secret = os.environ.get("TUYA_SECRET")
region = os.environ.get("TUYA_REGION")

# Ask interactively for whatever didn't come from an environment variable.
if not key:
    key = input("Access ID / Client ID: ").strip()
if not secret:
    secret = getpass.getpass("Access Secret / Client Secret (hidden): ").strip()
if not region:
    region = (input("Region [Enter = us / Western America]: ").strip() or "us")

if not key or not secret:
    print("ERROR: Access ID and Access Secret are required.")
    sys.exit(1)

print(f"Connecting to the Tuya Cloud (region={region})...")
cloud = tinytuya.Cloud(apiRegion=region, apiKey=key, apiSecret=secret)

devices = cloud.getdevices(verbose=False)

if not isinstance(devices, list):
    print("Unexpected response from the cloud:")
    print(json.dumps(devices, indent=2, ensure_ascii=False))
    sys.exit(1)

print(f"\n{len(devices)} device(s) found:\n")

out = []
for d in devices:
    item = {
        "id": d.get("id"),
        "name": d.get("name"),
        "key": d.get("key"),          # <-- local key
        "version": d.get("version"),  # protocol version (3.3 / 3.4 / 3.5)
        "ip": d.get("ip", ""),
        "category": d.get("category"),
        "product_name": d.get("product_name"),
    }
    out.append(item)
    # Show the local key partially masked in the log
    lk = item["key"] or ""
    lk_mask = (lk[:4] + "..." + lk[-2:]) if len(lk) > 6 else "(empty)"
    print(f"  - {item['name']}")
    print(f"      id:      {item['id']}")
    print(f"      version: {item['version']}")
    print(f"      ip:      {item['ip'] or '(discover via LAN scan)'}")
    print(f"      key:     {lk_mask}  (full key saved in devices.json)")
    print()

# Fill in IP and protocol version via a LAN scan (the cloud doesn't provide those)
print("Looking for the devices on the local network (scan)...")
try:
    found = tinytuya.deviceScan(False, 18)
except Exception as e:
    found = {}
    print(f"  (scan failed: {e})")

by_id = {v.get("gwId") or v.get("id"): v for v in found.values()}
for item in out:
    info = by_id.get(item["id"])
    if info:
        item["ip"] = info.get("ip", item["ip"])
        item["version"] = info.get("version", item["version"])
        print(f"  {item['name']}: ip={item['ip']} version={item['version']}")
    else:
        print(f"  {item['name']}: not seen in the scan (check it's on the same network)")

base = os.path.dirname(__file__)
path = os.path.join(base, "devices.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print("Saved to devices.json")

# Keep the .exe in sync: copy into dist/ if that folder exists
dist = os.path.join(base, "dist")
if os.path.isdir(dist):
    import shutil
    shutil.copy(path, os.path.join(dist, "devices.json"))
    print("Also updated dist/devices.json (used by the .exe)")
