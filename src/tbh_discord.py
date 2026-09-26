"""Discord webhook delivery for Taskbar Hero farm alerts.

The webhook URL is a bearer secret: keep it in the ignored project .env file or
an environment variable, never in generated HTML, logs, command-line arguments,
or tracked source files.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, ".env")
WEBHOOK_ENV = "TBH_DISCORD_WEBHOOK_URL"
MENTION_ENV = "TBH_DISCORD_MENTION_ID"
ENABLED_FILE = os.path.join(ROOT, "var", "farm_discord_enabled")
REQUEST_TIMEOUT_SECONDS = 8
MAX_ATTEMPTS = 3


def discord_enabled(enabled_file: str = ENABLED_FILE) -> bool:
    """Read the saved opt-in first; an explicit choice always beats environment defaults."""
    try:
        with open(enabled_file, encoding="utf-8") as fh:
            saved = fh.read().strip().casefold()
        return saved in {"1", "true", "yes", "s", "sim", "on"}
    except FileNotFoundError:
        pass
    except OSError:
        # Fail closed: an unreadable preference must never turn on notifications.
        return False

    override = os.environ.get("TBH_DISCORD_ENABLED")
    if override is not None:
        return override.strip().casefold() in {"1", "true", "yes", "s", "sim", "on"}
    return False


def set_discord_enabled(enabled: bool, enabled_file: str = ENABLED_FILE) -> None:
    """Persist whether this installation has opted into farm notifications."""
    directory = os.path.dirname(os.path.abspath(enabled_file))
    os.makedirs(directory, exist_ok=True)
    temp_path = f"{enabled_file}.{os.getpid()}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("1\n" if enabled else "0\n")
        os.replace(temp_path, enabled_file)
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
    try:
        os.chmod(enabled_file, 0o600)
    except OSError:
        pass


def _read_setting(name: str, env_file: str = ENV_FILE) -> str:
    value = (os.environ.get(name) or "").strip()
    if value:
        return value
    try:
        with open(env_file, encoding="utf-8-sig") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].lstrip()
                key, separator, raw_value = line.partition("=")
                if not separator or key.strip() != name:
                    continue
                value = raw_value.strip()
                if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                    value = value[1:-1]
                return value
    except OSError:
        pass
    return ""


def discord_settings(env_file: str = ENV_FILE) -> tuple[str, str]:
    """Return webhook URL and optional allowed user ID without logging either."""
    return _read_setting(WEBHOOK_ENV, env_file), _read_setting(MENTION_ENV, env_file)


def normalise_user_id(value: str) -> str:
    value = str(value or "").strip()
    if value.startswith("<@") and value.endswith(">"):
        value = value[2:-1]
        if value.startswith("!"):
            value = value[1:]
    return value


def valid_discord_user_id(value: str) -> bool:
    value = normalise_user_id(value)
    return value.isascii() and value.isdigit() and 17 <= len(value) <= 20


def valid_webhook_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(str(value or "").strip())
        port = parsed.port
    except ValueError:
        return False
    parts = parsed.path.split("/")
    return bool(
        parsed.scheme.lower() == "https"
        and parsed.hostname
        and parsed.hostname.lower() == "discord.com"
        and not parsed.username
        and not parsed.password
        and port in (None, 443)
        and not parsed.query
        and not parsed.fragment
        and len(parts) == 5
        and parts[1:3] == ["api", "webhooks"]
        and parts[3].isascii()
        and parts[3].isdigit()
        and 17 <= len(parts[3]) <= 20
        and bool(parts[4])
        and all(ch.isalnum() or ch in "._-" for ch in parts[4])
    )


def save_discord_settings(webhook_url: str, mention_id: str,
                          env_file: str = ENV_FILE) -> None:
    """Write webhook settings to .env, preserving unrelated local configuration."""
    webhook_url = str(webhook_url or "").strip()
    mention_id = normalise_user_id(mention_id)
    if not valid_webhook_url(webhook_url):
        raise ValueError("URL de webhook Discord invalido; cria/renova o webhook no canal de destino.")
    if mention_id and not valid_discord_user_id(mention_id):
        raise ValueError("ID de utilizador Discord invalido; usa o ID numerico ou deixa vazio.")

    settings = {WEBHOOK_ENV: webhook_url, MENTION_ENV: mention_id}
    try:
        with open(env_file, encoding="utf-8-sig") as fh:
            existing_lines = fh.read().splitlines()
    except FileNotFoundError:
        existing_lines = []

    output = []
    written = set()
    for raw_line in existing_lines:
        line = raw_line.strip()
        candidate = line[7:].lstrip() if line.startswith("export ") else line
        key = candidate.partition("=")[0].strip()
        if key in settings:
            if key not in written:
                output.append(f"{key}={settings[key]}")
                written.add(key)
        else:
            output.append(raw_line)
    for key, value in settings.items():
        if key not in written:
            output.append(f"{key}={value}")

    directory = os.path.dirname(os.path.abspath(env_file))
    os.makedirs(directory, exist_ok=True)
    temp_path = f"{env_file}.{os.getpid()}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(output).rstrip("\n") + "\n")
        os.replace(temp_path, env_file)
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
    try:
        os.chmod(env_file, 0o600)
    except OSError:
        pass


def build_payload(hit: dict, mention_id: str = "", test: bool = False) -> dict:
    user_id = normalise_user_id(mention_id)
    if not valid_discord_user_id(user_id):
        user_id = ""
    mention = f"<@{user_id}> " if user_id else ""
    if hit.get("type") == "zone_status":
        zone_status = str(hit.get("status") or "verify")
        headings = {
            "correct": "✅ ZONA CORRETA",
            "incorrect": "🚨 ZONA INCORRETA — VERIFICA ZONA",
            "verify": "⚠️ VERIFICA ZONA",
        }
        content = (
            f"{mention}{headings.get(zone_status, headings['verify'])}\n"
            f"**Item:** {str(hit.get('item') or hit.get('name') or '?')}\n"
            f"**Conta:** {str(hit.get('conta') or '?')}\n"
            f"**Zona no save:** {str(hit.get('zone') or 'desconhecida')}"
        )
        if hit.get("expected"):
            content += f"\n**Zonas conhecidas do item:** {str(hit['expected'])}"
        if hit.get("reason"):
            content += f"\n{str(hit['reason'])}"
    else:
        heading = "🧪 TESTE DO ALERTA DE FARM" if test else "🎉 ITEM ENCONTRADO!"
        content = (
        f"{mention}{heading}\n"
        f"**Item:** {str(hit.get('name') or '?')}\n"
        f"**Conta:** {str(hit.get('conta') or '?')}\n"
            f"**Quantidade nova:** {hit.get('qtd', 1)}"
        )
    return {
        "content": content[:2000],
        "allowed_mentions": {
            "parse": [],
            "users": [user_id] if user_id else [],
            "roles": [],
            "replied_user": False,
        },
    }


def post_webhook(url: str, payload: dict, timeout: float = REQUEST_TIMEOUT_SECONDS) -> int:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "TBH-Farm-Alerts/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return int(response.status)


def send_alert(hit: dict, *, webhook_url: str | None = None,
               mention_id: str | None = None, transport=None,
               test: bool = False, sleep=None) -> bool:
    """Send once; retry only explicit 429 responses, never ambiguous POST failures."""
    if not discord_enabled():
        return False
    configured_url, configured_user = discord_settings()
    url = configured_url if webhook_url is None else str(webhook_url).strip()
    user_id = configured_user if mention_id is None else str(mention_id).strip()
    if not url:
        print(f"[FARM] Discord nao configurado ({WEBHOOK_ENV} em .env).", flush=True)
        return False
    if not valid_webhook_url(url):
        print("[FARM] URL do webhook Discord invalido; nada enviado.", flush=True)
        return False
    if user_id and not valid_discord_user_id(user_id):
        print("[FARM] ID de mencao Discord invalido; nada enviado.", flush=True)
        return False

    sleeper = sleep or time.sleep
    payload = build_payload(hit, user_id, test=test)
    sender = transport or post_webhook
    for attempt in range(MAX_ATTEMPTS):
        retry_after = None
        try:
            status = int(sender(url, payload, REQUEST_TIMEOUT_SECONDS))
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            try:
                retry_after = float(exc.headers.get("Retry-After", ""))
            except (TypeError, ValueError, AttributeError):
                retry_after = None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # A timed-out POST may already have reached Discord. Do not blindly
            # repeat it and risk duplicate pings; the next distinct drop is retried.
            print(f"[FARM] Falha de rede no Discord ({type(exc).__name__}); sem reenvio para evitar duplicados.", flush=True)
            return False
        except Exception as exc:
            print(f"[FARM] Falha no envio Discord ({type(exc).__name__}); alerta local continua ativo.", flush=True)
            return False

        if 200 <= status < 300:
            if test:
                print("[FARM] Teste Discord enviado." + (" Mencao autorizada incluida." if user_id else " Sem ID de utilizador; sem mencao."), flush=True)
            else:
                print("[FARM] Alerta Discord enviado." + (" Mencao autorizada incluida." if user_id else " Sem ID de utilizador; sem mencao."), flush=True)
            return True
        if status == 429 and attempt + 1 < MAX_ATTEMPTS:
            delay = retry_after if retry_after is not None else 0.5 * (2 ** attempt)
            sleeper(max(0.1, min(delay, 3.0)))
            continue
        print(f"[FARM] Discord respondeu HTTP {status}; alerta local continua ativo.", flush=True)
        return False
    return False
