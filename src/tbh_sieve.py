r"""
SIEVE — integração com a API de scraping (https://scrape.usesieve.com).

O QUE FAZ
  Arranca "runs" de scraping a partir de uma instrução em linguagem natural
  (ex.: "Extrai o texto e o autor de cada citação" numa página pública), segue
  o estado até ao fim e guarda o resultado + session_id em disco para poder
  retomar depois de um crash SEM arrancar um run duplicado (cada run custa
  créditos e o POST /api/scrapes NÃO tem chave de idempotência).

COMO ENCAIXA NO PROJETO
  - HTTP com urllib.request (o MESMO cliente que o resto do toolkit usa — sem
    requests/httpx novos).
  - Persistência em JSON (sieve_runs.json), igual a baus.json/baus_cache.json.
  - CLI por flags (--login / --iniciar / --seguir / ...), igual a tbh_baus.py.
  - Segredo NUNCA em código: variável de ambiente SIEVE_API_KEY ou ficheiro
    .env na raiz (já ignorado pelo git). Sem chave configurada, este módulo
    não faz nada e o resto da app continua exatamente igual.

COMO OBTER A CHAVE (device login aprovado UMA vez pelo utilizador)
  python tbh_sieve.py --login
  -> mostra um link + código; o utilizador aprova no browser; a chave é
     gravada em .env (SIEVE_API_KEY) e nunca é impressa, registada ou commitada.
  Se não estiveres à frente do ecrã, podes separar em dois passos (o código
  expira em ~10 min):
     python tbh_sieve.py --login-codigo   # mostra o link+código
     python tbh_sieve.py --login-poll     # depois de aprovares no browser
  Alternativa: criar a chave em Settings -> API keys no site.

USO RÁPIDO
  python tbh_sieve.py --iniciar "Extrai o texto e o autor de cada citação" \
                      --url https://quotes.toscrape.com
  python tbh_sieve.py --seguir            # retoma os runs guardados até ao fim
  python tbh_sieve.py --estado            # lista os runs guardados
  python tbh_sieve.py --creditos

SEGURANÇA
  A chave tem acesso total à conta e não tem scopes: só no servidor/CLI, nunca
  em browser, bundle, logs, analytics, relatórios de erro ou git.
"""

import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

BASE_URL = "https://scrape.usesieve.com"
API_KEY_ENV = "SIEVE_API_KEY"
ENV_FILE = os.path.join(ROOT, ".env")
RUNS_FILE = os.path.join(ROOT, "var", "sieve_runs.json")
try: os.makedirs(os.path.dirname(RUNS_FILE), exist_ok=True)
except: pass
if not os.path.exists(RUNS_FILE):
    for _alt in [os.path.join(ROOT, "sieve_runs.json"), os.path.join(BASE, "sieve_runs.json")]:
        if os.path.exists(_alt): RUNS_FILE = _alt; break
if not os.path.exists(ENV_FILE):
    for _alt in [os.path.join(BASE, ".env"), os.path.join(ROOT, ".env")]:
        if os.path.exists(_alt): ENV_FILE = _alt; break

# Default é "regular" (política normal de acesso aos sites). "yolo" relaxa essa
# política e só deve ser usado por decisão explícita do utilizador.
COMPLIANCE_MODES = ("conservative", "regular", "yolo")
TABLE_SHAPES = ("long", "wide")

# Só "running" continua a poll. Qualquer outro valor que não seja
# done/refused é tratado como erro (a API não devolve mais nada na poll).
IN_PROGRESS = frozenset({"running"})

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_REFUSED = "refused"

SCHEMA_PASS = "pass"
SCHEMA_PARTIAL = "partial"
SCHEMA_FAIL = "fail"
SCHEMA_NOT_CHECKABLE = "not_checkable"
SCHEMA_NO_ARTIFACT = "no_artifact"

DEFAULT_POLL_START = 5.0      # começa a 5s
DEFAULT_POLL_CAP = 30.0       # tecto ~30s (runs demoram minutos)
DEFAULT_TIMEOUT = 60.0        # sem timeouts curtos
DEFAULT_MAX_RETRIES = 5

_UA = "tbh-toolkit-sieve/1.0"


# =====================================================================  erros
class SieveError(Exception):
    """Erro genérico do sieve. `retryable` diz se vale a pena repetir."""

    def __init__(self, msg, status=None, code=None, retryable=False, body=None):
        super().__init__(msg)
        self.status = status
        self.code = code
        self.retryable = retryable
        self.body = body


class SieveNotConfigured(SieveError):
    """Sem SIEVE_API_KEY: a app tem de continuar a funcionar na mesma."""


class SieveNetworkError(SieveError):
    """Falha de rede/timeout. Num POST isto NÃO pode ser repetido às cegas."""


class SieveHTTPError(SieveError):
    """Resposta HTTP de erro (400/401/402/404/429/5xx)."""


class SieveRefused(SieveError):
    """Run terminou com status 'refused' (nunca chegou a correr)."""

    def __init__(self, run):
        refusal = (run or {}).get("refusal") or {}
        code = refusal.get("code")
        msg = "run recusado" + (": " + str(code) if code else "")
        if code == "quota":
            msg += " (sem créditos no plano)"
        super().__init__(msg, code=code)
        self.run = run
        self.refusal = refusal


class SieveUnknownStatus(SieveError):
    """A poll devolveu um status que não é running/done/refused."""


