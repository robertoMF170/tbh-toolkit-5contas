"""Vigia os alvos de farm e avisa quando um save ganha o item procurado.

O processo e arrancado por run.bat e corre enquanto essa janela estiver aberta.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from datetime import datetime

import tbh_discord

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)


def _first_existing(candidates: list[str]) -> str:
    return next((path for path in candidates if os.path.exists(path)), candidates[0])


WATCH_FILE = _first_existing([
    os.path.join(ROOT, "var", "farm_watch.json"),
    os.path.join(ROOT, "farm_watch.json"),
    os.path.join(BASE, "farm_watch.json"),
])
ACCOUNTS_FILE = _first_existing([
    os.path.join(ROOT, "config", "baus.json"),
    os.path.join(ROOT, "baus.json"),
    os.path.join(BASE, "baus.json"),
])
STATE_FILE = os.path.join(ROOT, "var", "farm_alert_state.json")
LOCK_FILE = os.path.join(ROOT, "var", "farm_alert.lock")
# The legacy tbh_farm_watch.py writes a plain-text timestamp to its own
# farm_watch.heartbeat; keep this JSON health marker separate.
HEARTBEAT_FILE = os.path.join(ROOT, "var", "farm_alert.heartbeat")
PRICE_FILE = _first_existing([
    os.path.join(ROOT, "data", "tbhdata", "precos_cache.json"),
    os.path.join(ROOT, "tbhdata", "precos_cache.json"),
    os.path.join(BASE, "tbhdata", "precos_cache.json"),
])


def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError, TypeError):
        return default


def _write_json_atomic(path: str, data: dict) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temp_path = f"{path}.{os.getpid()}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(temp_path, path)
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


def _acquire_watch_lock(path: str = LOCK_FILE) -> int | None:
    """Acquire a process-wide lock so restarting run.bat cannot duplicate polling."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except OSError:
        os.close(fd)
        return None


def _release_watch_lock(fd: int) -> None:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        os.close(fd)


def _watch_process_running(path: str | None = None) -> bool:
    """Check the OS lock, so a stale heartbeat never claims a dead process is active."""
    fd = _acquire_watch_lock(path or LOCK_FILE)
    if fd is None:
        return True
    _release_watch_lock(fd)
    return False


def _watch_data(path: str = WATCH_FILE) -> dict:
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    if not isinstance(data.get("targets"), list):
        data["targets"] = []
    if not isinstance(data.get("hits"), list):
        data["hits"] = []
    return data


def load_targets(path: str = WATCH_FILE) -> list[dict]:
    data = _watch_data(path)
    return [
        {"name": str(target.get("name") or "").strip(),
         "conta": str(target.get("conta") or "").strip()}
        for target in data["targets"]
        if isinstance(target, dict) and str(target.get("name") or "").strip()
    ]


