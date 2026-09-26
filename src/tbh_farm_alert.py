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


def _inventory_method(inventory, name: str):
    """Avoids treating dynamic mock attributes as real reader capabilities."""
    if getattr(inventory, "__name__", "") == "tbh_inventario":
        return getattr(inventory, name, None)
    if callable(getattr(type(inventory), name, None)):
        return getattr(inventory, name)
    return None


def scan_inventories(accounts: list[dict], market_names: set[str], inventory=None,
                     zone_snapshots: dict | None = None) -> tuple[dict, set[str]]:
    """Devolve inventários, zonas atuais opcionais e contas cuja leitura falhou."""
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
            combined_reader = _inventory_method(inventory, "itens_da_conta_com_zona")
            if callable(combined_reader):
                try:
                    items, _deleted, zone = inventory.itens_da_conta_com_zona(
                        account["save"], _GAME_DATA_CACHE, market_names
                    )
                except Exception:
                    items, _deleted = inventory.itens_da_conta_detalhado(
                        account["save"], _GAME_DATA_CACHE, market_names
                    )
                else:
                    if zone_snapshots is not None:
                        zone_snapshots[name] = zone if isinstance(zone, dict) else {}
            else:
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


def _hit_matches_target(hit: dict, target: dict, accounts: list[dict]) -> bool:
    if str(hit.get("name") or "").strip().casefold() != str(target.get("name") or "").strip().casefold():
        return False
    requested_account = str(target.get("conta") or "").strip().casefold()
    if not requested_account:
        return True
    hit_account = str(hit.get("conta") or "").strip().casefold()
    resolved_account = resolve_account_name(requested_account, accounts)
    if resolved_account:
        return hit_account == resolved_account.casefold()
    return hit_account == requested_account or hit_account.endswith(f"({requested_account})")


def _target_hit_summary(targets: list[dict], accounts: list[dict] | None = None,
                        watch_file: str | None = None) -> list[dict]:
    """Summarize the quantities and alert events recorded for each watched target."""
    accounts = accounts or []
    history = _watch_data(watch_file or WATCH_FILE)["hits"]
    summary = []
    for target in targets:
        quantity = alert_count = 0
        for hit in history:
            if not isinstance(hit, dict) or not _hit_matches_target(hit, target, accounts):
                continue
            try:
                found = int(hit.get("qtd") or 0)
            except (TypeError, ValueError):
                continue
            if found > 0:
                quantity += found
                alert_count += 1
        summary.append({"qtd": quantity, "alertas": alert_count})
    return summary


def _print_watch_summary(targets: list[dict], accounts: list[dict],
                         watch_file: str | None = None) -> None:
    """Print a concise target/hit summary only when requested or targets change."""
    counts = _target_hit_summary(targets, accounts, watch_file)
    print(f"[FARM] Alvos a vigiar ({len(targets)}):", flush=True)
    total_quantity = total_alerts = 0
    for target, count in zip(targets, counts):
        account = target.get("conta") or "todas as contas"
        unit_word = "unidade" if count["qtd"] == 1 else "unidades"
        found_word = "encontrada" if count["qtd"] == 1 else "encontradas"
        alert_word = "alerta" if count["alertas"] == 1 else "alertas"
        print(
            f"[FARM]   {target['name']} @ {account} — {count['qtd']} {unit_word} "
            f"{found_word} em {count['alertas']} {alert_word}.",
            flush=True,
        )
        total_quantity += count["qtd"]
        total_alerts += count["alertas"]
    if not targets:
        print("[FARM] Sem alvos ativos.", flush=True)
    total_unit_word = "unidade" if total_quantity == 1 else "unidades"
    total_alert_word = "alerta" if total_alerts == 1 else "alertas"
    print(
        f"[FARM] Total nos últimos 100 registos guardados: {total_quantity} {total_unit_word} "
        f"em {total_alerts} {total_alert_word}.",
        flush=True,
    )


_DROP_STAGES_CACHE = {}