# =================================================================  segredos
def load_api_key() -> str:
    """Lê a chave: primeiro o ambiente, depois o .env do projeto.
    Devolve "" quando não está configurada (comportamento inalterado)."""
    val = (os.environ.get(API_KEY_ENV) or "").strip()
    if val:
        return val
    return _read_env_file().get(API_KEY_ENV, "").strip()


def _read_env_file() -> dict:
    out = {}
    if not os.path.exists(ENV_FILE):
        return out
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def save_api_key(api_key: str) -> None:
    """Grava SIEVE_API_KEY no .env do projeto (ignorado pelo git) sem imprimir
    nem tocar nas outras linhas. Nunca expõe o valor."""
    api_key = (api_key or "").strip()
    if not api_key:
        raise SieveError("chave vazia — não guardei nada")
    linhas = []
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                linhas = f.read().splitlines()
        except OSError:
            linhas = []
    out, encontrado = [], False
    for line in linhas:
        if line.strip().startswith(API_KEY_ENV + "="):
            out.append(API_KEY_ENV + "=" + api_key)
            encontrado = True
        else:
            out.append(line)
    if not encontrado:
        if out and out[-1].strip():
            out.append("")
        out.append("# sieve (https://scrape.usesieve.com) — servidor/CLI apenas, nunca commit")
        out.append(API_KEY_ENV + "=" + api_key)
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip("\n") + "\n")
    try:  # reduzir a leitura a outros utilizadores (best effort)
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass


def redact(text: str, api_key: str = "") -> str:
    """Remove qualquer chave que apareça por acidente num texto."""
    key = (api_key or load_api_key()).strip()
    if key and key in text:
        text = text.replace(key, "dc_sk_***")
    return text


# ================================================================ transporte
def default_transport(method, url, headers, data, timeout):
    """Único ponto que fala com a rede. Devolve (status, headers, bytes).
    Erros HTTP são valores de retorno; falhas de rede sobem SieveNetworkError."""
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:  # 4xx/5xx: resposta legítima
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, dict(e.headers or {}), body
    except Exception as e:  # timeout, DNS, TLS, ligação recusada, ...
        raise SieveNetworkError(
            "falha de rede em " + method.upper() + " " + url + ": " + str(e)[:160]
        ) from e


def _encode_multipart(fields, file_field, filename, content):
    """Codifica multipart/form-data (documento + campos). Devolve (bytes, content-type)."""
    import uuid
    boundary = "----SieveBoundary" + uuid.uuid4().hex
    out = []
    for k, v in (fields or {}).items():
        out.append(("--" + boundary).encode())
        out.append(('Content-Disposition: form-data; name="%s"' % k).encode())
        out.append(b"")
        out.append(str(v).encode("utf-8"))
    out.append(("--" + boundary).encode())
    out.append(('Content-Disposition: form-data; name="%s"; filename="%s"'
                % (file_field, filename)).encode())
    out.append(b"Content-Type: application/octet-stream")
    out.append(b"")
    out.append(content)
    out.append(("--" + boundary + "--").encode())
    out.append(b"")
    return b"\r\n".join(out), "multipart/form-data; boundary=" + boundary


def _decode_json(raw, default=None):
    if isinstance(raw, (dict, list)):
        return raw
    if not raw:
        return {} if default is None else default
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        return json.loads(raw)
    except (ValueError, TypeError):
        return {} if default is None else default


def _retry_after(headers) -> float:
    """Segundos do Retry-After (segundos ou data HTTP). Fallback: 5s."""
    val = None
    if headers:
        for k, v in headers.items():
            if str(k).lower() == "retry-after":
                val = v
                break
    if not val:
        return 5.0
    try:
        return max(0.0, float(val))
    except (TypeError, ValueError):
        pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(str(val))
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return 5.0


def _map_http_error(status, raw) -> SieveHTTPError:
    body = _decode_json(raw, default={}) or {}
    code = body.get("error") or body.get("code") or body.get("detail")
    detail = body.get("message") or body.get("detail") or body.get("error") or ""
    dicas = {
        400: "pedido inválido — corrige o pedido, não repetir",
        401: "chave em falta/revogada — verifica SIEVE_API_KEY",
        402: "sem créditos — vê GET /api/me/credits (plano, limite, usado, restante)",
        404: "não encontrado ou não é teu",
        409: "há um turno em curso — esperar e reenviar",
        429: "demasiados pedidos — respeita o Retry-After",
    }
    msg = "HTTP " + str(status) + (": " + str(code) if code else "")
    if detail and str(detail) != str(code):
        msg += " — " + str(detail)
    if status in dicas:
        msg += " (" + dicas[status] + ")"
    retryable = status == 429 or 500 <= int(status) < 600
    return SieveHTTPError(msg, status=status, code=code, retryable=retryable, body=body)


# ============================================================ persistência
def runs_load() -> dict:
    if os.path.exists(RUNS_FILE):
        try:
            with open(RUNS_FILE, encoding="utf-8-sig") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("runs"), dict):
                return d
        except Exception:
            pass
    return {"runs": {}}


def runs_save(d: dict) -> None:
    tmp = RUNS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, RUNS_FILE)  # escrita atómica: crash a meio não corrompe


