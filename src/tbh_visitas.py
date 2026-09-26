# -*- coding: utf-8 -*-
"""tbh_visitas.py - servidor local com estatisticas de visitantes.

Serve o site `minhas_builds.html` por HTTP (para que o browser consiga
fazer fetch a API) e expoe `/api/visitas`:

  GET  /api/visitas  -> estatisticas agregadas
  POST /api/visitas  -> {"device": "...", "event": "visit"|"ping"|"github_click"}

Guarda tudo em `var/visitas.json` (por IP e por device-id do browser).
Stdlib only; zero dependencias externas.

Uso:
  python -X utf8 src/tbh_visitas.py [--port 8765] [--host 127.0.0.1] [--root .] [--db var/visitas.json]
"""
from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
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
# ações locais do vigia de farm
# ---------------------------------------------------------------------------
def executar_acao_farm(pedido: dict) -> dict:
    """Add/remove/ack farm targets from the locally served dashboard."""
    if not isinstance(pedido, dict):
        raise ValueError("Pedido invalido.")
    action = str(pedido.get("action") or "").strip().lower()
    name = str(pedido.get("name") or "").strip()
    account = str(pedido.get("conta") or "").strip()
    if action not in {"add", "remove", "ack", "status", "add-build"}:
        raise ValueError("Acao de farm desconhecida.")
    if action != "status" and (not name or len(name) > 200 or len(account) > 120):
        raise ValueError("Nome do item ou conta invalido.")

    if action == "add-build":
        from urllib.parse import urlsplit
        from tbh_site import normalize_url, resolve_url, load_urls, save_urls

        parsed = urlsplit(normalize_url(name))
        if parsed.scheme != "https" or parsed.netloc.casefold() not in {"tbhindex.com", "www.tbhindex.com"}:
            raise ValueError("O link tem de ser de uma build do tbhindex.com.")
        build_url = resolve_url(normalize_url(name))
        if not build_url:
            raise ValueError("Nao encontrei essa build do tbhindex.com.")
        urls = load_urls()
        if build_url not in urls:
            urls.append(build_url)
            save_urls(urls)
        if not generate_farm_dashboard():
            raise RuntimeError("Nao foi possivel regenerar a dashboard.")
        return {"ok": True, "changed": build_url not in urls[:-1], "action": action,
                "message": "Build adicionada. A dashboard sera atualizada ao voltar a abrir."}

    import tbh_farm_alert as farm_alert

    if action == "status":
        changed = False
        message = "Estado dos alertas atualizado."
    elif action == "add":
        changed = farm_alert.add_target(name, account)
        message = ("Alerta registado: " if changed else "Esse alerta ja estava registado: ") + name
    elif action == "remove":
        changed = farm_alert.remove_target(name, account)
        message = ("Alerta removido: " if changed else "Esse alerta nao estava registado: ") + name
    else:
        changed = farm_alert.acknowledge_hits(name, conta=account) > 0
        message = ("Alerta confirmado: " if changed else "Nao havia alerta pendente para: ") + name

    watch_data = farm_alert._watch_data()
    return {
        "ok": True,
        "changed": changed,
        "action": action,
        "message": message,
        "targets": farm_alert.load_targets(),
        "hits": watch_data["hits"],
    }