def add_target(name: str, conta: str = "", watch_file: str = WATCH_FILE,
               state_file: str = STATE_FILE, accounts_file: str = ACCOUNTS_FILE,
               price_file: str = PRICE_FILE, inventory=None) -> bool:
    name = str(name or "").strip()
    conta = str(conta or "").strip()
    if not name:
        return False
    data = _watch_data(watch_file)
    key = (name.casefold(), conta.casefold())
    for target in data["targets"]:
        if isinstance(target, dict) and (
            str(target.get("name") or "").strip().casefold(),
            str(target.get("conta") or "").strip().casefold(),
        ) == key:
            return False

    state = _read_json(state_file, {})
    if not isinstance(state, dict):
        state = {}
    old_accounts = state.get("accounts", {})
    if not isinstance(old_accounts, dict):
        old_accounts = {}
    old_baselines = state.get("target_baselines", {})
    if not isinstance(old_baselines, dict):
        old_baselines = {}

    accounts = load_accounts(accounts_file)
    selected_account = resolve_account_name(conta, accounts) if conta else None
    if conta and not selected_account:
        configured = ", ".join(account["name"] for account in accounts) or "nenhuma conta configurada"
        print(f"[FARM] AVISO: '{conta}' nao corresponde a uma conta unica. O alvo fica associado a esse nome e nao alertara ate a conta ser resolvida. Configuradas: {configured}.", flush=True)
    if selected_account:
        accounts = [account for account in accounts if account["name"] == selected_account]

    # Try to snapshot current inventory to prevent false positives. A missing
    # dependency/save must not prevent registering an alert: the watcher will
    # retry and establish its first baseline once it can read that save.
    current, failed = {}, set()
    try:
        current, failed = scan_inventories(accounts, _market_names([{"name": name}], price_file), inventory)
    except (Exception, SystemExit) as exc:
        failed = {account["name"] for account in accounts}
        print(f"[FARM] Snapshot inicial indisponivel ({type(exc).__name__}: {exc}); alvo registado e o vigia vai tentar novamente.", flush=True)
    readable_current = dict(current)
    folded_old = {str(account).casefold(): items for account, items in old_accounts.items()}
    for account in failed:
        if account.casefold() in folded_old:
            current[account] = folded_old[account.casefold()]
    # Keep an explicit empty baseline for unreadable accounts. Otherwise poll_once
    # could mistake an older global snapshot for the moment this target was added.
    baseline_accounts = {
        account.casefold(): _item_count(items, name)
        for account, items in readable_current.items()
    }
    if selected_account:
        # Ignore snapshots from other accounts retained in old_state: this target
        # must only compare against the account explicitly selected by the user.
        baseline_accounts = {
            account.casefold(): _item_count(items, name)
            for account, items in readable_current.items()
            if account.casefold() == selected_account.casefold()
        }
    old_baselines[_target_key({"name": name, "conta": conta})] = {"accounts": baseline_accounts}
    state.update({"version": 1, "accounts": {**old_accounts, **current}, "target_baselines": old_baselines})

    _write_json_atomic(state_file, state)

    # Persist the watch request even if reading saves failed; the running monitor
    # can retry as soon as the save becomes available or its lock is released.
    data["targets"].append({"name": name, "conta": conta})
    _write_json_atomic(watch_file, data)
    return True


def remove_target(name: str, conta: str = "", watch_file: str = WATCH_FILE) -> bool:
    name_key = str(name or "").strip().casefold()
    conta_key = str(conta or "").strip().casefold()
    data = _watch_data(watch_file)
    before = len(data["targets"])
    data["targets"] = [
        target for target in data["targets"]
        if not isinstance(target, dict)
        or str(target.get("name") or "").strip().casefold() != name_key
        or (conta_key and str(target.get("conta") or "").strip().casefold() != conta_key)
    ]
    if len(data["targets"]) == before:
        return False
    _write_json_atomic(watch_file, data)
    return True


def acknowledge_hits(name: str = "", all_hits: bool = False, watch_file: str = WATCH_FILE,
                     conta: str = "") -> int:
    data = _watch_data(watch_file)
    acknowledged = 0
    for hit in data["hits"]:
        if not isinstance(hit, dict) or hit.get("acknowledged"):
            continue
        if (all_hits or not name or str(hit.get("name") or "").casefold() == name.casefold()) and (not conta or str(hit.get("conta") or "").casefold() == conta.casefold()):
            hit["acknowledged"] = True
            acknowledged += 1
    if acknowledged:
        _write_json_atomic(watch_file, data)
    return acknowledged


def load_accounts(path: str = ACCOUNTS_FILE) -> list[dict]:
    data = _read_json(path, {})
    if not isinstance(data, dict):
        return []
    rows = data.get("contas") or []
    if not isinstance(rows, list):
        return []
    accounts = []
    for account in rows:
        if not isinstance(account, dict):
            continue
        name = str(account.get("nome") or account.get("id") or "").strip()
        save = str(account.get("save") or "").strip()
        if name and save:
            accounts.append({"name": name, "save": os.path.expandvars(save)})
    return accounts


def resolve_account_name(requested: str, accounts: list[dict]) -> str | None:
    """Resolve a configured account name or its parenthesized Steam username."""
    requested = str(requested or "").strip().casefold()
    if not requested:
        return None
    names = [str(account.get("name") or "").strip() for account in accounts if account.get("name")]
    exact = [name for name in names if name.casefold() == requested]
    if len(exact) == 1:
        return exact[0]
    # Builds may store only a Steam login like `geek1781`, while baus.json
    # labels the account `Conta 1 (geek1781)`. Match that alias exactly first.
    aliases = []
    for name in names:
        left, sep, rest = name.rpartition("(")
        alias = rest[:-1].strip().casefold() if sep and rest.endswith(")") else ""
        if alias == requested:
            aliases.append(name)
    if len(aliases) == 1:
        return aliases[0]
    partial = [name for name in names if requested in name.casefold()]
    return partial[0] if len(partial) == 1 else None