class RunStore:
    """Guarda o estado dos runs em JSON, para retomar a poll após um crash."""

    def __init__(self, path=RUNS_FILE):
        self.path = path

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {"runs": {}}
        try:
            with open(self.path, encoding="utf-8-sig") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("runs"), dict):
                return d
        except Exception:
            pass
        return {"runs": {}}

    def _save(self, d: dict) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.path)

    def upsert(self, session_id: str, fields: dict) -> dict:
        d = self._load()
        rec = d["runs"].get(session_id) or {"session_id": session_id}
        rec.update(fields)
        rec.setdefault("criado_em", datetime.now().isoformat(timespec="seconds"))
        rec["tocado_em"] = datetime.now().isoformat(timespec="seconds")
        d["runs"][session_id] = rec
        self._save(d)
        return rec

    def get(self, session_id: str):
        return self._load()["runs"].get(session_id)

    def all(self) -> dict:
        return self._load()["runs"]

    def unfinished(self) -> list:
        return [r for r in self.all().values()
                if r.get("status") not in (STATUS_DONE, STATUS_REFUSED, "erro")]


# =================================================================  cliente
class SieveClient:
    """Cliente fino da API do sieve. Toda a lógica (URL, headers, retry,
    backoff, mapeamento de erros) vive aqui; a rede fica em `transport`."""

    def __init__(self, api_key=None, base_url=BASE_URL, transport=None,
                 sleep=None, timeout=DEFAULT_TIMEOUT, max_retries=DEFAULT_MAX_RETRIES,
                 store=None, on_log=None):
        self.api_key = api_key if api_key is not None else load_api_key()
        self.base_url = base_url.rstrip("/")
        self.transport = transport or default_transport
        self.sleep = sleep or time.sleep
        self.timeout = timeout
        self.max_retries = max_retries
        self.store = store
        self.on_log = on_log

    def __repr__(self):  # nunca expor a chave em repr/logs
        estado = "configurado" if self.api_key else "sem chave"
        return "SieveClient(base_url=%r, %s)" % (self.base_url, estado)

    # --------------------------------------------------------------- base
    def configured(self) -> bool:
        return bool(self.api_key)

    def _log(self, msg):
        if self.on_log:
            self.on_log(redact(str(msg), self.api_key))

    def _auth_headers(self, extra=None):
        if not self.api_key:
            raise SieveNotConfigured(
                "SIEVE_API_KEY não está configurada — corre: python tbh_sieve.py --login"
            )
        h = {"Authorization": "Bearer " + self.api_key,
             "Accept": "application/json",
             "User-Agent": _UA}
        if extra:
            h.update(extra)
        return h

    def request(self, method, path, body=None, *, retry_network=None, timeout=None,
                raw_body=None, content_type=None):
        """Faz um pedido. `retry_network` decide se uma falha de rede é repetida:
        por padrão só em GET. Um POST cujo timeout deixa dúvida NÃO é repetido."""
        method = method.upper()
        if retry_network is None:
            retry_network = method == "GET"
        url = self.base_url + path
        headers = self._auth_headers()
        data = None
        if raw_body is not None:
            data = raw_body
            headers["Content-Type"] = content_type or "application/octet-stream"
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        to = timeout or self.timeout
        tentativa = 0
        while True:
            tentativa += 1
            try:
                status, hdrs, raw = self.transport(method, url, headers, data, to)
            except SieveNetworkError as e:
                if not retry_network or tentativa > self.max_retries:
                    raise
                self._backoff(tentativa, None)
                continue
            status = int(status)
            if 200 <= status < 300:
                return _decode_json(raw)
            if status == 429 or 500 <= status < 600:
                if tentativa > self.max_retries:
                    raise _map_http_error(status, raw)
                self._backoff(tentativa, _retry_after(hdrs))
                continue
            raise _map_http_error(status, raw)

    def _backoff(self, tentativa, retry_after):
        if retry_after is not None:
            espera = float(retry_after)
        else:
            espera = min(DEFAULT_POLL_CAP, 2.0 ** (tentativa - 1))
        self._log("  retry em " + str(round(espera, 1)) + "s (tentativa " + str(tentativa) + ")")
        self.sleep(espera)

    # ------------------------------------------------------------- scrapes
    def start_scrape(self, instruction, *, target_urls=None, fields=None, schema=None,
                     output_schema=None, table_shape=None, compliance_mode="regular",
                     file_path=None):
        """POST /api/scrapes. Devolve a resposta 202. Persiste o session_id no
        store (se houver) ANTES de devolver, para retomar sem duplicar."""
        if not str(instruction or "").strip():
            raise SieveError("instrução obrigatória (linguagem natural)")
        if compliance_mode not in COMPLIANCE_MODES:
            raise SieveError("compliance_mode inválido: " + str(compliance_mode))
        if table_shape is not None and table_shape not in TABLE_SHAPES:
            raise SieveError("table_shape inválido: " + str(table_shape))
        if output_schema is not None:
            raw = json.dumps(output_schema, ensure_ascii=False).encode("utf-8")
            if len(raw) > 32 * 1024:
                raise SieveError("output_schema > 32KB (limite da API)")
        body = {"instruction": instruction, "compliance_mode": compliance_mode}
        if target_urls:
            body["target_urls"] = list(target_urls)
        if fields:
            body["fields"] = list(fields)
        if schema is not None:
            body["schema"] = schema
        if output_schema is not None:
            body["output_schema"] = output_schema
        if table_shape is not None:
            body["table_shape"] = table_shape
        if file_path is not None:
            with open(file_path, "rb") as fh:
                conteudo = fh.read()
            nome = os.path.basename(file_path)
            corpo_multi, ctype = _encode_multipart(
                {k: (json.dumps(v) if not isinstance(v, str) else v) for k, v in body.items()},
                "file", nome, conteudo)
            resp = self.request("POST", "/api/scrapes", retry_network=False,
                                raw_body=corpo_multi, content_type=ctype)
        else:
            resp = self.request("POST", "/api/scrapes", body, retry_network=False)
        sid = resp.get("session_id")
        if not sid:
            raise SieveError("resposta 202 sem session_id: " + str(resp)[:200])
        if self.store:
            self.store.upsert(str(sid), {
                "status": resp.get("status") or STATUS_QUEUED,
                "status_raw": resp.get("status"),
                "instruction": instruction,
                "target_urls": list(target_urls or []),
                "compliance_mode": compliance_mode,
                "poll": resp.get("poll"),
            })
        return resp

    def get_scrape(self, session_id):
        """GET /api/scrapes/<id>. GET pode ser repetido com backoff."""
        return self.request("GET", "/api/scrapes/" + urllib.parse.quote(str(session_id)))

    def poll_scrape(self, session_id, *, start=DEFAULT_POLL_START, cap=DEFAULT_POLL_CAP,
                    factor=1.6, on_update=None, max_checks=None, sleep=None):
        """Segue o run até done/refused. Intervalo 5s -> ~30s. Sem timeout curto."""
        dormir = sleep or self.sleep
        intervalo = float(start)
        checks = 0
        while True:
            run = self.get_scrape(session_id)
            checks += 1
            if on_update:
                on_update(run)
            self._record(session_id, run)
            status = run.get("status")
            if status == STATUS_DONE:
                return run
            if status == STATUS_REFUSED:
                raise SieveRefused(run)
            if status not in IN_PROGRESS:
                raise SieveUnknownStatus(
                    "status desconhecido na poll: " + repr(status) + " (run " + str(session_id) + ")"
                )
            if max_checks is not None and checks >= max_checks:
                raise SieveError("limite de verificações atingido sem terminar (run " + str(session_id) + ")")
            dormir(intervalo)
            intervalo = min(float(cap), intervalo * factor)

    def _record(self, session_id, run):
        if not self.store or not isinstance(run, dict):
            return
        self.store.upsert(str(session_id), {
            "status": run.get("status"),
            "turns": run.get("turns"),
            "summary": run.get("summary"),
            "files": run.get("files"),
            "schema_conformance": run.get("schema_conformance"),
            "refusal": run.get("refusal"),
        })

    # ------------------------------------------------------------ turnos
    def send_message(self, session_id, instruction, **body):
        """Follow-up: regista os turnos ANTES, envia, e só devolve quando o run
        está done E os turnos avançaram (senão líamos a resposta anterior)."""
        antes = self.get_scrape(session_id)
        turns_before = int((antes or {}).get("turns") or 0)
        payload = dict(body)
        payload["instruction"] = instruction
        while True:
            try:
                self.request("POST", "/api/scrapes/%s/messages" % urllib.parse.quote(str(session_id)),
                             payload, retry_network=False)
                break
            except SieveHTTPError as e:
                if e.status == 409:  # turno em curso: esperar e reenviar
                    self._log("  409: turno em curso, espero e reenvio")
                    self.sleep(5.0)
                    continue
                raise
        return self.poll_followup(session_id, turns_before)

    def poll_followup(self, session_id, turns_before, **kw):
        """Igual a poll_scrape mas exige que os turnos tenham avançado."""
        def _avancou(run):
            return run.get("status") == STATUS_DONE and int(run.get("turns") or 0) > int(turns_before)
        return self._poll_until(session_id, _avancou, **kw)

    def _poll_until(self, session_id, aceitar, *, start=DEFAULT_POLL_START,
                    cap=DEFAULT_POLL_CAP, factor=1.6, on_update=None,
                    max_checks=None, sleep=None):
        dormir = sleep or self.sleep
        intervalo = float(start)
        checks = 0
        while True:
            run = self.get_scrape(session_id)
            checks += 1
            if on_update:
                on_update(run)
            self._record(session_id, run)
            status = run.get("status")
            if status == STATUS_REFUSED:
                raise SieveRefused(run)
            if status not in IN_PROGRESS and status != STATUS_DONE:
                raise SieveUnknownStatus("status desconhecido: " + repr(status))
            if aceitar(run):
                return run
            if max_checks is not None and checks >= max_checks:
                raise SieveError("limite de verificações atingido (run " + str(session_id) + ")")
            dormir(intervalo)
            intervalo = min(float(cap), intervalo * factor)

    # ------------------------------------------------------------- ficheiros
    def file_url(self, f) -> str:
        """files[].url é relativo: prefixa a base."""
        u = f.get("url") if isinstance(f, dict) else f
        u = str(u or "")
        if u.startswith("http://") or u.startswith("https://"):
            return u
        return self.base_url + (u if u.startswith("/") else "/" + u)

    def download_file(self, f, dest_dir, filename=None) -> str:
        """Descarrega um ficheiro entregue, com o header Bearer."""
        url = self.file_url(f)
        nome = filename or (f.get("name") if isinstance(f, dict) else None) or url.rsplit("/", 1)[-1]
        nome = re.sub(r"[^\w.\-]+", "_", str(nome)) or "sieve_file"
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, nome)
        headers = self._auth_headers()
        status, _hdrs, raw = self.transport("GET", url, headers, None, self.timeout)
        if int(status) >= 400:
            raise _map_http_error(status, raw)
        with open(dest, "wb") as fh:
            fh.write(raw)
        return dest

    def download_files(self, run, dest_dir) -> list:
        return [self.download_file(f, dest_dir) for f in (run.get("files") or [])]

    # -------------------------------------------------------------- créditos
    def credits(self):
        return self.request("GET", "/api/me/credits")

    # -------------------------------------------------------------- monitores
    def create_monitor(self, session_id, instruction, schedule_kind, *,
                       schedule_time=None, schedule_timezone=None, email_recipients=None,
                       webhook_url=None, notify_only_if_changed=None):
        corpo = {"instruction": instruction, "schedule_kind": schedule_kind}
        for k, v in (("schedule_time", schedule_time),
                     ("schedule_timezone", schedule_timezone),
                     ("email_recipients", email_recipients),
                     ("webhook_url", webhook_url),
                     ("notify_only_if_changed", notify_only_if_changed)):
            if v is not None:
                corpo[k] = v
        return self.request("POST", "/api/scrapes/%s/monitor" % urllib.parse.quote(str(session_id)),
                            corpo, retry_network=False)

    def list_monitors(self, session_id):
        """O id do monitor lê-se de /api/sessions/<session_id>/monitors."""
        return self.request("GET", "/api/sessions/%s/monitors" % urllib.parse.quote(str(session_id)))

    def trigger_monitor(self, monitor_id):
        return self.request("POST", "/api/monitors/%s/runs" % urllib.parse.quote(str(monitor_id)),
                            {}, retry_network=False)

    def get_monitor_run(self, monitor_id, run_id):
        return self.request("GET", "/api/monitors/%s/runs/%s"
                            % (urllib.parse.quote(str(monitor_id)), urllib.parse.quote(str(run_id))))

    def poll_monitor_run(self, monitor_id, run_id, *, start=DEFAULT_POLL_START,
                         cap=DEFAULT_POLL_CAP, factor=1.6, sleep=None, on_update=None,
                         max_checks=None):
        """Segue um run de monitor até changed/no_change/failed."""
        terminado = {"changed", "no_change", "failed"}
        dormir = sleep or self.sleep
        intervalo = float(start)
        checks = 0
        while True:
            r = self.get_monitor_run(monitor_id, run_id)
            checks += 1
            if on_update:
                on_update(r)
            status = r.get("status")
            if status in terminado:
                return r
            if status not in IN_PROGRESS and status != STATUS_QUEUED:
                raise SieveUnknownStatus("status de monitor desconhecido: " + repr(status))
            if max_checks is not None and checks >= max_checks:
                raise SieveError("limite de verificações no monitor " + str(monitor_id))
            dormir(intervalo)
            intervalo = min(float(cap), intervalo * factor)

    def monitor_results(self, monitor_id, run_id):
        return self.request("GET", "/api/monitors/%s/runs/%s/results"
                            % (urllib.parse.quote(str(monitor_id)), urllib.parse.quote(str(run_id))))

    def monitor_results_param(self, monitor_id, params):
        """GET /api/monitors/<id>/results?<param>=<value>. Cache hits não gastam
        créditos; controla com _max_age (segundos) ou _fresh=1."""
        q = urllib.parse.urlencode({k: ("" if v is None else v) for k, v in (params or {}).items()})
        return self.request("GET", "/api/monitors/%s/results%s"
                            % (urllib.parse.quote(str(monitor_id)), ("?" + q) if q else ""))

    def monitor_runs(self, monitor_id):
        """Reconciliação: lista os runs do monitor (entregas perdidas nunca são
        reenviadas, por isso é preciso ir buscar o estado)."""
        return self.request("GET", "/api/monitors/%s/runs" % urllib.parse.quote(str(monitor_id)))