def _drop_stages_for_name(name: str) -> list:
    """Devolve zonas conhecidas para o item usando o mesmo mapa da dashboard."""
    cache_key = str(name or "").casefold()
    if cache_key in _DROP_STAGES_CACHE:
        return _DROP_STAGES_CACHE[cache_key]
    try:
        import tbh_farm
        stages = tbh_farm.drop_stages_for_name(name)
        stages = stages if isinstance(stages, list) else []
    except (Exception, SystemExit):
        stages = []
    if stages:
        _DROP_STAGES_CACHE[cache_key] = stages
    return stages


def _canonical_drop_zones(stages: list) -> list[tuple[int, int, int, bool]]:
    zones = set()
    for stage in stages or []:
        if not isinstance(stage, (list, tuple)) or len(stage) < 4:
            continue
        try:
            act, no, diff_index = int(stage[0]), int(stage[1]), int(stage[3])
            plague = bool(int(stage[9])) if len(stage) > 9 else act >= 21
        except (TypeError, ValueError):
            continue
        if diff_index in {0, 1, 2, 3}:
            zones.add((act, no, diff_index, plague))
    return sorted(zones)


def _zone_display(zone: dict) -> str:
    label = str(zone.get("label") or "").strip()
    if label:
        return label
    try:
        act, no = int(zone.get("act")), int(zone.get("no"))
    except (TypeError, ValueError):
        key = zone.get("key")
        return f"fase {key}" if key else "desconhecida"
    diff = str(zone.get("diff") or "").upper()
    diff_label = {
        "NORMAL": "Normal", "NIGHTMARE": "Pesadelo", "HELL": "Inferno",
        "TORMENT": "Tormento", "PLAGUE": "Plague",
    }.get(diff, "")
    return f"{act}-{no} {diff_label}".strip()


def _expected_zone_labels(zones: list[tuple[int, int, int, bool]], limit: int = 5) -> str:
    diff_labels = {0: "Normal", 1: "Pesadelo", 2: "Inferno", 3: "Tormento"}
    labels = []
    for act, no, diff_index, plague in zones:
        if diff_index not in diff_labels:
            continue
        label = f"{act}-{no} {diff_labels[diff_index]}"
        if plague:
            label += " (Plague)"
        labels.append(label)
    if zones and not labels:
        return "Plague — dificuldade a verificar no save"
    if len(labels) > limit:
        labels = labels[:limit] + [f"+{len(labels) - limit} outras"]
    return ", ".join(labels)


def _evaluate_zone(zone: dict, drop_stages: list) -> tuple[str, str, list[tuple[int, int, int, bool]]]:
    zones = _canonical_drop_zones(drop_stages)
    if not zone:
        return "verify", "Não consegui ler a zona atual do save.", zones
    if not zones:
        return "verify", "Não há zonas de drop conhecidas para este item.", zones
    try:
        act, no = int(zone.get("act")), int(zone.get("no"))
    except (TypeError, ValueError):
        return "verify", "O save não contém uma zona que eu consiga comparar.", zones

    plague = bool(zone.get("plague"))
    if plague and zone.get("diff_index") not in {0, 1, 2, 3}:
        same_place = any(
            candidate[0] == act and candidate[1] == no and candidate[3]
            for candidate in zones
        )
        if same_place:
            return "verify", "A dificuldade atual de Plague não está indicada no save.", zones
        return "incorrect", "Esta fase não está entre as zonas de drop conhecidas do item.", zones

    try:
        diff_index = int(zone.get("diff_index"))
    except (TypeError, ValueError):
        return "verify", "O save não indica a dificuldade necessária para comparar a zona.", zones
    if diff_index not in {0, 1, 2, 3}:
        return "verify", "O save não indica a dificuldade necessária para comparar a zona.", zones
    if (act, no, diff_index, plague) in zones:
        return "correct", "A zona do save corresponde a uma fase conhecida de drop deste item.", zones
    return "incorrect", "Esta fase não está entre as zonas de drop conhecidas do item.", zones