def _accounts_for_targets(targets: list[dict], accounts: list[dict]) -> list[dict]:
    """Limit explicit-account alerts to those saves; unscoped alerts need all accounts."""
    if not targets:
        return []
    if any(not str(target.get("conta") or "").strip() for target in targets):
        return accounts
    selected = {
        resolved.casefold()
        for target in targets
        if (resolved := resolve_account_name(target.get("conta"), accounts))
    }
    return [account for account in accounts if account["name"].casefold() in selected]


def _market_names(targets: list[dict], price_file: str = PRICE_FILE) -> set[str]:
    data = _read_json(price_file, {})
    if isinstance(data, dict):
        items = data.get("itens") or data
    else:
        items = {}
    names = set(items) if isinstance(items, dict) else set()
    names.update(target["name"] for target in targets)
    return names

_GAME_DATA_CACHE = None
_GAME_DATA_OWNER = None
_LAST_SCAN_ERRORS = {}


def scan_inventories(accounts: list[dict], market_names: set[str], inventory=None) -> tuple[dict, set[str]]:
    """Devolve quantidades por conta e os nomes de contas cuja leitura falhou."""
    global _GAME_DATA_CACHE, _GAME_DATA_OWNER
    if inventory is None:
        import tbh_inventario as inventory

    if not accounts:
        return {}, set()

    snapshots = {}
    failed = set()
    if _GAME_DATA_OWNER is not inventory or _GAME_DATA_CACHE is None:
        try:
            _GAME_DATA_CACHE = inventory.carregar_dados_jogo()
            _GAME_DATA_OWNER = inventory
        except (Exception, SystemExit) as exc:
            error = f"{type(exc).__name__}: {exc}"
            for account in accounts:
                name = account["name"]
                failed.add(name)
                if _LAST_SCAN_ERRORS.get(name) != error:
                    print(f"[FARM] Dados do inventario indisponiveis ({error}); a tentar novamente.", flush=True)
                    _LAST_SCAN_ERRORS[name] = error
            return snapshots, failed
    for account in accounts:
        name = account["name"]
        try:
            items, _deleted = inventory.itens_da_conta_detalhado(
                account["save"], _GAME_DATA_CACHE, market_names
            )
            snapshots[name] = {str(item): int(count) for item, count in items.items()}
            if name in _LAST_SCAN_ERRORS:
                print(f"[FARM] Leitura do save recuperada: {name}.", flush=True)
                _LAST_SCAN_ERRORS.pop(name, None)
        except Exception as exc:
            failed.add(name)
            error = f"{type(exc).__name__}: {exc}"
            if _LAST_SCAN_ERRORS.get(name) != error:
                print(f"[FARM] Nao consegui ler {name}: {error}", flush=True)
                _LAST_SCAN_ERRORS[name] = error
    return snapshots, failed


def _target_key(target: dict) -> str:
    return json.dumps([
        target["name"].casefold(),
        (target.get("conta") or "").casefold(),
    ], ensure_ascii=True, separators=(",", ":"))


def _item_count(items: dict, name: str) -> int:
    if name in items:
        return int(items.get(name) or 0)
    target = name.casefold()
    for item_name, count in items.items():
        if str(item_name).casefold() == target:
            return int(count or 0)
    return 0


def _farm_window_title(targets: list[dict]) -> str:
    if not targets:
        return "TBH RUN - Alertas de farm (sem alvos)"
    if len(targets) == 1:
        target = targets[0]
        account = target.get("conta") or "Todas as contas"
        return f"TBH RUN - {target['name']} @ {account}"[:120]
    names = ", ".join(target["name"] for target in targets[:2])
    suffix = f" +{len(targets) - 2}" if len(targets) > 2 else ""
    return f"TBH RUN - {len(targets)} alertas: {names}{suffix}"[:120]