# ============================================================ conformidade
def schema_status(run) -> str:
    """Classifica o schema_conformance de um run done.
    pass ok; partial = sem violações mas faltam colunas; fail = não conforma
    mesmo após reparação; not_checkable/no_artifact = nada verificável."""
    conf = (run or {}).get("schema_conformance")
    if not isinstance(conf, dict):
        return SCHEMA_NO_ARTIFACT
    status = conf.get("status")
    if status in (SCHEMA_PASS, SCHEMA_PARTIAL, SCHEMA_FAIL,
                  SCHEMA_NOT_CHECKABLE, SCHEMA_NO_ARTIFACT):
        return status
    return SCHEMA_NO_ARTIFACT


def is_clean(run) -> bool:
    """True só quando os dados podem ser apresentados como limpos."""
    return schema_status(run) in (SCHEMA_PASS, SCHEMA_NOT_CHECKABLE, SCHEMA_NO_ARTIFACT)


def schema_warning(run):
    """Aviso a mostrar quando os dados NÃO podem ser apresentados como limpos."""
    st = schema_status(run)
    if st == SCHEMA_PARTIAL:
        return "conformidade parcial: sem violações, mas faltam colunas declaradas"
    if st == SCHEMA_FAIL:
        return "conformidade FALHOU após reparação — NÃO apresentar como dados limpos"
    return ""