def _zone_status_key(target: dict, account_name: str) -> str:
    return json.dumps(
        [str(target.get("name") or "").casefold(), account_name.casefold()],
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _zone_status_signature(status: str, zone: dict, zones: list,
                            reason: str) -> str:
    # Só notifica quando muda o resultado ou as zonas-base, nunca a cada fase/onda.
    return json.dumps(
        [status, zones, reason],
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    )


def notify_zone_status(alert_data: dict) -> None:
    labels = {
        "correct": "ZONA CORRETA",
        "incorrect": "ZONA INCORRETA — VERIFICA ZONA",
        "verify": "VERIFICA ZONA",
    }
    label = labels.get(alert_data.get("status"), "VERIFICA ZONA")
    message = (
        f"{label}: {alert_data.get('item') or '?'} | Conta: {alert_data.get('conta') or '?'} | "
        f"Zona no save: {alert_data.get('zone') or 'desconhecida'}"
    )
    if alert_data.get("expected"):
        message += f" | Zonas conhecidas do item: {alert_data['expected']}"
    if alert_data.get("reason"):
        message += f" | {alert_data['reason']}"
    print(f"\n[FARM] {message}", flush=True)
    try:
        tbh_discord.send_alert(alert_data)
    except Exception as exc:
        print(f"[FARM] Aviso de zona Discord falhou ({type(exc).__name__}); aviso local continua ativo.", flush=True)


def notify_drop(hit: dict) -> None:
    message = f"ITEM ENCONTRADO: {hit['name']}\nConta: {hit['conta']}\nQuantidade nova: {hit['qtd']}"
    print(f"\n\a[FARM] {message.replace(chr(10), ' | ')}", flush=True)
    try:
        tbh_discord.send_alert(hit)
    except Exception as exc:
        # A falha remota nunca impede a vigia; o drop continua visivel na dashboard.
        print(f"[FARM] Aviso Discord falhou ({type(exc).__name__}); alerta continua guardado na dashboard.", flush=True)


def poll_once(state_file: str = STATE_FILE, watch_file: str = WATCH_FILE,
              accounts_file: str = ACCOUNTS_FILE, price_file: str = PRICE_FILE,
              inventory=None, notify=notify_drop, zone_reader=None,
              notify_zone=notify_zone_status) -> list[dict]:
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
    if not isinstance(old_state, dict):
        old_state = {}
    previous = old_state.get("accounts", {})
    if not isinstance(previous, dict):
        previous = {}
    old_baselines = old_state.get("target_baselines", {})
    if not isinstance(old_baselines, dict):
        old_baselines = {}

    if inventory is None:
        try:
            import tbh_inventario as inventory
        except (Exception, SystemExit):
            inventory = None
    zone_snapshots = {}
    current, failed = scan_inventories(
        accounts, _market_names(targets, price_file), inventory,
        zone_snapshots=zone_snapshots,
    ) if accounts else ({}, set())
    if zone_reader is None and inventory is not None:
        zone_reader = _inventory_method(inventory, "zona_atual_da_conta")
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

    old_zone_statuses = old_state.get("zone_statuses", {})
    if not isinstance(old_zone_statuses, dict):
        old_zone_statuses = {}
    old_zone_unreadable = old_state.get("zone_unreadable", [])
    if not isinstance(old_zone_unreadable, list):
        old_zone_unreadable = []
    active_zone_keys = set()
    for target in targets:
        requested_account = str(target.get("conta") or "").strip()
        if requested_account:
            resolved_account = resolve_account_name(requested_account, all_accounts)
            target_accounts = [
                account for account in accounts
                if resolved_account and account["name"].casefold() == resolved_account.casefold()
            ]
        else:
            target_accounts = accounts
        active_zone_keys.update(
            _zone_status_key(target, account["name"]) for account in target_accounts
        )
    next_zone_statuses = {
        key: value for key, value in old_zone_statuses.items()
        if key in active_zone_keys
    }
    next_zone_unreadable = {
        str(name) for name in old_zone_unreadable
        if str(name).casefold() in failed_accounts
    }
    zone_notifications = []
    zone_keys_seen = set()
    if callable(zone_reader) or zone_snapshots or failed_accounts:
        for target in targets:
            requested_account = str(target.get("conta") or "").strip()
            if requested_account:
                resolved_account = resolve_account_name(requested_account, all_accounts)
                target_accounts = [
                    account for account in accounts
                    if resolved_account and account["name"].casefold() == resolved_account.casefold()
                ]
            else:
                target_accounts = accounts
            try:
                drop_stages = _drop_stages_for_name(target["name"])
            except Exception:
                drop_stages = []
            for account in target_accounts:
                account_fold = account["name"].casefold()
                if account_fold in failed_accounts:
                    if account_fold in next_zone_unreadable:
                        continue
                    zone = {}
                    next_zone_unreadable.add(account["name"])
                elif account["name"] in zone_snapshots:
                    zone = zone_snapshots[account["name"]]
                    next_zone_unreadable.discard(account["name"])
                elif callable(zone_reader):
                    try:
                        zone = zone_reader(account["save"]) or {}
                    except Exception:
                        zone = {}
                    if zone:
                        next_zone_unreadable.discard(account["name"])
                else:
                    zone = {}
                if not isinstance(zone, dict):
                    zone = {}
                if account["name"].casefold() in failed_accounts:
                    status = "verify"
                    reason = "Não consegui ler a zona atual do save."
                    zones = _canonical_drop_zones(drop_stages)
                else:
                    status, reason, zones = _evaluate_zone(zone, drop_stages)
                status_key = _zone_status_key(target, account["name"])
                signature = _zone_status_signature(status, zone, zones, reason)
                next_zone_statuses[status_key] = signature
                if status_key in zone_keys_seen:
                    continue
                zone_keys_seen.add(status_key)
                if old_zone_statuses.get(status_key) == signature:
                    continue
                zone_notifications.append({
                    "type": "zone_status",
                    "status": status,
                    "item": target["name"],
                    "name": target["name"],
                    "conta": account["name"],
                    "zone": _zone_display(zone),
                    "expected": _expected_zone_labels(zones),
                    "reason": reason,
                })

    _write_json_atomic(state_file, {
        "version": 1,
        "accounts": {**previous, **current},
        "target_baselines": next_baselines,
        "zone_statuses": next_zone_statuses,
        "zone_unreadable": sorted(next_zone_unreadable),
    })

    for zone_alert in zone_notifications:
        notify_zone(zone_alert)
    for hit in hits:
        _record_hit(hit, watch_file)
        notify(hit)
    return hits


def watch(interval: float = 2.0, report_interval: float = 900.0) -> None:
    interval = max(0.5, min(interval, 60.0))
    report_interval = max(1.0, min(report_interval, 86400.0))
    print(f"[FARM] Vigia iniciado: consulta saves a cada {interval:g}s. Deixa o run.bat aberto.", flush=True)
    last_signature = None
    last_report = time.monotonic()
    last_error_signature = None
    last_error_report = 0.0
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
                    _print_watch_summary(targets, configured_accounts)
                else:
                    print("[FARM] Sem alvos. Clica Farmar na dashboard para adicionar um item.", flush=True)
                last_report = time.monotonic()

            # Sinaliza o arranque antes do primeiro scan, para o .bat confirmar que o
            # processo existe mesmo quando ainda nao ha alvos ou saves acessiveis.
            _write_heartbeat(targets, configured_accounts, interval, status="scanning" if targets else "starting", watched_accounts=watched_accounts)
            if targets:
                hits = poll_once()
                configured_accounts = load_accounts()
                watched_accounts = _accounts_for_targets(targets, configured_accounts)
                if hits:
                    _print_watch_summary(targets, configured_accounts)
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
                now = time.monotonic()
                if now - last_report >= report_interval:
                    good = max(0, len(watched_accounts) - unreadable)
                    webhook_url, _mention_id = tbh_discord.discord_settings()
                    discord_on = (
                        tbh_discord.discord_enabled()
                        and tbh_discord.valid_webhook_url(webhook_url)
                    )
                    discord_label = "ativo" if discord_on else "desativado"
                    print(
                        f"[FARM] Continua a vigiar: {len(targets)} alvo(s); "
                        f"saves legiveis {good}/{len(watched_accounts)}; Discord {discord_label}. "
                        f"Le os saves a cada {interval:g}s; proximo resumo em "
                        f"{report_interval / 60:g} minuto(s).",
                        flush=True,
                    )
                    last_report = now
            else:
                _LAST_SCAN_ERRORS.clear()
                status = "waiting_for_targets" if configured_accounts else "no_accounts"
                _write_heartbeat(targets, configured_accounts, interval, status=status, watched_accounts=watched_accounts)
                now = time.monotonic()
                if now - last_report >= report_interval:
                    print(
                        "[FARM] Continua ativo, a espera de itens para vigiar na dashboard. "
                        f"Nao consulta saves sem alvos; proximo sinal em cada ciclo de {report_interval:g}s.",
                        flush=True,
                    )
                    last_report = now
            last_error_signature = None
        except KeyboardInterrupt:
            print("\n[FARM] Vigia parado.", flush=True)
            return
        except (Exception, SystemExit) as exc:
            error = f"{type(exc).__name__}: {exc}"
            fallback_targets = locals().get("targets", [])
            fallback_accounts = locals().get("configured_accounts", [])
            fallback_watched = locals().get("watched_accounts", [])
            _write_heartbeat(fallback_targets, fallback_accounts, interval, status="error", error=error, watched_accounts=fallback_watched)
            now = time.monotonic()
            if error != last_error_signature or now - last_error_report >= report_interval:
                print(f"[FARM] Erro no ciclo de vigia ({error}). Vou tentar novamente.", flush=True)
                last_error_signature = error
                last_error_report = now
        time.sleep(max(0.1, interval - (time.monotonic() - started)))


def _ask_yes_no(question: str) -> bool:
    while True:
        answer = input(question).strip().casefold()
        if answer in {"s", "sim", "y", "yes"}:
            return True
        if answer in {"n", "nao", "não", "no"}:
            return False
        print("Resposta invalida. Escreve S para sim ou N para nao.", flush=True)


def _print_discord_setup_instructions() -> None:
    print("\n[Discord] Para receber alertas no canal que escolheres:", flush=True)
    print("  1. Abre o canal no Discord e entra em Editar canal → Integracoes → Webhooks.", flush=True)
    print("  2. Cria um webhook novo nesse canal e copia o URL.", flush=True)
    print("  3. O URL e secreto: nao o publiques nem o envies em mensagens.", flush=True)
    print("  4. Se quiseres mencionar uma pessoa, ativa o Modo Desenvolvedor e copia o ID numerico dela.", flush=True)
    print("  5. O URL sera pedido oculto; o ID e opcional (Enter para nao mencionar).\n", flush=True)


def _collect_discord_setup(show_instructions: bool = True) -> bool:
    if show_instructions:
        _print_discord_setup_instructions()
    webhook_url = getpass.getpass("Webhook Discord novo (entrada oculta): ").strip()
    mention_id = input("ID numerico do utilizador a mencionar (Enter para nao mencionar): ").strip()
    try:
        tbh_discord.save_discord_settings(webhook_url, mention_id)
    except (OSError, ValueError) as exc:
        print(f"Configuracao Discord nao guardada: {exc}", flush=True)
        return False
    print("Configuracao Discord guardada em .env sem mostrar o webhook.", flush=True)
    return True


def _discord_prompt() -> int:
    print("\n[Discord] O envio acontece quando a vigia encontra um drop novo ou deteta uma mudanca na zona da farm.", flush=True)
    if not _ask_yes_no("Queres receber notificacoes no Discord? [S/N]: "):
        tbh_discord.set_discord_enabled(False)
        print("Discord desligado. A vigia local continua ativa.", flush=True)
        return 0

    webhook_url, mention_id = tbh_discord.discord_settings()
    configured = (
        tbh_discord.valid_webhook_url(webhook_url)
        and (not mention_id or tbh_discord.valid_discord_user_id(mention_id))
    )
    if not configured:
        print("Nao encontrei um webhook Discord valido neste computador.", flush=True)
        _print_discord_setup_instructions()
        if not _ask_yes_no("Queres configurar agora? [S/N]: "):
            tbh_discord.set_discord_enabled(False)
            print("Discord desligado. Podes configurar mais tarde; a vigia local continua ativa.", flush=True)
            return 0
        if not _collect_discord_setup(show_instructions=False):
            tbh_discord.set_discord_enabled(False)
            print("Discord desligado por agora; a vigia local continua ativa.", flush=True)
            return 0

    tbh_discord.set_discord_enabled(True)
    print("Discord ativado. Nao sera enviada mensagem de teste; os avisos saem apenas quando houver drops.", flush=True)
    return 0


def _status_hit_key(hit: dict) -> str:
    try:
        quantity = int(hit.get("qtd") or 0)
    except (TypeError, ValueError):
        quantity = 0
    return json.dumps(
        [
            str(hit.get("name") or "").casefold(),
            str(hit.get("conta") or "").casefold(),
            quantity,
            str(hit.get("time") or ""),
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _matching_target_hits(targets: list[dict], accounts: list[dict]) -> list[dict]:
    history = _watch_data()["hits"]
    return [
        hit for hit in history
        if isinstance(hit, dict)
        and any(_hit_matches_target(hit, target, accounts) for target in targets)
    ]


def _status_target_label(target: dict) -> str:
    item = str(target.get("name") or "?")
    account = str(target.get("conta") or "todas as contas")
    return f"{item} @ {account}"


def _status_report(args, compact: bool = False) -> int:
    if not compact:
        discord_label = "ativadas" if tbh_discord.discord_enabled() else "desativadas"
        print(f"Discord: notificacoes {discord_label} pela preferencia local.")

    heartbeat = watcher_status(interval=args.interval)
    heartbeat["process_running"] = _watch_process_running()
    heartbeat["alive"] = heartbeat["alive"] and heartbeat["process_running"]
    age = float(heartbeat.get("age_seconds") or 0)
    now_label = datetime.now().strftime("%H:%M:%S")
    if heartbeat["process_running"] and not heartbeat["alive"]:
        if compact:
            print(f"[{now_label}] VIGIA SEM HEARTBEAT — sem atualização há {age:.1f}s.", flush=True)
        else:
            print(f"VIGIA PRESO OU SEM HEARTBEAT — o processo existe, mas nao atualiza ha {age:.1f}s.")
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
        if compact:
            matches = _matching_target_hits(targets, status_accounts)
            total_drops = 0
            for hit in matches:
                try:
                    total_drops += max(0, int(hit.get("qtd") or 0))
                except (TypeError, ValueError):
                    continue
            if matches:
                last_drop = str(matches[-1].get("time") or "hora desconhecida")
                drops_text = f"{total_drops} unidade(s) em {len(matches)} drop(s); último: {last_drop}"
            else:
                drops_text = "nenhum drop registado para estes alvos ainda"
            state_labels = {
                "active": "VIGIA ATIVO — A VIGIAR",
                "waiting_for_targets": "VIGIA ATIVO — À ESPERA DE ALVOS",
                "save_read_error": "VIGIA ATIVO — ERRO DE SAVE",
                "partial_warning": "VIGIA ATIVO — COM AVISO",
                "account_not_found": "VIGIA ATIVO — CONTA NÃO ENCONTRADA",
                "no_accounts": "VIGIA ATIVO — SEM CONTAS",
                "starting": "VIGIA A ARRANCAR",
                "scanning": "VIGIA A LER SAVES",
                "error": "VIGIA ATIVO — COM ERRO",
            }
            unreadable = heartbeat.get("unreadable_accounts", [])
            unreadable_count = len(unreadable) if isinstance(unreadable, list) else 0
            readable_count = max(0, len(watched_accounts) - unreadable_count)
            target_labels = [_status_target_label(target) for target in targets]
            if len(target_labels) > 3:
                target_labels = target_labels[:3] + [f"+{len(target_labels) - 3} outros"]
            targets_text = ", ".join(target_labels) or "sem alvos"
            print(
                f"[{now_label}] {state_labels.get(status, 'VIGIA ATIVO')} | "
                f"última leitura: {heartbeat.get('updated_at', '?')} ({age:.1f}s) | "
                f"saves legíveis: {readable_count}/{len(watched_accounts)} | "
                f"alvos: {targets_text} | {drops_text}",
                flush=True,
            )
        else:
            print(f"VIGIA ATIVO — {heartbeat.get('target_count', len(targets))} alvo(s), estado: {status}.")
            _print_watch_summary(targets, status_accounts)
            print("Contas vigiadas: " + (", ".join(account["name"] for account in watched_accounts) or "nenhuma") + ".")
            if args.conta:
                print(f"Conta pedida: {args.conta} -> {requested_account}.")
            print(f"Ultima verificacao: {heartbeat.get('updated_at', '?')}; intervalo: {heartbeat.get('interval_seconds', '?')}s.")

        if status == "no_accounts":
            print("ERRO: o vigia esta vivo, mas nao carregou contas. Confirma config/baus.json.")
        if status == "account_not_found":
            print("ERRO: a conta associada a um alvo nao foi encontrada no ficheiro de contas.")
        if status in {"starting", "scanning"} and not compact:
            print("VIGIA A ARRANCAR — a primeira leitura dos saves ainda esta em curso.")
            return 3
        unreadable = heartbeat.get("unreadable_accounts", [])
        if isinstance(unreadable, list) and unreadable:
            if not compact:
                print("Saves com erro de leitura: " + ", ".join(str(name) for name in unreadable))
        if heartbeat.get("error"):
            if not compact:
                print("Ultimo erro do vigia: " + str(heartbeat["error"]))
        if status in {"no_accounts", "save_read_error", "partial_warning", "account_not_found", "error"} or heartbeat.get("error") or unreadable:
            if not compact:
                print("AVISO: processo ativo, mas ha erros que podem impedir alguns alertas; corrige os detalhes acima.")
            return 2
        if status in {"starting", "scanning"}:
            return 3
        if status == "waiting_for_targets":
            if not compact:
                print("VIGIA ATIVO, a espera — clica Farmar na dashboard para comecar os alertas.")
            return 4
        return 0

    if heartbeat["alive"] and heartbeat.get("status") in {"starting", "scanning"}:
        if compact:
            print(f"[{now_label}] VIGIA A ARRANCAR — primeira leitura dos saves ainda em curso.", flush=True)
        else:
            print("VIGIA A ARRANCAR — primeira leitura dos saves ainda em curso.")
        return 3
    if heartbeat["alive"] and args.conta and not requested_account:
        names = ", ".join(account["name"] for account in status_accounts) or "nenhuma"
        print(f"[{now_label}] VIGIA ATIVO, mas conta '{args.conta}' não configurada: {names}." if compact else f"VIGIA ATIVO, mas a conta '{args.conta}' nao esta na lista configurada: {names}.")
        return 2
    if heartbeat["alive"] and args.conta and not watches_requested_account:
        print(f"[{now_label}] VIGIA ATIVO, mas sem alvo associado a '{requested_account}'." if compact else f"VIGIA ATIVO, mas nao tem alvo associado a '{requested_account}'.")
        return 2
    if compact:
        print(f"[{now_label}] VIGIA INATIVO — sem heartbeat recente. Abre o run.bat e deixa-o aberto.", flush=True)
    else:
        print("VIGIA INATIVO — sem heartbeat recente. Abre o run.bat e deixa-o aberto.")
    return 1


def _status_follow(args) -> int:
    interval = max(1.0, min(float(args.status_interval), 300.0))
    seen_hits = {
        _status_hit_key(hit)
        for hit in _watch_data()["hits"]
        if isinstance(hit, dict)
    }
    print(
        f"[FARM] A acompanhar o status de {interval:g} em {interval:g}s sem limpar o ecrã. "
        "Ctrl+C para parar; os novos drops aparecem abaixo.",
        flush=True,
    )
    try:
        while True:
            _status_report(args, compact=True)
            for hit in _watch_data()["hits"]:
                if not isinstance(hit, dict):
                    continue
                signature = _status_hit_key(hit)
                if signature in seen_hits:
                    continue
                seen_hits.add(signature)
                timestamp = str(hit.get("time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                print(
                    f"\a[FARM] NOVO DROP DETETADO — {hit.get('name') or '?'} | "
                    f"Conta: {hit.get('conta') or '?'} | +{hit.get('qtd') or 0} | {timestamp}",
                    flush=True,
                )
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[FARM] Acompanhamento do status parado; a vigia de saves continua ativa.", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vigia os itens farmados e alerta quando aparecem nos saves.")
    parser.add_argument("--watch", action="store_true", help="vigia continuamente, consultando a cada 2 segundos")
    parser.add_argument("--status", action="store_true", help="acompanha continuamente o vigia, sem limpar o terminal")
    parser.add_argument("--once", action="store_true", help="com --status, mostra o estado uma vez e termina")
    parser.add_argument("--status-interval", type=float, default=5.0, help="segundos entre atualizacoes do status (predefinicao 5)")
    parser.add_argument("--check-running", action="store_true", help="verifica o bloqueio do processo sem iniciar outra vigia")
    parser.add_argument("--discord-setup", action="store_true", help="guarda o webhook e o ID opcional do utilizador num .env local")
    parser.add_argument("--test-discord", action="store_true", help="envia uma mensagem de teste para o webhook configurado")
    parser.add_argument("--interval", type=float, default=2.0, help="intervalo entre verificacoes (segundos)")
    parser.add_argument("--report-interval", type=float, default=900.0, help="intervalo entre resumos do vigia (segundos; predefinicao 15 minutos)")
    parser.add_argument("--discord-check", action="store_true", help="verifica se existe uma configuracao Discord valida sem revelar o webhook")
    parser.add_argument("--discord-prompt", action="store_true", help="pergunta se queres ativar Discord e orienta a configuracao, sem enviar mensagens")
    parser.add_argument("--discord-enable", action="store_true", help="ativa as notificacoes Discord se houver um webhook valido")
    parser.add_argument("--discord-disable", action="store_true", help="desativa as notificacoes Discord locais")
    parser.add_argument("--add", metavar="ITEM", help="adiciona um item aos alertas")
    parser.add_argument("--conta", default="", help="associa o alvo ou verifica esta conta (com --status/--add/--rm)")
    parser.add_argument("--rm", metavar="ITEM", help="remove um item dos alertas")
    parser.add_argument("--ack", metavar="ITEM", nargs="?", const="", help="confirma alertas pendentes")
    parser.add_argument("--all", action="store_true", help="confirma todos os alertas pendentes")
    args = parser.parse_args(argv)
    if args.discord_prompt:
        return _discord_prompt()
    if args.check_running:
        running = _watch_process_running()
        print("VIGIA JA EM EXECUCAO." if running else "VIGIA NAO ESTA EM EXECUCAO.", flush=True)
        return 0 if running else 1
    if args.discord_disable:
        tbh_discord.set_discord_enabled(False)
        print("Notificacoes Discord desativadas neste computador.", flush=True)
        return 0
    if args.discord_enable:
        webhook_url, mention_id = tbh_discord.discord_settings()
        if not tbh_discord.valid_webhook_url(webhook_url):
            print("Discord nao configurado; cria o webhook antes de o ativar.", flush=True)
            return 1
        if mention_id and not tbh_discord.valid_discord_user_id(mention_id):
            print("ID de mencao invalido; corrige-o antes de ativar o Discord.", flush=True)
            return 1
        tbh_discord.set_discord_enabled(True)
        print("Notificacoes Discord ativadas neste computador.", flush=True)
        return 0
    if args.discord_check:
        webhook_url, mention_id = tbh_discord.discord_settings()
        if not webhook_url or not tbh_discord.valid_webhook_url(webhook_url):
            print("Discord ainda nao esta configurado com um webhook valido.", flush=True)
            return 1
        if mention_id and not tbh_discord.valid_discord_user_id(mention_id):
            print("O webhook existe, mas o ID de mencao configurado e invalido.", flush=True)
            return 1
        print("Discord configurado; o webhook nao foi mostrado.", flush=True)
        return 0
    if args.discord_setup:
        print("\n[Discord] Antes de continuar, cria um webhook no canal onde queres os alertas:", flush=True)
        print("  1. Discord → abre o canal → Editar canal → Integracoes → Webhooks.", flush=True)
        print("  2. Cria um webhook e copia o URL. Trata-o como palavra-passe; nao o partilhes.\n", flush=True)
        print("O URL sera pedido em modo oculto. O ID numerico de mencao e opcional (Enter para nao mencionar).", flush=True)
        webhook_url = getpass.getpass("Webhook Discord (entrada oculta): ").strip()
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
        if confirmed.upper() != "SIM":
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
        if args.once:
            return _status_report(args)
        return _status_follow(args)
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
            watch(
                max(0.5, min(args.interval, 60.0)),
                max(1.0, min(args.report_interval, 86400.0)),
            )
        finally:
            _release_watch_lock(lock_fd)
        return 0
    poll_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