def _set_farm_window_title(targets: list[dict]) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(_farm_window_title(targets))
    except Exception:
        pass


def watcher_status(path: str = HEARTBEAT_FILE, now: float | None = None,
                   interval: float = 2.0) -> dict:
    """Returns whether the alert watcher has reported a recent heartbeat."""
    heartbeat = _read_json(path, {})
    if not isinstance(heartbeat, dict):
        heartbeat = {}
    try:
        age = (time.time() if now is None else now) - float(heartbeat.get("updated_epoch") or 0)
    except (TypeError, ValueError):
        age = float("inf")
    heartbeat["age_seconds"] = max(0.0, age)
    heartbeat["alive"] = age <= max(10.0, interval * 4)
    return heartbeat


def _write_heartbeat(targets: list[dict], accounts: list[dict], interval: float,
                     status: str = "running", error: str = "",
                     path: str = HEARTBEAT_FILE,
                     watched_accounts: list[dict] | None = None) -> None:
    """Persists a small status marker so run.bat can confirm the watcher is alive."""
    watched_accounts = accounts if watched_accounts is None else watched_accounts
    account_names = {str(account.get("name") or "").casefold() for account in watched_accounts}
    unreadable = sorted(
        name for name in _LAST_SCAN_ERRORS
        if name.casefold() in account_names
    )
    _write_json_atomic(path, {
        "pid": os.getpid(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "updated_epoch": time.time(),
        "interval_seconds": interval,
        "status": status,
        "target_count": len(targets),
        "targets": [{"name": target["name"], "conta": target.get("conta") or ""} for target in targets],
        "account_count": len(accounts),
        "accounts": [account["name"] for account in accounts],
        "watched_account_count": len(watched_accounts),
        "watched_accounts": [account["name"] for account in watched_accounts],
        "unreadable_accounts": unreadable,
        "error": error,
    })


def _account_save_fingerprint(accounts: list[dict]) -> str:
    """Fingerprint da configuração de contas para detetar contas novas no vigia."""
    return json.dumps(sorted((a["name"].casefold(), os.path.normcase(a["save"])) for a in accounts), ensure_ascii=True)


def find_new_drops(previous: dict, current: dict, targets: list[dict]) -> list[dict]:
    """Encontra aumentos para alvos cuja linha de base existe (sem falsos hits)."""
    hits = []
    checked = set()
    accounts_by_fold = {name.casefold(): name for name in current}
    previous_by_fold = {name.casefold(): name for name in previous}

    for target in targets:
        name = target["name"]
        target_account = target.get("conta") or ""
        key = (name.casefold(), target_account.casefold())
        if key in checked:
            continue
        checked.add(key)

        if target_account:
            account_names = [accounts_by_fold[target_account.casefold()]] if target_account.casefold() in accounts_by_fold else []
        else:
            account_names = list(current)

        for account_name in account_names:
            previous_name = previous_by_fold.get(account_name.casefold())
            if previous_name is None:
                continue
            old_items = previous.get(previous_name) or {}
            new_items = current.get(account_name) or {}
            old_count = int(old_items.get(name, 0) or 0)
            new_count = int(new_items.get(name, 0) or 0)
            if new_count > old_count:
                hits.append({"name": name, "conta": account_name, "qtd": new_count - old_count})
    return hits


def _record_hit(hit: dict, path: str = WATCH_FILE) -> None:
    data = _watch_data(path)
    data["hits"].append({
        "name": hit["name"],
        "conta": hit["conta"],
        "qtd": hit["qtd"],
        "acknowledged": False,
        "time": datetime.now().isoformat(timespec="seconds"),
    })
    data["hits"] = data["hits"][-100:]
    _write_json_atomic(path, data)


def notify_drop(hit: dict) -> None:
    message = f"ITEM ENCONTRADO: {hit['name']}\nConta: {hit['conta']}\nQuantidade nova: {hit['qtd']}"
    print(f"\n\a[FARM] {message.replace(chr(10), ' | ')}", flush=True)
    try:
        tbh_discord.send_alert(hit)
    except Exception as exc:
        # Remote notification must never prevent the local sound/popup.
        print(f"[FARM] Aviso Discord falhou ({type(exc).__name__}); alerta local continua ativo.", flush=True)
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            message,
            "Taskbar Hero — item de farm encontrado",
            0x00000040 | 0x00040000,
        )
        # Clicar OK no popup confirma este alerta pendente na dashboard também.
        acknowledge_hits(hit["name"], watch_file=WATCH_FILE, conta=hit["conta"])
    except Exception as exc:
        print(f"[FARM] Nao consegui mostrar o popup: {exc}", flush=True)


