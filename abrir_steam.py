r"""ABRIR STEAM/JOGO POR SANDBOX — cada sandbox entra na conta Steam certa e
abre o Task Bar Hero sozinho, sem selecionares nada.

Como funciona:
  - Cada conta Steam corre numa sandbox do Sandboxie (baus.json tem o mapa).
  - O Steam guarda as contas com password memorizada, mas entra sempre na
    ultima que fez login. Aqui forcamos a conta certa com -login <nome>
    (a password memorizada e usada automaticamente; se pedira Steam Guard
    insere-o uma vez e fica memorizado).
  - Depois de o Steam arrancar, -applaunch 3678970 abre o jogo.

Uso:
  python abrir_steam.py                # menu com as contas
  python abrir_steam.py 2              # abre a conta 2 (a numeracao do baus.json)
  python abrir_steam.py 2 3 4 5        # abre varias de uma vez
  python abrir_steam.py --todas        # abre todas as sandboxes
  python abrir_steam.py --estado       # mostra o que esta a correr

Cria tambem atalhos .bat: abrir_conta2.bat, etc. (duplo clique e ja esta).
"""

import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
SBIE_START = r"C:\Program Files\Sandboxie-Plus\Start.exe"
GAME_APPID = "3678970"
# tempo que o steam costuma levar a ficar operacional dentro da sandbox
STEAM_ARRANQUE = 25


def contas() -> list:
    """[{idx, nome, id, sandbox}] — sandbox deduzida do caminho do save."""
    cfg = json.load(open(os.path.join(BASE, "baus.json"), encoding="utf-8-sig"))
    out = []
    for i, c in enumerate(cfg.get("contas", []), 1):
        sandbox = ""
        save = c.get("save", "")
        if "\\Sandbox\\" in save:
            # caminho: C:\Sandbox\Robs\<nome_da_caixa>\user\...
            sandbox = save.split("\\Sandbox\\")[1].split("\\")[1]
        out.append({"idx": i, "nome": c.get("nome", "?"), "id": str(c.get("id", "")),
                    "save": save, "sandbox": sandbox})
    return out


def nome_steam(steam_id: str) -> str:
    """AccountName da conta a partir do loginusers.vdf do Steam (para -login)."""
    import re
    vdf = r"C:\Program Files (x86)\Steam\config\loginusers.vdf"
    try:
        txt = open(vdf, encoding="utf-8", errors="replace").read()
    except Exception:
        return ""
    m = re.search(r'"' + steam_id + r'"\s*\{[^{}]*?"AccountName"\s*"([^"]+)"', txt)
    return (m.group(1) if m else "").strip()


def _processos_sandbox() -> dict:
    """{accountLogin: True} das sandboxes com Steam/jogo a correr + {box: True}.
    O Sandboxie não deixa ver os PIDs de fora, mas a linha de comando do
    steam.exe lançado por nós traz "-login <conta>" (WMI consegue ler).
    GameID do jogo no commandline (ex.: "--GameID=76561198...") também indica
    qual sandbox está a jogar. Devolve {"logins": set, "gameids": set}.
    """
    import re
    logins, gameids = set(), set()
    try:
        r = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='steam.exe' or Name='TaskBarHero.exe'\""
             " | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=30)
        data = json.loads(r.stdout or "[]")
        if isinstance(data, dict):
            data = [data]
        for p in data or []:
            cl = str(p.get("CommandLine") or "")
            m = re.search(r"-login\s+([^\"\s]+)", cl)
            if m:
                logins.add(m.group(1))
            m = re.search(r"--GameID=(\d{5,})", cl)
            if m:
                gameids.add(m.group(1))
    except Exception:
        pass
    return {"logins": logins, "gameids": gameids}


def sandbox_a_correr(info: dict) -> bool:
    """True se esta conta já tem Steam (com o seu -login) ou jogo a correr."""
    proc = _processos_sandbox()
    acc = nome_steam(info["id"])
    if acc and acc in proc["logins"]:
        return True
    if info["id"] in proc["gameids"]:
        return True
    return False


def lancar(box: str, programa: str, args: list = None, espera: int = 20) -> bool:
    try:
        subprocess.run([SBIE_START, "/box:" + box, programa] + (args or []),
                       timeout=espera, capture_output=True)
        return True
    except subprocess.TimeoutExpired:
        return True  # o start.exe pode nao terminar se a app continuar aberta
    except Exception as e:
        print("   erro: " + str(e)[:100])
        return False


