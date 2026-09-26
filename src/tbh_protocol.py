import os
import re
import sys
import subprocess
from urllib.parse import unquote

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

VALID = re.compile(r"^https?://(www\.)?tbhindex\.com/(pt/)?builds/\d+/?$", re.I)


def _titulo_farm(conta: str = "") -> str:
    """Gera um título de consola seguro e identificável para a conta."""
    nome_conta = re.sub(r"[^\w ().-]", "_", (conta or "Todas as contas").strip())[:60]
    return "TBH FARM - " + (nome_conta or "Todas as contas")


def _abrir_run_farm(conta: str = "") -> bool:
    """Abre o vigia numa consola visível, com a conta identificada no título."""
    bat = os.path.join(ROOT, "run_farm.bat")
    if os.name != "nt" or not os.path.isfile(bat):
        return False

    titulo = _titulo_farm(conta)
    env = os.environ.copy()
    env["TBH_FARM_CONTA"] = conta
    env["TBH_FARM_TITULO"] = titulo
    try:
        subprocess.Popen(
            ["cmd.exe", "/K", f"title {titulo} & call {os.path.basename(bat)}"],
            cwd=ROOT,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
        return True
    except OSError as exc:
        print("AVISO: nao consegui abrir run_farm.bat: " + str(exc))
        return False


def _handle_farm(raw: str):
    from urllib.parse import parse_qs
    if not os.path.exists(os.path.join(BASE, "tbh_farm_watch.py")):
        # versao publica: vigia de farm nao incluido — apenas informa e sai limpo
        print("O vigia de farm (tbh_farm_watch.py) nao faz parte desta versao publica.")
        print("Disponiveis: tbh://add?url=... e tbh://rm?url=... (builds do tbhindex.com).")
        return True
    try:
        # tbh://farm?add=Nome+ou+tbh://farm?rm=Nome ou tbh://farm?ack=Nome
        q = raw.split("?", 1)[1] if "?" in raw else ""
        qs = parse_qs(q)
        # parse_qs already decodes, but also handle unquote for single values
        def one(k):
            v = qs.get(k)
            if not v: return ""
            return unquote(v[0])

        def adicionar(nome, conta_farm=""):
            print(f"A marcar para farmar: {nome}" + (f" @ {conta_farm}" if conta_farm else " @ auto (deteta sozinho qual conta droppou)"))
            cmd = [sys.executable, os.path.join(BASE, "tbh_farm_watch.py"), "--add", nome]
            if conta_farm:
                cmd += ["--conta", conta_farm]
            r = subprocess.run(cmd, cwd=ROOT if os.path.isdir(os.path.join(ROOT, "config")) else BASE)
            if r.returncode != 0:
                print("ERRO ao marcar: " + str(r.returncode))
                return
            # Abre a janela visível depois de guardar o alvo, para o .bat já o encontrar.
            if _abrir_run_farm(conta_farm):
                print(f"OK marcado! run_farm.bat aberto numa janela dedicada: {_titulo_farm(conta_farm)}.")
            else:
                print("OK marcado, mas nao consegui abrir run_farm.bat. Abre-o manualmente para ver o vigia.")

        add = one("add")
        rm = one("rm")
        ack = one("ack")
        conta = one("conta") or one("account") or ""
        # compat: tbh://farm?add=Nome&conta=Conta 1
        if add:
            # conta pode vir do botão da build (|user=Conta X) — se não vier, auto-deteta no watch
            adicionar(add, conta)
            return True
        if rm:
            print(f"A remover farm: {rm}")
            r = subprocess.run([sys.executable, os.path.join(BASE, "tbh_farm_watch.py"), "--rm", rm] + (["--conta", conta] if conta else []), cwd=ROOT if os.path.isdir(os.path.join(ROOT, "config")) else BASE)
            return True
        if ack or "ack-all" in q.lower() or "ack_all" in q.lower():
            nome = ack or ""
            if "ack-all" in q.lower() or "ack_all" in q.lower():
                print("A confirmar todos hits...")
                r = subprocess.run([sys.executable, os.path.join(BASE, "tbh_farm_watch.py"), "--ack", "--all"], cwd=ROOT if os.path.isdir(os.path.join(ROOT, "config")) else BASE)
            else:
                print(f"A confirmar hit: {nome}")
                r = subprocess.run([sys.executable, os.path.join(BASE, "tbh_farm_watch.py"), "--ack", nome] if nome else [sys.executable, os.path.join(BASE, "tbh_farm_watch.py"), "--ack"], cwd=ROOT if os.path.isdir(os.path.join(ROOT, "config")) else BASE)
            return True
        # if no known param, treat raw path as add (+ conta se vier na query)
        # e.g. tbh://farm/Eclipse Amulet (Cosmic) A  ou  tbh://farm/Void Crystal?conta=Conta 1
        tail = raw.split("farm", 1)[-1].lstrip("/ ?")
        if tail and not any(k in q for k in ("add","rm","ack")):
            # tail pode ter ?conta=...
            if "?" in tail:
                tail, q2 = tail.split("?", 1)
                qs2 = parse_qs(q2)
                if not conta:
                    conta = (qs2.get("conta") or qs2.get("account") or [""])[0]
                    if conta: conta = unquote(conta)
            tail = unquote(tail)
            adicionar(tail, conta)
            return True
        print("Uso farm: tbh://farm?add=Nome%20Do%20Item[&conta=Conta]  |  tbh://farm?rm=Nome  |  tbh://farm?ack=Nome")
        return True
    except Exception as e:
        print("ERRO farm: " + str(e))
        return True


def main() -> None:
    try:
        raw = sys.argv[1] if len(sys.argv) > 1 else ""
        # farm protocol — novo
        if raw.lower().startswith("tbh://farm"):
            handled = _handle_farm(raw)
            # regenera site para reflectir estado Farmando
            try:
                subprocess.run([sys.executable, os.path.join(BASE, "tbh_site.py"), "--sem-abrir"], cwd=ROOT if os.path.isdir(os.path.join(ROOT, "config")) else BASE, timeout=20)
                print("Site regenerado com estado Farmando.")
            except Exception:
                pass
            return
        m = re.match(r"^tbh://(add|rm)\?url=(.+)$", raw, re.I)
        if not m:
            print("Link invalido: " + raw)
            print("Validos: tbh://add?url=...  tbh://rm?url=...  tbh://farm?add=Nome")
            return
        action, enc = m.group(1).lower(), unquote(m.group(2))
        enc = enc.split("?", 1)[0].split("#", 1)[0]
        if not VALID.match(enc):
            print("URL nao permitida (so builds do tbhindex.com): " + enc)
            return
        print("A " + ("importar" if action == "add" else "remover") + ": " + enc)
        print("Isto pode demorar uns segundos (volta a sacar todas as builds)...")
        r = subprocess.run([sys.executable, os.path.join(BASE, "tbh_site.py"), "--" + action, enc], cwd=ROOT if os.path.isdir(os.path.join(ROOT, "config")) else BASE)
        if r.returncode != 0:
            print("O script devolveu erro " + str(r.returncode))
    except Exception as e:
        print("ERRO: " + str(e))
    finally:
        try:
            if sys.stdin and sys.stdin.isatty():
                input("\nEnter para fechar...")
        except EOFError:
            pass


if __name__ == "__main__":
    main()