# =========================================================== device login
def device_code(client_name="tbh-toolkit (TaskBarHero)", *, transport=None,
                base_url=BASE_URL, timeout=DEFAULT_TIMEOUT):
    """Passo 1: pede um código de dispositivo. Não abre nada nem aprova nada."""
    tr = transport or default_transport
    url = base_url.rstrip("/") + "/api/auth/device/code"
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": _UA}
    data = json.dumps({"client_name": client_name}).encode("utf-8")
    status, _h, raw = tr("POST", url, headers, data, timeout)
    if int(status) >= 400:
        raise _map_http_error(status, raw)
    return _decode_json(raw)


def device_token(device_code_value, *, transport=None, base_url=BASE_URL, timeout=DEFAULT_TIMEOUT):
    """Passo 3 (uma tentativa): POST /api/auth/device/token."""
    tr = transport or default_transport
    url = base_url.rstrip("/") + "/api/auth/device/token"
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": _UA}
    data = json.dumps({"device_code": device_code_value}).encode("utf-8")
    status, _h, raw = tr("POST", url, headers, data, timeout)
    body = _decode_json(raw, default={}) or {}
    if int(status) == 200:
        return body
    if int(status) == 400:
        return {"error": body.get("error") or "unknown"}
    raise _map_http_error(status, raw)


