import os
import re
import sys
import subprocess
from urllib.parse import unquote

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

VALID = re.compile(r"^https?://(www\.)?tbhindex\.com/(pt/)?builds/\d+/?$", re.I)


def _handle_farm(raw: str):
    from urllib.parse import parse_qs
    try:
        import tbh_farm_alert as farm_alert
        # tbh://farm?add=Nome ou tbh://farm?rm=Nome ou tbh://farm?ack=Nome
        q = raw.split("?", 1)[1] if "?" in raw else ""
        qs = parse_qs(q)
        # parse_qs already decodes, but also handle unquote for single values
        def one(k):
            v = qs.get(k)
            if not v: return ""
            return unquote(v[0])

        def adicionar(nome, conta_farm=""):
            if farm_alert.add_target(nome, conta_farm):
                destino = f" @ {conta_farm}" if conta_farm else " @ todas as contas"
                print(f"OK — alerta registado: {nome}{destino}. O run.bat verifica os saves a cada 2s.")
            else:
                print(f"Este alvo ja esta registado: {nome}.")

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
            removed = farm_alert.remove_target(rm, conta)
            print(f"Alvo removido: {rm}." if removed else f"Alvo nao encontrado: {rm}.")
            return True
        if ack or "ack-all" in q.lower() or "ack_all" in q.lower():
            nome = ack or ""
            count = farm_alert.acknowledge_hits(
                nome,
                all_hits=("ack-all" in q.lower() or "ack_all" in q.lower() or not nome),
            )
            print(f"{count} alerta(s) confirmado(s).")
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