def poll_once(state_file: str = STATE_FILE, watch_file: str = WATCH_FILE,
              accounts_file: str = ACCOUNTS_FILE, price_file: str = PRICE_FILE,
              inventory=None, notify=notify_drop) -> list[dict]:
    targets = load_targets(watch_file)
    all_accounts = load_accounts(accounts_file)
    if not all_accounts:
        print(f"[FARM] Ainda nao encontrei contas em {accounts_file}.", flush=True)
        return []

    # Unscoped targets need all accounts to identify where a drop happened;
    # explicit-account targets read only their selected saves.
    accounts = _accounts_for_targets(targets, all_accounts)
    for target in targets:
        if target.get("conta") and not resolve_account_name(target["conta"], all_accounts):
            print(f"[FARM] A conta do alvo '{target['name']}' ('{target.get('conta')}') nao corresponde a nenhuma conta em {accounts_file}.", flush=True)

    old_state = _read_json(state_file, {})
    previous = old_state.get("accounts", {}) if isinstance(old_state, dict) else {}
    if not isinstance(previous, dict):
        previous = {}
    old_baselines = old_state.get("target_baselines", {}) if isinstance(old_state, dict) else {}
    if not isinstance(old_baselines, dict):
        old_baselines = {}

    current, failed = scan_inventories(accounts, _market_names(targets, price_file), inventory) if accounts else ({}, set())
    failed_accounts = {str(name).casefold() for name in failed}
    previous_accounts = {str(name).casefold(): items for name, items in previous.items()}
    for name in failed:
        if name.casefold() in previous_accounts:
            current[name] = previous_accounts[name.casefold()]

    # A previously cached inventory can keep state stable during a save lock, but
    # must never be treated as a fresh read or used to seed a new target baseline.
    readable_current = {
        name: items for name, items in current.items()
        if name.casefold() not in failed_accounts
    }
    accounts_by_fold = {name.casefold(): name for name in readable_current}
    next_baselines = {}
    hits = []
    hit_keys = set()
    for target in targets:
        key = _target_key(target)
        old_target_state = old_baselines.get(key)
        old_counts = old_target_state.get("accounts", {}) if isinstance(old_target_state, dict) else {}
        if not isinstance(old_counts, dict):
            old_counts = {}
        old_counts = {str(name).casefold(): int(count or 0) for name, count in old_counts.items()}
        if old_target_state is None:
            # Legacy/manual targets fall back to the last global snapshot.
            old_counts = {
                account.casefold(): _item_count(items or {}, target["name"])
                for account, items in previous_accounts.items()
            }

        # New accounts enter the baseline at their first valid read, not as false drops.
        for account_name, items in readable_current.items():
            old_counts.setdefault(account_name.casefold(), _item_count(items, target["name"]))

        if target.get("conta"):
            requested_account = resolve_account_name(target["conta"], all_accounts)
            account = accounts_by_fold.get(requested_account.casefold()) if requested_account else None
            account_names = [account] if account else []
        else:
            account_names = list(readable_current)

        next_counts = dict(old_counts)
        for account_name in account_names:
            account_key = account_name.casefold()
            items = readable_current.get(account_name) or {}
            count = _item_count(items, target["name"])
            if account_key not in old_counts:
                # This target/account pair was not observed before; start at today's count.
                next_counts[account_key] = count
                continue
            old_count = old_counts[account_key]
            if count > old_count:
                hit_key = (target["name"].casefold(), account_key)
                if hit_key not in hit_keys:
                    hits.append({"name": target["name"], "conta": account_name, "qtd": count - old_count})
                    hit_keys.add(hit_key)
            # Track both gains and spending so only a later gain is a new drop.
            next_counts[account_key] = count
        next_baselines[key] = {"accounts": next_counts}

    _write_json_atomic(state_file, {
        "version": 1,
        "accounts": {**previous, **current},
        "target_baselines": next_baselines,
    })

    for hit in hits:
        _record_hit(hit, watch_file)
        notify(hit)
    return hits


