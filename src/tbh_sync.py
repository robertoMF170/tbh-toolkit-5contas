#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tbh_sync — confirma que os saves de cada conta estão sincronizados com a Steam
ANTES de arrancar as contas (proteção contra perda de dados).

Corrido pelo run.bat como passo [2/5]:

    python -X utf8 src/tbh_sync.py --pre

Por conta (config/baus.json -> contas[] {nome, id, save[, cloud]}):
  1. SEMPRE faz backup do save local -> var/saves_backup/<conta>/ (guarda os 20 mais recentes)
  2. Compara o save local (AppData\\LocalLow\\TesseractStudio\\TaskbarHero\\SaveFile_Live.es3)
     com a cache da Steam Cloud (Steam\\userdata\\<id32>\\3678970\\ac\\WinAppDataLocalLow\\...)
  3. Save local em falta / vazio / corrompido -> restaura da cloud (ou do backup mais novo)
  4. Local != cloud -> pergunta: [R]estaurar cloud->local / [M]anter local / [P]arar arranque
     (antes de decidir, guarda também uma cópia da cloud em var/saves_backup/)

Porquê: se arrancares o jogo com um save local velho (ex.: sandbox restaurada) o jogo
sobrescreve a Steam Cloud no próximo sync e PERDES o progresso — já aconteceu.

Códigos de saída: 0 = tudo sincronizado · 1 = houve divergências/avisos
                  2 = conta SEM save utilizável (não arranques essa conta) · 3 = cancelado
