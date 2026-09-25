import re
import os
import time
import socket

IP = socket.gethostbyname("tbhindex.com")  # primeira resolução funciona
_orig = socket.getaddrinfo


def pinned(host, *a, **k):
    if host == "tbhindex.com":
        return _orig(IP, *a, **k)
    return _orig(host, *a, **k)


socket.getaddrinfo = pinned
print("tbhindex.com fixo em", IP)

import tbh_arvore as ta

home = ta.http_get("https://tbhindex.com/pt")
alvo = ["i18n-data", "game-data", "tbhSkillTree", "tbhRunes", "tbhRuneCosts", "statsReference", "heroMeta"]
for key in alvo:
    m = re.search(r"/assets/(" + key + r"-[A-Za-z0-9_-]+\.js)", home)
    if not m:
        print("sem", key)
        continue
    name = m.group(1).split("/")[-1]
    corpo = ta.http_get("https://tbhindex.com/assets/" + m.group(1))
    with open(os.path.join("tbhdata", name), "w", encoding="utf-8") as f:
        f.write(corpo)
    print("guardado:", name, len(corpo))
    for f2 in os.listdir("tbhdata"):
        if f2.startswith(key + "-") and f2 != name:
            os.remove(os.path.join("tbhdata", f2))