LOGIN_FILE = os.path.join(ROOT, "var", "sieve_login.json")
if not os.path.exists(LOGIN_FILE):
    for _alt in [os.path.join(ROOT, "sieve_login.json"), os.path.join(BASE, "sieve_login.json")]:
        if os.path.exists(_alt): LOGIN_FILE = _alt; break


def login_state_save(cod: dict) -> None:
    """Guarda o device_code pendente para poder aprovar mais tarde (o código
    expira em ~10 min). Não é a chave — só o código de dispositivo."""
    d = {"device_code": cod.get("device_code"), "user_code": cod.get("user_code"),
         "verification_uri_complete": (cod.get("verification_uri_complete")
                                       or cod.get("verification_uri")),
         "interval": cod.get("interval") or 5, "expires_in": cod.get("expires_in") or 600,
         "criado_em": time.time()}
    tmp = LOGIN_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, LOGIN_FILE)
    try:
        os.chmod(LOGIN_FILE, 0o600)
    except OSError:
        pass


def login_state_load():
    if not os.path.exists(LOGIN_FILE):
        return None
    try:
        with open(LOGIN_FILE, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


LOGIN_HELP = """\
AVISO: aprova SÓ um código que TU começaste. Se não pediste isto,
       não aproves — pode ser phishing (alguém a iniciar o login)."""


def _mostrar_codigo(cod: dict, mostrar) -> None:
    completo = cod.get("verification_uri_complete") or cod.get("verification_uri") or ""
    intervalo = float(cod.get("interval") or 5)
    expires_in = float(cod.get("expires_in") or 600)
    mostrar("")
    mostrar("== APROVAR O ACESSO AO SIEVE (uma vez) ==")
    mostrar("1) Abre este link no browser: " + str(completo))
    mostrar("2) Confirma que o código mostrado é: " + str(cod.get("user_code") or "?"))
    mostrar("3) Entra (Google ou email), verifica que o código é o mesmo e clica em Approve.")
    mostrar("")
    mostrar(LOGIN_HELP)
    mostrar("O código expira em ~" + str(int(expires_in // 60)) + " min e só serve uma vez.")
    mostrar("(podes aprovar já; a poll está à espera a cada " + str(int(intervalo)) + "s)")
    mostrar("")


def device_login_poll(device_code_value, *, interval=5.0, expires_in=600.0, transport=None,
                      sleep=None, show=None, store_key=True, base_url=BASE_URL,
                      now=None, timeout=DEFAULT_TIMEOUT):
    """Passo 3 (bloco): faz poll até sucesso/negação/expiração e grava a chave.
    NUNCA imprime a chave."""
    tr = transport or default_transport
    dormir = sleep or time.sleep
    mostrar = show or (lambda m: print(m))
    relogio = now or time.time
    fim = relogio() + float(expires_in)
    intervalo = float(interval)
    while True:
        if relogio() > fim:
            raise SieveError("código expirado — recomeça com: python tbh_sieve.py --login")
        resp = device_token(device_code_value, transport=tr, base_url=base_url, timeout=timeout)
        if resp.get("api_key"):
            api_key = resp["api_key"]
            if store_key:
                save_api_key(api_key)
            try:
                os.remove(LOGIN_FILE)
            except OSError:
                pass
            mostrar("Aprovado. Chave guardada em .env como " + API_KEY_ENV
                    + " (não é impressa por segurança).")
            return api_key
        err = resp.get("error")
        if err == "authorization_pending":
            pass
        elif err == "slow_down":
            intervalo += 5
        elif err == "access_denied":
            raise SieveError("o utilizador recusou o acesso — a parar")
        elif err == "expired_token":
            raise SieveError("código expirado — recomeça com: python tbh_sieve.py --login")
        else:
            raise SieveError("erro no device login: " + str(err))
        dormir(intervalo)


def device_login(client_name="tbh-toolkit (TaskBarHero)", *, transport=None,
                 sleep=None, show=None, store_key=True, base_url=BASE_URL,
                 now=None, timeout=DEFAULT_TIMEOUT):
    """Fluxo completo: mostra o link+código, faz poll até sucesso/negação.
    Devolve a api_key (e grava-a no .env se store_key). NUNCA imprime a chave."""
    tr = transport or default_transport
    mostrar = show or (lambda m: print(m))
    cod = device_code(client_name, transport=tr, base_url=base_url, timeout=timeout)
    device_code_value = cod.get("device_code")
    if not device_code_value:
        raise SieveError("resposta sem device_code: " + str(cod)[:200])
    _mostrar_codigo(cod, mostrar)
    return device_login_poll(device_code_value,
                             interval=float(cod.get("interval") or 5),
                             expires_in=float(cod.get("expires_in") or 600),
                             transport=tr, sleep=sleep, show=mostrar,
                             store_key=store_key, base_url=base_url, now=now, timeout=timeout)


# ============================================================= webhooks
def webhook_secret_ok(provided, expected) -> bool:
    """Compara o segredo do caminho em tempo constante (evita timing attacks)."""
    a = (provided or "").encode("utf-8")
    b = (expected or "").encode("utf-8")
    if not a or not b:
        return False
    return hmac.compare_digest(a, b)


def webhook_dedupe_key(monitor_id, run_id) -> str:
    return str(monitor_id) + ":" + str(run_id)


class WebhookStore:
    """Deduplica entregas em (monitor_id, run_id). Os webhooks são enviados uma
    vez e nunca reenviados, mas podem repetir-se — e o receiver tem de ser idempotente."""

    def __init__(self, path=None):
        self.path = path or os.path.join(ROOT, "var", "sieve_webhooks.json")
        if not os.path.exists(self.path):
            for _alt in [os.path.join(ROOT, "sieve_webhooks.json"), os.path.join(BASE, "sieve_webhooks.json")]:
                if os.path.exists(_alt): self.path = _alt; break

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8-sig") as f:
                    d = json.load(f)
                if isinstance(d, dict) and isinstance(d.get("vistos"), dict):
                    return d
            except Exception:
                pass
        return {"vistos": {}}

    def _save(self, d):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.path)

    def seen(self, monitor_id, run_id) -> bool:
        return webhook_dedupe_key(monitor_id, run_id) in self._load()["vistos"]

    def mark(self, monitor_id, run_id, extra=None):
        d = self._load()
        d["vistos"][webhook_dedupe_key(monitor_id, run_id)] = {
            "quando": datetime.now().isoformat(timespec="seconds"),
            **(extra or {}),
        }
        self._save(d)


def handle_webhook(payload, *, path_secret, expected_secret, store, fetch_results=None,
                   schedule_async=None) -> dict:
    """Núcleo do receiver (puro/testável). Regras que a API do sieve impõe:
    - URL público https com segredo no caminho, comparado em tempo constante;
    - responder 2xx em <10s e processar assíncrono;
    - deduplicar em (monitor_id, run_id);
    - ir buscar results_url com a chave antes de agir (e sempre que data.truncated).
    Devolve {"http": <int>, "motivo": str}."""
    if not webhook_secret_ok(path_secret, expected_secret):
        return {"http": 404, "motivo": "segredo inválido"}
    payload = payload or {}
    data = payload.get("data") or {}
    monitor_id = payload.get("monitor_id") or data.get("monitor_id")
    run_id = payload.get("run_id") or data.get("run_id")
    if not monitor_id or not run_id:
        return {"http": 400, "motivo": "sem monitor_id/run_id"}
    if store.seen(monitor_id, run_id):
        return {"http": 200, "motivo": "duplicado ignorado", "duplicado": True}
    store.mark(monitor_id, run_id)
    # processamento assíncrono: devolve 2xx já, o trabalho continua fora do request
    trabalho = {"monitor_id": monitor_id, "run_id": run_id,
                "event": payload.get("event"), "data": data}

    def _processar():
        if fetch_results and (data.get("results_url") or data.get("truncated")):
            try:
                trabalho["results"] = fetch_results(monitor_id, run_id, data.get("results_url"))
            except Exception as e:  # nunca deixar rebentar o worker
                trabalho["erro"] = str(e)[:200]
        return trabalho

    if schedule_async:
        schedule_async(_processar)
    else:
        _processar()
    return {"http": 200, "motivo": "aceite", "trabalho": trabalho}


# ===================================================================== CLI
def _imprimir_estado(runs: dict) -> None:
    if not runs:
        print("(nenhum run guardado em sieve_runs.json)")
        return
    for sid, r in runs.items():
        print("  " + str(sid) + "  [" + str(r.get("status") or "?") + "]"
              + (" turnos=" + str(r.get("turns")) if r.get("turns") is not None else "")
              + ("  " + str(r.get("summary"))[:80] if r.get("summary") else ""))
        print("     " + str(r.get("instruction") or "")[:100])


def cli() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return

    if a[0] == "--login":
        nome = "tbh-toolkit (TaskBarHero)"
        if "--nome" in a and a.index("--nome") + 1 < len(a):
            nome = a[a.index("--nome") + 1]
        try:
            device_login(nome)
        except SieveError as e:
            print("ERRO: " + redact(str(e)))
        return

    if a[0] == "--login-codigo":
        nome = "tbh-toolkit (TaskBarHero)"
        if "--nome" in a and a.index("--nome") + 1 < len(a):
            nome = a[a.index("--nome") + 1]
        try:
            cod = device_code(nome)
            login_state_save(cod)
            _mostrar_codigo(cod, print)
            print("Quando aprovares no browser, corre: python tbh_sieve.py --login-poll")
        except SieveError as e:
            print("ERRO: " + redact(str(e)))
        return

    if a[0] == "--login-poll":
        st = login_state_load()
        if not st or not st.get("device_code"):
            print("não há código pendente — corre: python tbh_sieve.py --login-codigo")
            return
        restante = float(st.get("expires_in") or 600) - (time.time() - float(st.get("criado_em") or 0))
        if restante <= 0:
            print("código expirado — recomeça com: python tbh_sieve.py --login-codigo")
            return
        try:
            device_login_poll(st["device_code"], interval=float(st.get("interval") or 5),
                              expires_in=restante)
        except SieveError as e:
            print("ERRO: " + redact(str(e)))
        return

    if a[0] == "--creditos":
        c = SieveClient()
        if not c.configured():
            print("SIEVE_API_KEY em falta — corre: python tbh_sieve.py --login")
            return
        try:
            print(json.dumps(c.credits(), indent=1, ensure_ascii=False))
        except SieveError as e:
            print("ERRO: " + redact(str(e)))
        return

    if a[0] == "--estado":
        _imprimir_estado(runs_load()["runs"])
        return

    if a[0] == "--iniciar":
        if len(a) < 2:
            print('uso: python tbh_sieve.py --iniciar "instrução" [--url U ...] '
                  '[--campo C ...] [--schema ficheiro.json] [--modo regular]')
            return
        instr = a[1]
        urls, campos, schema, modo = [], [], None, "regular"
        i = 2
        while i < len(a):
            if a[i] == "--url" and i + 1 < len(a):
                urls.append(a[i + 1]); i += 2
            elif a[i] == "--campo" and i + 1 < len(a):
                campos.append(a[i + 1]); i += 2
            elif a[i] == "--schema" and i + 1 < len(a):
                with open(a[i + 1], encoding="utf-8") as fh:
                    schema = json.load(fh)
                i += 2
            elif a[i] == "--modo" and i + 1 < len(a):
                modo = a[i + 1]; i += 2
            else:
                i += 1
        cli_sieve = SieveClient(store=RunStore())
        if not cli_sieve.configured():
            print("SIEVE_API_KEY em falta — corre: python tbh_sieve.py --login")
            return
        print("(cada run aceite gasta créditos — o POST não é repetido em timeouts)")
        try:
            r = cli_sieve.start_scrape(instr, target_urls=urls, fields=campos,
                                       output_schema=schema, compliance_mode=modo)
            print("run aceite (202): session_id=" + str(r.get("session_id")))
            print("segue com: python tbh_sieve.py --seguir")
        except SieveError as e:
            print("ERRO: " + redact(str(e)))
        return

    if a[0] == "--seguir":
        cli_sieve = SieveClient(store=RunStore())
        if not cli_sieve.configured():
            print("SIEVE_API_KEY em falta — corre: python tbh_sieve.py --login")
            return
        store = cli_sieve.store
        alvos = ([a[1]] if len(a) > 1 else
                 [r["session_id"] for r in store.unfinished()])
        if not alvos:
            print("(nada para seguir)")
            return
        for sid in alvos:
            print("a seguir " + str(sid) + " ...")
            try:
                run = cli_sieve.poll_scrape(sid, on_update=lambda r: print("  status: " + str(r.get("status"))))
                st = schema_status(run)
                print("  done (" + st + ")" + (" — " + schema_warning(run) if schema_warning(run) else ""))
                for f in (run.get("files") or []):
                    print("  ficheiro: " + str(f.get("name")) + " (" + str(f.get("size")) + "B)")
            except SieveRefused as e:
                print("  recusado: " + str(e.code or "?"))
            except SieveError as e:
                print("  erro: " + redact(str(e)))
        return

    if a[0] == "--mensagem" and len(a) > 2:
        cli_sieve = SieveClient(store=RunStore())
        if not cli_sieve.configured():
            print("SIEVE_API_KEY em falta — corre: python tbh_sieve.py --login")
            return
        try:
            run = cli_sieve.send_message(a[1], a[2])
            print("turno concluído (turnos=" + str(run.get("turns")) + ")")
        except SieveError as e:
            print("ERRO: " + redact(str(e)))
        return

    if a[0] == "--descarregar" and len(a) > 1:
        cli_sieve = SieveClient(store=RunStore())
        if not cli_sieve.configured():
            print("SIEVE_API_KEY em falta — corre: python tbh_sieve.py --login")
            return
        dest = os.path.join(ROOT, "var", "sieve_resultados", str(a[1]))
        if not os.path.exists(os.path.join(ROOT, "var", "sieve_resultados")) and os.path.exists(os.path.join(BASE, "sieve_resultados")):
            dest = os.path.join(BASE, "sieve_resultados", str(a[1]))
        try:
            run = cli_sieve.get_scrape(a[1])
            caminhos = cli_sieve.download_files(run, dest)
            for p in caminhos:
                print("guardado: " + p)
        except SieveError as e:
            print("ERRO: " + redact(str(e)))
        return

    print("opção desconhecida. vê: python tbh_sieve.py --help")


if __name__ == "__main__":
    cli()