Opções: --auto  não pergunta; só faz ações seguras (backup + restaurar local em falta)
"""

import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
BACKUP_ROOT = os.path.join(ROOT, "var", "saves_backup")
CLOUD_REL = os.path.join("ac", "WinAppDataLocalLow", "TesseractStudio", "TaskbarHero",
                         "SaveFile_Live.es3")
STEAM_ROOTS = [
    "C:/Program Files (x86)/Steam", "C:/Program Files/Steam",
    "C:/Steam", "C:/Steam2", "D:/Steam", "D:/Steam2", "E:/Steam", "F:/Steam",
]
STEAM_ID64_BASE = 76561197960265728
BACKUPS_POR_CONTA = 20


# ------------------------------------------------------------- config

def _carregar_baus():
    for p in (os.path.join(ROOT, "config", "baus.json"),
              os.path.join(ROOT, "baus.json"),
              os.path.join(BASE, "baus.json")):
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8-sig"))
            except Exception as e:
                print(f"tbh_sync: AVISO nao consegui ler {p}: {e}")
    return None


# ------------------------------------------------------------- util

def _slug(nome):
    return re.sub(r"[^\w\-]+", "_", str(nome))[:40] or "conta"


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _fmt(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")


def _valido(path):
    """Save utilizavel: existe, nao esta vazio e (se der) desencripta bem."""
    if not path or not os.path.isfile(path):
        return False
    if os.path.getsize(path) < 1024:
        return False
    try:
        import tbh_inventario as ti
    except Exception:
        return True  # sem validador disponivel: fica a heuristica do tamanho
    try:
        dados = ti._es3_decrypt(path)
        return isinstance(dados, dict) and bool(dados)
    except ModuleNotFoundError:
        return True  # falta o cryptography: nao sabemos, nao acusamos
    except Exception:
        return False  # nao desencripta = corrompido / a meio de escrita


def _backup(pasta, src, prefixo="SaveFile"):
    os.makedirs(pasta, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(pasta, f"{prefixo}_{ts}.es3")
    shutil.copy2(src, dst)
    antigos = sorted(glob.glob(os.path.join(pasta, f"{prefixo}_*.es3")))
    for a in antigos[:-BACKUPS_POR_CONTA]:
        try:
            os.remove(a)
        except OSError:
            pass
    return dst


def _ultimo_backup(slug):
    cands = sorted(glob.glob(os.path.join(BACKUP_ROOT, slug, "SaveFile_*.es3")))
    return cands[-1] if cands else None


def _escolha(pergunta, opcoes, default):
    try:
        r = input(pergunta).strip().lower()[:1]
    except EOFError:
        r = ""
    return r if r in opcoes else default


# ------------------------------------------------------------- steam cloud

def _cloud_dirs(conta):
    dirs = []
    if conta.get("cloud"):
        dirs.append(conta["cloud"])
    id64 = str(conta.get("id") or "")
    if id64.isdigit():
        id32 = str(int(id64) - STEAM_ID64_BASE)
        for r in STEAM_ROOTS:
            dirs.append(os.path.join(r, "userdata", id32, "3678970"))
        # sandboxes: derivar a raiz da box a partir do caminho do save local
        local = str(conta.get("save") or "")
        m = re.search(r"(?i)^(.*[\\/]sandbox[\\/][^\\/]+[\\/][^\\/]+)[\\/]user[\\/]current[\\/]", local)
        if m:
            box = m.group(1)
            for pat in ("drive/*/Program Files*/Steam*/userdata/{}/3678970",
                        "drive/*/Steam*/userdata/{}/3678970",
                        "drive/*/*/userdata/{}/3678970"):
                dirs.extend(glob.glob(os.path.join(box, pat.format(id32))))
    return dirs


def _cloud_save(dir3678970):
    cand = os.path.join(dir3678970, CLOUD_REL)
    return cand if os.path.isfile(cand) else None


def _melhor_cloud(conta):
    cands = [c for c in (_cloud_save(d) for d in _cloud_dirs(conta)) if c]
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


# ------------------------------------------------------------- por conta

def _processar(conta, auto):
    """Devolve 0 ok · 1 aviso · 2 sem save · 3 cancelado."""
    nome = conta.get("nome") or "?"
    local = conta.get("save") or ""
    slug = _slug(nome)
    print(f"— {nome}")
    if not local:
        print("    [AVISO] sem caminho de save em config/baus.json — nada a verificar.")
        return 1

    nuvem = _melhor_cloud(conta)
    pasta_bk = os.path.join(BACKUP_ROOT, slug)

    # 1) backup SEMPRE do save local atual
    if os.path.isfile(local):
        b = _backup(pasta_bk, local)
        print(f"    backup local: {os.path.basename(b)} ({os.path.getsize(local)} bytes)")

    local_ok = _valido(local)
    nuvem_ok = _valido(nuvem)

    # 2) local em falta/corrompido
    if not local_ok:
        if nuvem_ok:
            if auto or _escolha("    [AVISO] save local em falta/corrompido — restaurar da Steam Cloud? [S/n] ",
                                "sn", "s") == "s":
                os.makedirs(os.path.dirname(local), exist_ok=True)
                shutil.copy2(nuvem, local)
                print("    RESTAURADO da Steam Cloud -> save local.")
                return 1
            print("    [AVISO] ficou como estava (se arrancares o jogo, a cloud pode ser sobrescrita!).")
            return 1
        bk = _ultimo_backup(slug)
        if bk and (auto or _escolha(f"    [AVISO] sem cloud — restaurar o backup {os.path.basename(bk)}? [S/n] ",
                                    "sn", "s") == "s"):
            os.makedirs(os.path.dirname(local), exist_ok=True)
            shutil.copy2(bk, local)
            print("    RESTAURADO do backup local.")
            return 1
        print("    [ERRO] SEM save utilizavel (nem local, nem cloud, nem backup).")
        print("           NAO arranques esta conta: um save novo sobrescreve a cloud e perdes o progresso.")
        return 2

    # 3) local ok — comparar com a cloud
    if not nuvem_ok:
        print("    nota: a Steam Cloud ainda nao tem cache deste save (primeira sincronizacao?).")
        return 0
    if _md5(local) == _md5(nuvem):
        print("    OK — sincronizado com a Steam Cloud.")
        return 0

    # divergencia: guarda a cloud antes de decidir qualquer coisa
    _backup(pasta_bk, nuvem, prefixo="Cloud")
    lm, cm = os.path.getmtime(local), os.path.getmtime(nuvem)
    if lm > cm + 2:
        # caso normal: jogaste localmente e o progresso sobe para a cloud no proximo sync
        print(f"    nota: save local mais novo ({_fmt(lm)} vs cloud {_fmt(cm)}) — o progresso sobe para a cloud no proximo sync.")
        return 0
    if auto:
        print(f"    [AVISO] local ({_fmt(lm)}) != cloud ({_fmt(cm)}) — mantido o local (modo --auto).")
        return 1
    if cm > lm + 2:
        print(f"    [AVISO] a Steam Cloud e MAIS NOVA que o save local (cloud {_fmt(cm)} vs local {_fmt(lm)}).")
        print("            Manter o local sobrescreve a cloud no proximo sync e perdes progresso!")
        op = _escolha("      [R]estaurar cloud->local (recomendado) / [M]anter local / [P]arar arranque: ",
                      "rmp", "r")
    else:
        print(f"    [AVISO] save local ({_fmt(lm)}) != cloud ({_fmt(cm)}) mas sao de idades parecidas.")
        op = _escolha("      [R]estaurar cloud->local / [M]anter local / [P]arar arranque: ",
                      "rmp", "r")
    if op == "r":
        shutil.copy2(nuvem, local)
        print("    RESTAURADO da Steam Cloud -> save local (o local antigo esta no backup).")
        return 1
    if op == "m":
        print("    mantido o local — a cloud vai ser atualizada no proximo sync.")
        return 1
    print("    ARRANQUE CANCELADO — nao se mexeu em nada.")
    return 3


# ------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="Confirma sync dos saves com a Steam Cloud antes do login.")
    ap.add_argument("--pre", action="store_true", help="verificacao pre-login (default)")
    ap.add_argument("--auto", action="store_true", help="nao pergunta; so acoes seguras")
    args = ap.parse_args(argv)

    cfg = _carregar_baus()
    contas = (cfg or {}).get("contas") or []
    if not contas:
        print("tbh_sync: sem contas configuradas (config/baus.json) — nada a fazer.")
        return 0

    print("=== tbh_sync — saves locais vs Steam Cloud ===")
    nivel = 0
    for conta in contas:
        r = _processar(conta, args.auto)
        if r == 3:
            return 3
        nivel = max(nivel, r)

    if nivel == 0:
        print("=== todos os saves sincronizados ===")
    elif nivel == 1:
        print("=== ha divergencias/avisos (ve acima) ===")
    else:
        print("=== ATENCAO: ha contas SEM save utilizavel — nao as arranques ===")
    return nivel


if __name__ == "__main__":
    sys.exit(main())
