import os
import re
import sys
import subprocess
from urllib.parse import unquote

BASE = os.path.dirname(os.path.abspath(__file__))

VALID = re.compile(r"^https?://(www\.)?tbhindex\.com/(pt/)?builds/\d+/?$", re.I)


def main() -> None:
    try:
        raw = sys.argv[1] if len(sys.argv) > 1 else ""
        m = re.match(r"^tbh://(add|rm)\?url=(.+)$", raw, re.I)
        if not m:
            print("Link invalido: " + raw)
            return
        action, enc = m.group(1).lower(), unquote(m.group(2))
        enc = enc.split("?", 1)[0].split("#", 1)[0]
        if not VALID.match(enc):
            print("URL nao permitida (so builds do tbhindex.com): " + enc)
            return
        print("A " + ("importar" if action == "add" else "remover") + ": " + enc)
        print("Isto pode demorar uns segundos (volta a sacar todas as builds)...")
        r = subprocess.run([sys.executable, os.path.join(BASE, "tbh_site.py"), "--" + action, enc], cwd=BASE)
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
