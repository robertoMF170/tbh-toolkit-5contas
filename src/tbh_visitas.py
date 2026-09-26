# -*- coding: utf-8 -*-
"""tbh_visitas.py - servidor local com estatisticas de visitantes.

Serve o site `minhas_builds.html` por HTTP (para que o browser consiga
fazer fetch a API) e expoe `/api/visitas`:

  GET  /api/visitas  -> estatisticas agregadas
  POST /api/visitas  -> {"device": "...", "event": "visit"|"ping"|"github_click"}

Guarda tudo em `var/visitas.json` (por IP e por device-id do browser).
Stdlib only; zero dependencias externas.

Uso:
  python -X utf8 src/tbh_visitas.py [--port 8765] [--root .] [--db var/visitas.json]
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(AQUI)

PORTA_BASE = 8765
ONLINE_SEGUNDOS = 60          # heartbeat < 60s => online
SESSAO_SEGUNDOS = 1800        # gap > 30 min entre pings => nova visita/sessao

_LOCK = threading.RLock()
_DB_PATH = [None]  # mutavel, definido no arranque


# ---------------------------------------------------------------------------
# persistencia
# ---------------------------------------------------------------------------
def _db_padrao() -> str:
    for base in (ROOT, AQUI):
        p = os.path.join(base, "var", "visitas.json")
        if os.path.isdir(os.path.dirname(p)):
            return p
    return os.path.join(ROOT, "var", "visitas.json")


def carregar(caminho: str) -> dict:
    try:
        with open(caminho, "r", encoding="utf-8-sig") as fh:
            dados = json.load(fh)
        if isinstance(dados, dict):
            return dados
    except (OSError, ValueError):
        pass
    return {"ips": {}, "devices": {}}


def guardar(caminho: str, dados: dict) -> None:
    pasta = os.path.dirname(caminho) or "."
    os.makedirs(pasta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=pasta, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(dados, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, caminho)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# registos
# ---------------------------------------------------------------------------
def _registo(dados: dict, grupo: str, chave: str, agora: float) -> dict:
    grupo_map = dados.setdefault(grupo, {})
    rec = grupo_map.get(chave)
    if not isinstance(rec, dict):
        rec = {"visitas": 0, "github": 0, "first": agora, "last": 0.0,
               "ips": [], "devices": []}
        grupo_map[chave] = rec
    return rec


def _associa(rec: dict, campo: str, valor: str, limite: int = 50) -> None:
    if valor and valor not in rec.get(campo, []):
        lista = rec.setdefault(campo, [])
        lista.append(valor)
        if len(lista) > limite:
            del lista[: len(lista) - limite]


def registar(dados: dict, ip: str, device: str, evento: str,
              agora: "float | None" = None) -> bool:
    """Aplica um evento; devolve True se houve alteracao."""
    agora = time.time() if agora is None else agora
    evento = (evento or "ping").strip().lower()
    if evento not in ("visit", "ping", "github_click"):
        evento = "ping"
    mudou = False
    with _LOCK:
        rip = _registo(dados, "ips", ip, agora)
        rdev = _registo(dados, "devices", device, agora)
        for rec in (rip, rdev):
            nova_sessao = rec.get("last", 0) <= 0 or (agora - rec.get("last", 0)) > SESSAO_SEGUNDOS
            if nova_sessao or evento == "visit":
                if nova_sessao or not rec.get("_contou", False):
                    rec["visitas"] = int(rec.get("visitas", 0)) + 1
                    rec["_contou"] = True
                    mudou = True
            if rec.get("last", 0) < agora:
                rec["last"] = agora
                mudou = True
        if evento == "github_click":
            rip["github"] = int(rip.get("github", 0)) + 1
            rdev["github"] = int(rdev.get("github", 0)) + 1
            mudou = True
        _associa(rip, "devices", device)
        _associa(rdev, "ips", ip)
    return mudou


# ---------------------------------------------------------------------------
# estatisticas
# ---------------------------------------------------------------------------
def _escrever_stats(dados: dict) -> dict:
    agora = time.time()

    def _grupo(nome: str) -> list:
        saida = []
        itens = sorted(dados.get(nome, {}).items(),
                       key=lambda kv: kv[1].get("last", 0), reverse=True)
        for chave, rec in itens:
            saida.append({
                "id": chave,
                "visitas": int(rec.get("visitas", 0)),
                "github": int(rec.get("github", 0)),
                "online": bool(agora - rec.get("last", 0) < ONLINE_SEGUNDOS),
                "last": rec.get("last", 0),
                "devices": sorted(rec.get("devices", [])),
            })
        return saida

    per_ip = _grupo("ips")
    per_device = [d for d in _grupo("devices") if d["id"]]
    online_ips = [g for g in per_ip if g["online"]]
    return {
        "agora": agora,
        "online_agora": len({d["id"] for d in per_device if d["online"]}),
        "ips_online": len(online_ips),
        "total_visitas": sum(g["visitas"] for g in per_ip),
        "total_github": sum(g["github"] for g in per_ip),
        "por_ip": per_ip,
        "por_device": per_device,
    }


# ---------------------------------------------------------------------------
# servidor
# ---------------------------------------------------------------------------
class VisitasHandler(BaseHTTPRequestHandler):
    server_version = "tbhVisitas/1.0"

    # -- helpers -----------------------------------------------------------
    def _cors(self):
        """Headers CORS: o dashboard pode estar aberto como file:// ..."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")

    def _json(self, payload, codigo=200):
        corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(corpo)

    def _ip(self) -> str:
        return (self.client_address[0] or "?") if self.client_address else "?"

    def _ficheiro(self, caminho: str):
        base = getattr(self.server, "tbh_root", ROOT)
        real_base = os.path.realpath(base)
        alvo = os.path.realpath(os.path.join(base, caminho.lstrip("/\\").replace("\\", "/")))
        if not (alvo == real_base or alvo.startswith(real_base + os.sep)):
            self._json({"erro": "caminho invalido"}, 403)
            return
        if not os.path.isfile(alvo):
            self._json({"erro": "nao encontrado"}, 404)
            return
        tipos = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml", ".png": "image/png",
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".ico": "image/x-icon",
        }
        ext = os.path.splitext(alvo)[1].lower()
        try:
            with open(alvo, "rb") as fh:
                corpo = fh.read()
        except OSError:
            self._json({"erro": "nao foi possivel ler"}, 500)
            return
        self.send_response(200)
        self.send_header("Content-Type", tipos.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(corpo)))
        self._cors()
        self.end_headers()
        self.wfile.write(corpo)

    # -- rotas -------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        rota = self.path.split("?", 1)[0]
        if rota in ("/api/visitas", "/api/visitas/"):
            with _LOCK:
                dados = carregar(_DB_PATH[0])
            self._json(_escrever_stats(dados))
        elif rota in ("/", "/index.html", "/minhas_builds.html"):
            self._ficheiro("minhas_builds.html")
        else:
            self._ficheiro(rota)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self._cors()
        self.end_headers()

    def do_POST(self):  # noqa: N802
        rota = self.path.split("?", 1)[0]
        if rota not in ("/api/visitas", "/api/visitas/"):
            self._json({"erro": "rota desconhecida"}, 404)
            return
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
            bruto = self.rfile.read(tamanho) if tamanho > 0 else b"{}"
            pedido = json.loads(bruto.decode("utf-8") or "{}")
        except (ValueError, OSError):
            pedido = {}
        if not isinstance(pedido, dict):
            pedido = {}
        device = str(pedido.get("device") or "")[:64].strip()
        evento = str(pedido.get("event") or "ping")
        ip = self._ip()
        with _LOCK:
            dados = carregar(_DB_PATH[0])
            mudou = registar(dados, ip, device, evento)
            if mudou:
                guardar(_DB_PATH[0], dados)
            stats = _escrever_stats(dados)
        self._json({"ok": True, "stats": stats})

    def log_message(self, fmt, *args):  # silencioso por defeito
        if getattr(self.server, "tbh_verbose", False):
            super().log_message(fmt, *args)


def arrancar(porta: int, root: str, db: str, verbose: bool = False) -> ThreadingHTTPServer:
    _DB_PATH[0] = db
    httpd = ThreadingHTTPServer(("0.0.0.0", porta), VisitasHandler)
    httpd.tbh_root = root
    httpd.tbh_verbose = verbose
    return httpd


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Servidor local de estatisticas de visitas do site tbh.")
    parser.add_argument("--port", type=int, default=PORTA_BASE,
                        help="porta HTTP (predefinicao: %d)" % PORTA_BASE)
    parser.add_argument("--root", default=ROOT,
                        help="pasta raiz com minhas_builds.html")
    parser.add_argument("--db", default=_db_padrao(),
                        help="caminho do ficheiro var/visitas.json")
    parser.add_argument("--verbose", action="store_true",
                        help="logar pedidos no terminal")
    args = parser.parse_args(argv)

    httpd = arrancar(args.port, os.path.abspath(args.root),
                     os.path.abspath(args.db), args.verbose)
    print("[visitas] http://localhost:%d/  (db: %s)" % (args.port, args.db), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