def watch(interval: float = 2.0) -> None:
    interval = max(0.5, min(interval, 60.0))
    print(f"[FARM] Vigia iniciado: consulta saves a cada {interval:g}s. Deixa o run.bat aberto.", flush=True)
    last_signature = None
    while True:
        started = time.monotonic()
        try:
            targets = load_targets()
            configured_accounts = load_accounts()
            watched_accounts = _accounts_for_targets(targets, configured_accounts)
            target_signature = tuple((t["name"], t.get("conta") or "") for t in targets)
            if target_signature != last_signature:
                last_signature = target_signature
                _set_farm_window_title(targets)
                if targets:
                    print("[FARM] A vigiar: " + "; ".join(
                        t["name"] + (f" @ {t['conta']}" if t.get("conta") else " @ todas as contas")
                        for t in targets
                    ), flush=True)
                else:
                    print("[FARM] Sem alvos. Clica Farmar na dashboard para adicionar um item.", flush=True)

            # Sinaliza o arranque antes do primeiro scan, para o .bat confirmar que o
            # processo existe mesmo quando ainda nao ha alvos ou saves acessiveis.
            _write_heartbeat(targets, configured_accounts, interval, status="scanning" if targets else "starting", watched_accounts=watched_accounts)
            if targets:
                poll_once()
                configured_accounts = load_accounts()
                watched_accounts = _accounts_for_targets(targets, configured_accounts)
                watched_names = {account["name"].casefold() for account in watched_accounts}
                unreadable = len(watched_names & {name.casefold() for name in _LAST_SCAN_ERRORS})
                unresolved = any(target.get("conta") and not resolve_account_name(target["conta"], configured_accounts) for target in targets)
                if not configured_accounts:
                    status = "no_accounts"
                elif unresolved or not watched_accounts:
                    status = "account_not_found"
                elif unreadable == len(watched_accounts):
                    status = "save_read_error"
                elif unreadable:
                    status = "partial_warning"
                else:
                    status = "active"
                _write_heartbeat(targets, configured_accounts, interval, status=status, watched_accounts=watched_accounts)
                good = max(0, len(watched_accounts) - unreadable)
                print(f"[FARM] {datetime.now().strftime('%H:%M:%S')} — {len(targets)} alvo(s); saves vigiados legiveis {good}/{len(watched_accounts)}; verifica a cada {interval:g}s.", flush=True)
            else:
                _LAST_SCAN_ERRORS.clear()
                status = "waiting_for_targets" if configured_accounts else "no_accounts"
                _write_heartbeat(targets, configured_accounts, interval, status=status, watched_accounts=watched_accounts)
        except KeyboardInterrupt:
            print("\n[FARM] Vigia parado.", flush=True)
            return
        except (Exception, SystemExit) as exc:
            error = type(exc).__name__
            fallback_targets = locals().get("targets", [])
            fallback_accounts = locals().get("configured_accounts", [])
            fallback_watched = locals().get("watched_accounts", [])
            _write_heartbeat(fallback_targets, fallback_accounts, interval, status="error", error=error, watched_accounts=fallback_watched)
            print(f"[FARM] Erro no ciclo de vigia ({error}): {exc}", flush=True)
        time.sleep(max(0.1, interval - (time.monotonic() - started)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vigia os itens farmados e alerta quando aparecem nos saves.")
    parser.add_argument("--watch", action="store_true", help="vigia continuamente, consultando a cada 2 segundos")
    parser.add_argument("--status", action="store_true", help="mostra se o vigia de alertas está ativo")
    parser.add_argument("--check-running", action="store_true", help="verifica o bloqueio do processo sem iniciar outra vigia")
    parser.add_argument("--discord-setup", action="store_true", help="guarda o webhook e o ID opcional do utilizador num .env local")
    parser.add_argument("--test-discord", action="store_true", help="envia uma mensagem de teste para o webhook configurado")
    parser.add_argument("--interval", type=float, default=2.0, help="intervalo entre verificacoes (segundos)")
    parser.add_argument("--add", metavar="ITEM", help="adiciona um item aos alertas")
    parser.add_argument("--conta", default="", help="associa o alvo ou verifica esta conta (com --status/--add/--rm)")
    parser.add_argument("--rm", metavar="ITEM", help="remove um item dos alertas")
    parser.add_argument("--ack", metavar="ITEM", nargs="?", const="", help="confirma alertas pendentes")
    parser.add_argument("--all", action="store_true", help="confirma todos os alertas pendentes")
    args = parser.parse_args(argv)
    if args.check_running:
        running = _watch_process_running()
        print("VIGIA JA EM EXECUCAO." if running else "VIGIA NAO ESTA EM EXECUCAO.", flush=True)
        return 0 if running else 1
    if args.discord_setup:
        webhook_url = getpass.getpass("Webhook Discord novo (entrada oculta; nao reutilizes o que foi exposto): ").strip()
        mention_id = input("ID numerico do utilizador robs (Enter para nao mencionar): ").strip()
        try:
            tbh_discord.save_discord_settings(webhook_url, mention_id)
        except (OSError, ValueError) as exc:
            print(f"Configuracao Discord nao guardada: {exc}", flush=True)
            return 1
        print("Configuracao Discord guardada em .env sem mostrar o webhook.", flush=True)
        print("Confirma o envio com: python -X utf8 src\\tbh_farm_alert.py --test-discord", flush=True)
        return 0
    if args.test_discord:
        webhook_url, mention_id = tbh_discord.discord_settings()
        if not webhook_url:
            print(f"Discord nao configurado ({tbh_discord.WEBHOOK_ENV} em .env).", flush=True)
            return 1
        if mention_id and not tbh_discord.valid_discord_user_id(mention_id):
            print("ID de mencao Discord invalido; teste nao enviado.", flush=True)
            return 2
        allowed_user = tbh_discord.normalise_user_id(mention_id)
        confirmed = input(
            "Vai ser enviada uma mensagem de teste no canal configurado" +
            (f" com mencao a <@{allowed_user}>" if allowed_user else " sem mencao") +
            ". Escreve SIM para continuar: "
        ).strip()
        if confirmed != "SIM":
            print("Teste Discord cancelado.", flush=True)
            return 3
        ok = tbh_discord.send_alert(
            {"name": "Teste do alerta de farm", "conta": "teste manual", "qtd": 1},
            test=True,
        )
        return 0 if ok else 1
    if args.add:
        changed = add_target(args.add, args.conta)
        print(("Alerta adicionado: " if changed else "Alerta ja registado: ") + args.add, flush=True)
        return 0
    if args.rm:
        changed = remove_target(args.rm, args.conta)
        print(("Alerta removido: " if changed else "Alerta nao encontrado: ") + args.rm, flush=True)
        return 0
    if args.ack is not None:
        print(f"{acknowledge_hits(args.ack, args.all or not args.ack)} alerta(s) confirmado(s).", flush=True)
        return 0
    if args.status:
        webhook_url, mention_id = tbh_discord.discord_settings()
        if not webhook_url:
            print(f"Discord: nao configurado ({tbh_discord.WEBHOOK_ENV} em .env).")
        elif not tbh_discord.valid_webhook_url(webhook_url):
            print("Discord: URL configurado, mas formato invalido.")
        else:
            print("Discord: webhook configurado; " + ("mencao autorizada configurada." if mention_id and tbh_discord.valid_discord_user_id(mention_id) else "sem ID valido para mencionar robs."))
        heartbeat = watcher_status(interval=args.interval)
        heartbeat["process_running"] = _watch_process_running()
        heartbeat["alive"] = heartbeat["alive"] and heartbeat["process_running"]
        if heartbeat["process_running"] and not heartbeat["alive"]:
            print(f"VIGIA PRESO OU SEM HEARTBEAT — o processo existe, mas nao atualiza ha {heartbeat['age_seconds']:.1f}s.")
            print("Os alertas nao estao confirmados; verifica a janela do run.bat e os erros de leitura.")
            return 2
        account_rows = heartbeat.get("accounts", [])
        status_accounts = [
            {"name": str(name).strip()}
            for name in account_rows
            if isinstance(name, str) and name.strip()
        ] if isinstance(account_rows, list) else []
        watched_rows = heartbeat.get("watched_accounts", account_rows)
        watched_accounts = [
            {"name": str(name).strip()}
            for name in watched_rows
            if isinstance(name, str) and name.strip()
        ] if isinstance(watched_rows, list) else []
        requested_account = resolve_account_name(args.conta, status_accounts) if args.conta else None
        target_rows = heartbeat.get("targets", [])
        targets = [target for target in target_rows if isinstance(target, dict)] if isinstance(target_rows, list) else []
        watches_requested_account = not args.conta or any(
            not str(target.get("conta") or "").strip()
            or resolve_account_name(target.get("conta"), status_accounts) == requested_account
            for target in targets
        )
        if heartbeat["alive"] and (not args.conta or requested_account) and watches_requested_account:
            status = str(heartbeat.get("status") or "?")
            print(f"VIGIA ATIVO — {heartbeat.get('target_count', len(targets))} alvo(s), estado: {status}.")
            print("Alvos: " + ("; ".join(
                str(target.get("name") or "?") + (f" @ {target.get('conta')}" if target.get("conta") else " @ todas")
                for target in targets
            ) or "nenhum"))
            print("Contas vigiadas: " + (", ".join(account["name"] for account in watched_accounts) or "nenhuma") + ".")
            if args.conta:
                print(f"Conta pedida: {args.conta} -> {requested_account}.")
            print(f"Ultima verificacao: {heartbeat.get('updated_at', '?')}; intervalo: {heartbeat.get('interval_seconds', '?')}s.")
            if status == "no_accounts":
                print("ERRO: o vigia esta vivo, mas nao carregou contas. Confirma config/baus.json.")
            if status == "account_not_found":
                print("ERRO: a conta associada a um alvo nao foi encontrada no ficheiro de contas.")
            if status in {"starting", "scanning"}:
                print("VIGIA A ARRANCAR — a primeira leitura dos saves ainda esta em curso.")
                return 3
            unreadable = heartbeat.get("unreadable_accounts", [])
            if isinstance(unreadable, list) and unreadable:
                print("Saves com erro de leitura: " + ", ".join(str(name) for name in unreadable))
            if heartbeat.get("error"):
                print("Ultimo erro do vigia: " + str(heartbeat["error"]))
            if status in {"no_accounts", "save_read_error", "partial_warning", "account_not_found", "error"} or heartbeat.get("error") or unreadable:
                print("AVISO: processo ativo, mas ha erros que podem impedir alguns alertas; corrige os detalhes acima.")
                return 2
            if status == "waiting_for_targets":
                print("VIGIA ATIVO, a espera — clica Farmar na dashboard para comecar os alertas.")
                return 4
            return 0
        if heartbeat["alive"] and heartbeat.get("status") in {"starting", "scanning"}:
            print("VIGIA A ARRANCAR — primeira leitura dos saves ainda em curso.")
            return 3
        if heartbeat["alive"] and args.conta and not requested_account:
            names = ", ".join(account["name"] for account in status_accounts) or "nenhuma"
            print(f"VIGIA ATIVO, mas a conta '{args.conta}' nao esta na lista configurada: {names}.")
            return 2
        if heartbeat["alive"] and args.conta and not watches_requested_account:
            print(f"VIGIA ATIVO, mas nao tem alvo associado a '{requested_account}'.")
            return 2
        print("VIGIA INATIVO — sem heartbeat recente. Abre o run.bat e deixa-o aberto.")
        return 1
    if args.watch:
        lock_fd = _acquire_watch_lock()
        if lock_fd is None:
            print("[FARM] Ja existe um vigia ativo; nao vou iniciar outro.", flush=True)
            return 5
        try:
            try:
                os.remove(HEARTBEAT_FILE)
            except FileNotFoundError:
                pass
            except OSError as exc:
                print(f"[FARM] Nao consegui limpar heartbeat antigo: {exc}", flush=True)
            watch(max(0.5, min(args.interval, 60.0)))
        finally:
            _release_watch_lock(lock_fd)
        return 0
    poll_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