def gerar_builds(root: str) -> bool:
    """Regenerate the builds dashboard in a child process."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tbh_site.py")
    try:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", script, "--sem-abrir"],
            cwd=os.path.abspath(root),
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


# ---------------------------------------------------------------------------
# servidor
# ---------------------------------------------------------------------------
class VisitasHandler(BaseHTTPRequestHandler):
    server_version = "tbhVisitas/1.0"

    # -- helpers -----------------------------------------------------------
    def _cors(self):
        """Keep public stats compatible; allow farm writes only for same-machine origins."""
        if self.path.split("?", 1)[0] == "/api/farm":
            if self._farm_request_is_local():
                origin = self.headers.get("Origin", "")
                self.send_header("Access-Control-Allow-Origin", "null" if origin == "null" else origin)
                self.send_header("Vary", "Origin")
        else:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-TBH-Farm-Token")
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
        relative_parts = os.path.relpath(alvo, real_base).replace("\\", "/").split("/")
        allowed_static = (
            len(relative_parts) >= 2
            and relative_parts[0].casefold() == "assets"
            and os.path.splitext(alvo)[1].casefold() in {
                ".css", ".gif", ".ico", ".jpeg", ".jpg", ".js", ".png", ".svg", ".webp", ".woff", ".woff2"
            }
        ) or (
            len(relative_parts) >= 3
            and [part.casefold() for part in relative_parts[:2]] == ["data", "tbhdata"]
            and os.path.splitext(alvo)[1].casefold() in {".css", ".js", ".png", ".svg"}
        )
        if any(part.startswith(".") for part in relative_parts) or not (
            relative_parts == ["minhas_builds.html"] or allowed_static
        ):
            self._json({"erro": "ficheiro privado ou nao publicado"}, 404)
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
        if relative_parts == ["minhas_builds.html"]:
            token = getattr(self.server, "tbh_farm_token", "")
            corpo = corpo.replace(b"__TBH_FARM_API_TOKEN_VALUE__", token.encode("ascii"))
        self.send_response(200)
        self.send_header("Content-Type", tipos.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(corpo)))
        if relative_parts == ["minhas_builds.html"]:
            self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(corpo)

    # -- rotas -------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        rota = self.path.split("?", 1)[0]
        if rota == "/api/open":
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                self._json({"ok": False, "erro": "Abertura permitida apenas neste computador."}, 403)
                return
            if not generate_farm_dashboard():
                self._json({"ok": False, "erro": "Nao foi possivel gerar a dashboard. Confirma a janela do run.bat."}, 500)
                return
            self._json({"ok": True, "message": "Dashboard atualizada."})
        elif rota == "/api/health":
            self._json({
                "ok": True,
                "farm_api": 1,
                "root": os.path.realpath(getattr(self.server, "tbh_root", ROOT)),
            })
        elif rota == "/api/farm":
            if not self._farm_request_is_local() or not hmac.compare_digest(
                self.headers.get("X-TBH-Farm-Token", ""),
                getattr(self.server, "tbh_farm_token", ""),
            ):
                self._json({"ok": False, "erro": "Acesso local nao autorizado."}, 403)
                return
            try:
                import tbh_farm_alert as farm_alert
                watch_data = farm_alert._watch_data()
                self._json({"ok": True, "targets": farm_alert.load_targets(), "hits": watch_data["hits"]})
            except Exception:
                self._json({"ok": False, "erro": "Nao foi possivel ler o estado dos alertas."}, 500)
        elif rota in ("/api/visitas", "/api/visitas/"):
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

    def _farm_request_is_local(self) -> bool:
        try:
            peer_is_local = ipaddress.ip_address(self.client_address[0]).is_loopback
        except (ValueError, TypeError):
            peer_is_local = False
        port = int(self.server.server_address[1])
        bound_host = str(self.server.server_address[0]).lower()
        allowed_hosts = {f"localhost:{port}"}
        if bound_host == "0.0.0.0":
            allowed_hosts.update({f"127.0.0.1:{port}", f"[::1]:{port}"})
        elif bound_host in {"127.0.0.1", "::1"}:
            allowed_hosts.add(f"{bound_host}:{port}" if bound_host != "::1" else f"[::1]:{port}")
        elif bound_host == "localhost":
            allowed_hosts.add(f"127.0.0.1:{port}")
        allowed_origins = {f"http://{host}" for host in allowed_hosts} | {"null"}
        origin = self.headers.get("Origin", "")
        return (
            peer_is_local
            and self.headers.get("Host", "").lower() in allowed_hosts
            and (origin in allowed_origins or (self.command == "GET" and not origin))
        )

    def do_POST(self):  # noqa: N802
        rota = self.path.split("?", 1)[0]
        if rota == "/api/farm":
            if not self._farm_request_is_local() or not hmac.compare_digest(
                self.headers.get("X-TBH-Farm-Token", ""),
                getattr(self.server, "tbh_farm_token", ""),
            ):
                self._json({"ok": False, "erro": "Acoes de farm so podem ser usadas pela dashboard local."}, 403)
                return
            if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
                self._json({"ok": False, "erro": "O pedido tem de ser JSON."}, 415)
                return
            try:
                tamanho = int(self.headers.get("Content-Length") or 0)
                if tamanho <= 0 or tamanho > 8192:
                    raise ValueError("Tamanho de pedido invalido.")
                pedido = json.loads(self.rfile.read(tamanho).decode("utf-8"))
                resultado = executar_acao_farm(pedido)
            except (ValueError, UnicodeDecodeError) as exc:
                self._json({"ok": False, "erro": str(exc) or "Pedido JSON invalido."}, 400)
                return
            except Exception:
                self._json({"ok": False, "erro": "Nao foi possivel guardar a alteracao do vigia."}, 500)
                return
            self._json(resultado)
            return
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


class TBHThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def generate_farm_dashboard() -> bool:
    """Regenerate the full dashboard in the project root served by this local server."""
    # Set by arrancar() for the active serving instance.
    server = _ACTIVE_SERVER[0]
    if server is None:
        return False
    return gerar_builds(server.tbh_root)


_ACTIVE_SERVER = [None]


def arrancar(porta: int, root: str, db: str, verbose: bool = False,
             host: str = "127.0.0.1") -> ThreadingHTTPServer:
    _DB_PATH[0] = db
    httpd = TBHThreadingHTTPServer((host, porta), VisitasHandler)
    httpd.tbh_bound_host = host
    httpd.tbh_root = os.path.abspath(root)
    httpd.tbh_verbose = verbose
    httpd.tbh_farm_token = secrets.token_urlsafe(32)
    _ACTIVE_SERVER[0] = httpd
    return httpd


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Servidor local de estatisticas de visitas do site tbh.")
    parser.add_argument("--port", type=int, default=PORTA_BASE,
                        help="porta HTTP (predefinicao: %d)" % PORTA_BASE)
    parser.add_argument("--host", default="127.0.0.1",
                        help="interface de rede; por defeito so aceita ligacoes deste computador")
    parser.add_argument("--check-api", action="store_true",
                        help="confirma se o servidor local TBH compativel esta ativo nesta porta")
    parser.add_argument("--root", default=ROOT,
                        help="pasta raiz com minhas_builds.html")
    parser.add_argument("--db", default=_db_padrao(),
                        help="caminho do ficheiro var/visitas.json")
    parser.add_argument("--verbose", action="store_true",
                        help="logar pedidos no terminal")
    args = parser.parse_args(argv)
    if args.check_api:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/health", timeout=2) as response:
                health = json.loads(response.read().decode("utf-8"))
            if (
                response.status == 200
                and health.get("farm_api") == 1
                and os.path.realpath(str(health.get("root") or "")) == os.path.realpath(args.root)
            ):
                print("[visitas] API local TBH pronta.", flush=True)
                return 0
        except (OSError, ValueError, urllib.error.URLError):
            pass
        print("[visitas] Nenhum servidor TBH compativel nesta porta.", flush=True)
        return 1

    httpd = arrancar(args.port, os.path.abspath(args.root),
                     os.path.abspath(args.db), args.verbose, args.host)
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