def abrir_conta(info: dict, com_jogo: bool = True) -> None:
    box = info["sandbox"]
    acc = nome_steam(info["id"])
    if not box:
        # conta nativa (fora de sandbox): lança o Steam normal com a conta certa
        steam = r"C:\Program Files (x86)\Steam\steam.exe"
        args = [steam] + (["-login", acc] if acc else []) + (["-applaunch", GAME_APPID] if com_jogo else [])
        print("[nativa] a abrir " + info["nome"] + " (login " + (acc or "?") + ")...")
        try:
            subprocess.Popen(args)
        except Exception as e:
            print("   erro: " + str(e)[:100])
        return
    if sandbox_a_correr(info):
        print("[" + box + "] ja esta a correr — salto (fecha primeiro se queres reiniciar)")
        return
    if not acc:
        print("[" + box + "] NAO SEI QUE CONTA Steam e — cancelo (evita entrar na conta errada e reiniciar o save)")
        return
    print("[" + box + "] a abrir Steam como " + acc + "...")
    if not lancar(box, r"C:\Program Files (x86)\Steam\steam.exe", ["-login", acc]):
        return
    time.sleep(STEAM_ARRANQUE)
    if com_jogo:
        print("[" + box + "] a abrir o jogo (appid " + GAME_APPID + ")...")
        lancar(box, r"C:\Program Files (x86)\Steam\steam.exe", ["-applaunch", GAME_APPID], espera=15)
    time.sleep(2)


def fechar(info: dict) -> None:
    """Fecha o Steam/jogo desta conta (procura pelo login no commandline)."""
    acc = nome_steam(info["id"])
    try:
        r = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='steam.exe' or Name='TaskBarHero.exe'\""
             " | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=30)
        data = json.loads(r.stdout or "[]")
        if isinstance(data, dict):
            data = [data]
        mortos = 0
        for p in data or []:
            cl = str(p.get("CommandLine") or "")
            if (acc and ("-login " + acc) in cl) or info["id"] in cl:
                subprocess.run(["taskkill", "/PID", str(p["ProcessId"]), "/F"], capture_output=True)
                mortos += 1
        print("[" + (info["sandbox"] or "nativa") + "] fechados " + str(mortos) + " processos de " + acc)
    except Exception as e:
        print("   erro ao fechar: " + str(e)[:100])


def criar_bats() -> None:
    """Cria abrir_contaN.bat para cada conta (duplo clique = abre essa conta)."""
    for info in contas():
        caminho = os.path.join(BASE, "abrir_conta" + str(info["idx"]) + ".bat")
        conteudo = ("@echo off\r\nchcp 65001 >nul\r\ntitle Abrir " + info["nome"]
                    + " - Task Bar Hero\r\ncd /d \"%~dp0\"\r\npython -X utf8 abrir_steam.py "
                    + str(info["idx"]) + "\r\n")
        try:
            atual = open(caminho, encoding="utf-8").read()
        except Exception:
            atual = ""
        if atual != conteudo:
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(conteudo)


def estado() -> None:
    print("Estado das contas:")
    proc = _processos_sandbox()
    for info in contas():
        acc = nome_steam(info["id"])
        a_correr = (acc and acc in proc["logins"]) or info["id"] in proc["gameids"]
        onde = info["sandbox"] or "nativa"
        print("  Conta " + str(info["idx"]) + " " + info["nome"]
              + " -> " + onde + " : " + ("A CORRER" if a_correr else "parada"))


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = [x for x in sys.argv[1:]]
    if not os.path.exists(SBIE_START):
        print("Nao encontrei o Sandboxie Start.exe em: " + SBIE_START)
        return
    criar_bats()
    if "--estado" in a:
        estado()
        return
    lista = contas()
    nums = [int(x) for x in a if x.isdigit()]
    if "--fechar" in a:
        alvo = nums or [i["idx"] for i in lista]
        for n in alvo:
            info = next((x for x in lista if x["idx"] == n), None)
            if info:
                fechar(info)
        return
    if "--todas" in a:
        nums = [i["idx"] for i in lista]
    if not nums:
        print("Que conta abrir?")
        for i in lista:
            corr = " [A CORRER]" if i["sandbox"] and sandbox_a_correr(i["sandbox"]) else ""
            print("  " + str(i["idx"]) + ". " + i["nome"] + "  (sandbox: " + (i["sandbox"] or "nativa") + ")" + corr)
        try:
            r = input("numero (vazio=sair): ").strip()
        except EOFError:
            r = ""
        if r.isdigit():
            nums = [int(r)]
        else:
            return
    for n in nums:
        info = next((x for x in lista if x["idx"] == n), None)
        if info:
            abrir_conta(info)
        else:
            print("nao existe conta " + str(n))
    print("feito.")


if __name__ == "__main__":
    main()
