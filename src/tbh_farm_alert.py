"""Vigia os alvos de farm e avisa quando um save ganha o item procurado.

O processo e arrancado por run.bat e corre enquanto essa janela estiver aberta.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

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
HEARTBEAT_FILE = os.path.join(ROOT, "var", "farm_watch.heartbeat")
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
        print(f"[FARM] AVISO: '{conta}' nao corresponde a uma conta unica. Vou vigiar todas as contas. Configuradas: {configured}.", flush=True)
    if selected_account:
        accounts = [account for account in accounts if account["name"] == selected_account]

    # Try to snapshot current inventory to prevent false positives. A missing
    # dependency/save must not prevent registering an alert: the watcher will
    # retry and establish its first baseline once it can read that save.
    current, failed = {}, set()
    try:
        current, failed = scan_inventories(accounts, _market_names([{"name": name}], price_file), inventory)
    except Exception as exc:
        failed = {account["name"] for account in accounts}
        print(f"[FARM] Snapshot inicial indisponivel ({type(exc).__name__}: {exc}); alvo registado e o vigia vai tentar novamente.", flush=True)
    folded_old = {str(account).casefold(): items for account, items in old_accounts.items()}
    for account in failed:
        if account.casefold() in folded_old:
            current[account] = folded_old[account.casefold()]
    old_baselines[_target_key({"name": name, "conta": conta})] = {
        "accounts": {account.casefold(): _item_count(items, name) for account, items in current.items()}
    }
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

    if _GAME_DATA_OWNER is not inventory or _GAME_DATA_CACHE is None:
        try:
            _GAME_DATA_CACHE = inventory.carregar_dados_jogo()
            _GAME_DATA_OWNER = inventory
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            for account in accounts:
                name = account["name"]
                failed.add(name)
                if _LAST_SCAN_ERRORS.get(name) != error:
                    print(f"[FARM] Dados do inventario indisponiveis ({error}); a tentar novamente.", flush=True)
                    _LAST_SCAN_ERRORS[name] = error
            return {}, failed
    snapshots = {}
    failed = set()
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
                     path: str = HEARTBEAT_FILE) -> None:
    """Persists a small status marker so run.bat can confirm the watcher is alive."""
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
        "unreadable_accounts": sorted(_LAST_SCAN_ERRORS),
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

    # Scans all accounts so automatic detection works, but only notifies accounts
    # selected on a target. The actual matching below enforces the target account.
    accounts = all_accounts
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

    current, failed = scan_inventories(accounts, _market_names(targets, price_file), inventory)
    previous_accounts = {str(name).casefold(): items for name, items in previous.items()}
    for name in failed:
        if name.casefold() in previous_accounts:
            current[name] = previous_accounts[name.casefold()]

    accounts_by_fold = {name.casefold(): name for name in current}
    selected_targets = [target for target in targets if target.get("conta")]
    if selected_targets and len(selected_targets) == len(targets):
        allowed_accounts = {
            (resolve_account_name(target["conta"], all_accounts) or "").casefold()
            for target in selected_targets
        } - {""}
        accounts = [account for account in accounts if account["name"].casefold() in allowed_accounts]
        current = {name: items for name, items in current.items() if name.casefold() in allowed_accounts}
        accounts_by_fold = {name.casefold(): name for name in current}
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
        for account_name, items in current.items():
            old_counts.setdefault(account_name.casefold(), _item_count(items, target["name"]))

        if target.get("conta"):
            requested_account = resolve_account_name(target["conta"], accounts)
            account = accounts_by_fold.get(requested_account.casefold()) if requested_account else None
            account_names = [account] if account else []
        else:
            account_names = list(current)

        next_counts = dict(old_counts)
        for account_name in account_names:
            account_key = account_name.casefold()
            items = current.get(account_name) or {}
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
        "accounts": current,
        "target_baselines": next_baselines,
    })

    for hit in hits:
        _record_hit(hit, watch_file)
        notify(hit)
    return hits


def watch(interval: float = 2.0) -> None:
    interval = max(0.5, min(interval, 60.0))
    print(f"[FARM] Vigia iniciado: consulta saves de 2 em 2 segundos. Deixa o run.bat aberto.", flush=True)
    last_signature = None
    while True:
        started = time.monotonic()
        try:
            targets = load_targets()
            accounts = load_accounts()
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
            _write_heartbeat(targets, accounts, interval, status="starting" if not targets else "scanning")
            poll_once()
            accounts = load_accounts()
            unreadable = len(_LAST_SCAN_ERRORS)
            if not targets:
                status = "waiting_for_targets"
            elif not accounts:
                status = "no_accounts"
            elif unreadable == len(accounts):
                status = "save_read_error"
            elif unreadable:
                status = "partial_warning"
            elif any(target.get("conta") and not resolve_account_name(target["conta"], accounts) for target in targets):
                status = "account_not_found"
            else:
                status = "active"
            _write_heartbeat(targets, accounts, interval, status=status)
            if targets:
                good = max(0, len(accounts) - unreadable)
                print(f"[FARM] {datetime.now().strftime('%H:%M:%S')} — {len(targets)} alvo(s); saves legiveis {good}/{len(accounts)}; verifica a cada {interval:g}s.", flush=True)
        except KeyboardInterrupt:
            print("\n[FARM] Vigia parado.", flush=True)
            return
        except Exception as exc:
            error = type(exc).__name__
            fallback_targets = locals().get("targets", [])
            fallback_accounts = locals().get("accounts", [])
            _write_heartbeat(fallback_targets, fallback_accounts, interval, status="error", error=error)
            print(f"[FARM] Erro no ciclo de vigia ({error}): {exc}", flush=True)
        time.sleep(max(0.1, interval - (time.monotonic() - started)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vigia os itens farmados e alerta quando aparecem nos saves.")
    parser.add_argument("--watch", action="store_true", help="vigia continuamente, consultando a cada 2 segundos")
    parser.add_argument("--status", action="store_true", help="mostra se o vigia de alertas está ativo")
    parser.add_argument("--interval", type=float, default=2.0, help="intervalo entre verificacoes (segundos)")
    parser.add_argument("--add", metavar="ITEM", help="adiciona um item aos alertas")
    parser.add_argument("--conta", default="", help="associa o alvo a uma conta (só com --add/--rm)")
    parser.add_argument("--rm", metavar="ITEM", help="remove um item dos alertas")
    parser.add_argument("--ack", metavar="ITEM", nargs="?", const="", help="confirma alertas pendentes")
    parser.add_argument("--all", action="store_true", help="confirma todos os alertas pendentes")
    args = parser.parse_args(argv)
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
        heartbeat = watcher_status(interval=args.interval)
        age = heartbeat["age_seconds"]
        status_accounts = [{"name": name} for name in heartbeat.get("accounts", [])] if isinstance(heartbeat, dict) else []
        requested_account = resolve_account_name(args.conta, status_accounts) if args.conta else None
        targets = heartbeat.get("targets", []) if isinstance(heartbeat, dict) else []
        watches_requested_account = not args.conta or any(
            not str(target.get("conta") or "").strip()
            or resolve_account_name(target.get("conta"), status_accounts) == requested_account
            for target in targets
        )
        if heartbeat["alive"] and (not args.conta or requested_account) and watches_requested_account:
            print(f"VIGIA ATIVO — {heartbeat.get('target_count', 0)} alvo(s), {heartbeat.get('account_count', 0)} conta(s), estado: {heartbeat.get('status', '?')}.")
            if args.conta:
                print(f"Conta pedida: {args.conta} -> {requested_account}.")
            print(f"Ultima verificacao: {heartbeat.get('updated_at', '?')}; intervalo: {heartbeat.get('interval_seconds', '?')}s.")
            if heartbeat.get("status") == "no_accounts":
                print("AVISO: o vigia esta vivo, mas nao carregou contas. Confirma config/baus.json.")
            if heartbeat.get("status") == "account_not_found":
                print("ERRO: conta selecionada nao encontrada no ficheiro de contas.")
            if heartbeat.get("unreadable_accounts"):
                print("Saves com erro de leitura: " + ", ".join(heartbeat["unreadable_accounts"]))
            return 0
        if heartbeat["alive"] and args.conta and not requested_account:
            print(f"VIGIA ATIVO, mas a conta '{args.conta}' nao esta na lista configurada: {', '.join(a['name'] for a in status_accounts) or 'nenhuma'}.")
            return 2
        if heartbeat["alive"] and args.conta and not watches_requested_account:
            print(f"VIGIA ATIVO, mas nao tem alvo associado a '{requested_account}'.")
            return 2
        print("VIGIA INATIVO — sem heartbeat recente. Abre o run.bat e deixa-o aberto.")
        return 1
    if args.watch:
        watch(max(0.5, min(args.interval, 60.0)))
        return 0
    poll_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
