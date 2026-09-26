import os
import re
import sys
import io
import json
import base64
import urllib.parse
import tbh_arvore as ta
import tbh_mapa as tm

BASE = ta.BASE
ROOT = getattr(ta, 'ROOT', os.path.dirname(BASE))

DEFAULT_URLS = [
    "https://tbhindex.com/pt/builds/252",
    "https://tbhindex.com/pt/builds/214",
    "https://tbhindex.com/pt/builds/324",
    "https://tbhindex.com/pt/builds/141",
]

STATE_FILE = os.path.join(ROOT, "config", "builds.json")
if not os.path.exists(STATE_FILE):
    for _alt in [os.path.join(ROOT, "builds.json"), os.path.join(BASE, "builds.json")]:
        if os.path.exists(_alt): STATE_FILE = _alt; break
OUT = os.path.join(ROOT, "minhas_builds.html")

CHAR_DIR = os.path.join(ROOT, "assets", "icons_chars")
if not os.path.isdir(CHAR_DIR):
    for _alt in [os.path.join(ROOT, "icons_chars"), os.path.join(BASE, "icons_chars")]:
        if os.path.isdir(_alt): CHAR_DIR = _alt; break
GAME_ICONS_DIR = os.path.join(ROOT, "assets", "icons_passivos")
if not os.path.isdir(GAME_ICONS_DIR):
    for _alt in [os.path.join(ROOT, "icons_passivos"), os.path.join(BASE, "icons_passivos")]:
        if os.path.isdir(_alt): GAME_ICONS_DIR = _alt; break

PT_ATIVAS = {
    10101: "Investida Perfurante", 10201: "Investida de Escudo", 10301: "Golpe de Retribuição",
    10401: "Campo de Égide", 10501: "Lâmina Sagrada", 10601: "Vontade Inabalável",
    20101: "Tiro Rápido", 20201: "Tiro Disperso", 20301: "Chuva de Flechas",
    20401: "Impulso Veloz", 20501: "Flecha Perfurante", 20601: "Tiro Atravessante",
    30101: "Bola de Fogo", 30201: "Orbe de Gelo", 30301: "Relâmpago",
    30401: "Hidra de Chamas", 30501: "Nevão", 30601: "Golpe de Meteoro",
    40101: "Cura", 40201: "Bênção do Poder", 40301: "Ira dos Céus",
    40401: "Santuário", 40501: "Bênção de Proteção", 40601: "Ressurreição",
    50101: "Virote Explosivo", 50201: "Virote de Gelo", 50301: "Carregamento Rápido",
    50401: "Armadilha Carregada", 50501: "Torre de Besta", 50601: "Virote de Choque",
    60101: "Salto Impactante", 60201: "Golpe Esmagador", 60301: "Brado do Comandante",
    60401: "Impacto Sísmico", 60501: "Giro de Machado", 60601: "Sede de Sangue",
}

PT_STATS = {
    "AddHpPerHit": "HP por Golpe", "AddHpPerKill": "HP por Abate",
    "AllElementalResistance": "Resistência Elemental Total", "AreaOfEffect": "Área de Efeito",
    "Armor": "Armadura", "AttackDamage": "Dano de Ataque", "AttackSpeed": "Velocidade de Ataque",
    "BlockChance": "Chance de Bloqueio", "CastSpeed": "Velocidade de Conjuração",
    "ColdDamagePercent": "% Dano de Frio", "CooldownReduction": "Redução de Recarga",
    "CriticalChance": "Chance de Crítico", "CriticalDamage": "Dano Crítico",
    "DamageAbsorption": "Absorção de Dano", "DamageReduction": "Redução de Dano",
    "DodgeChance": "Chance de Esquiva", "ElementalDodgeChance": "Esquiva Elemental",
    "FireDamagePercent": "% Dano de Fogo", "HpLeech": "Roubo de Vida",
    "HpRegenPerSec": "Regeneração de HP/s", "IncreaseAreaOfEffectDamage": "Dano de Área Aumentado",
    "IncreaseProjectileDamage": "Dano de Projétil Aumentado", "LightningDamagePercent": "% Dano de Raio",
    "MaxDodgeChance": "Esquiva Máxima", "MaxHp": "HP Máximo", "MovementSpeed": "Velocidade de Movimento",
    "PhysicalDamagePercent": "% Dano Físico", "SkillDurationIncrease": "Duração de Skills Aumentada",
    "SkillHealIncrease": "Cura de Skills Aumentada", "SkillRangeExpansion": "Alcance de Skills Aumentado",
}


def load_stat_icon_map() -> dict:
    """Mapeia statType -> nome do icone oficial (Passive_*) a partir do statsReference do site."""
    mp = {}
    ddir = os.path.join(ROOT, "data", "tbhdata")
    if not os.path.isdir(ddir):
        for _alt in [os.path.join(ROOT, "tbhdata"), os.path.join(BASE, "tbhdata")]:
            if os.path.isdir(_alt): ddir = _alt; break
    for f in os.listdir(ddir):
        if f.startswith("statsReference"):
            s = open(os.path.join(ddir, f), encoding="utf-8").read()
            for m in re.finditer(r"([A-Za-z]+):`(Passive_[A-Za-z]+)`", s):
                mp.setdefault(m.group(1), m.group(2))
            break
    return mp


def load_game_icons() -> None:
    """Carrega os icones oficiais extraidos do jogo: passivas (via statsReference) e skills ativas (Skill_<id>)."""
    if not os.path.isdir(GAME_ICONS_DIR):
        return
    statmap = load_stat_icon_map()
    for stat, icone in statmap.items():
        p = os.path.join(GAME_ICONS_DIR, icone + ".png")
        if os.path.exists(p):
            _pref = "assets/icons_passivos/" if "assets" in GAME_ICONS_DIR else "icons_passivos/"
            ta.HERO_ICONS.setdefault(stat.lower(), _pref + icone + ".png")
    for f in os.listdir(GAME_ICONS_DIR):
        m = re.match(r"Skill_(\d{5})\.png", f)
        if m:
            _pref2 = "assets/icons_passivos/" if "assets" in GAME_ICONS_DIR else "icons_passivos/"
            ta.SKILL_ICONS[int(m.group(1))] = _pref2 + f


def nome_pt_ativa(aid, nome_en):
    return PT_ATIVAS.get(aid, nome_en)


def nome_pt_stat(stat):
    return PT_STATS.get(stat, stat)


def normalize_url(u: str) -> str:
    u = u.strip()
    if not u.startswith("http"):
        u = "https://" + u
    return u.split("?", 1)[0].split("#", 1)[0]


MIX_RE = re.compile(r"^mix:(\d+)\+(\d+)$")


def misturar(imortal: dict, equipa: dict) -> dict:
    """MISTURA: herois da build 'imortal' (ex: priest da 214) + os herois
    da 'equipa' (ex: hunter/ranger da 153) que ainda nao estejam la."""
    def base(h):
        return re.sub(r"\s*\(level \d+\)", "", h).strip().lower()

    ja_ha = {base(sec["hero"]) for sec in imortal["sections"]}
    secs = list(imortal["sections"]) + [s for s in equipa["sections"] if base(s["hero"]) not in ja_ha]
    t1 = imortal["title"].split("(")[0].strip()[:44]
    t2 = equipa["title"].split("(")[0].strip()[:44]
    extra = ", ".join(re.sub(r"\s*\(level \d+\)", "", s["hero"]).strip() for s in equipa["sections"]
                     if base(s["hero"]) not in ja_ha) or "nenhum (herois repetidos)"
    notas = (
        "MISTURA de duas builds: " + t1 + " + " + t2 + ". "
        "O PRIEST segue a build imortal (ataque basico + attack speed + life leech, SEM Wrath of Heaven — "
        "nota do autor: leech por cast e' inconsistente e caro). Os outros herois (" + extra + ") vem da "
        "segunda build. O priest imortal precisa de DPS que mate rapido; se o dano nao chegar, baixa a "
        "intensidade da plague. Fontes: tbhindex.com/pt/builds (ver links no cartao)."
    )
    return {"title": "MISTURA: " + t1 + " + " + t2,
            "url": imortal.get("url", ""),
            "notes": notas,
            "category": imortal.get("category") or equipa.get("category") or "",
            "sections": secs}


def carregar_build(entry: str) -> dict:
    """Entry normal (URL do tbhindex) ou mistura 'mix:PRIEST+EQUIPA'.
    Aceita sufixo opcional '|user=Nome da Conta' (ignorado aqui; usado no cartao)."""
    entry = str(entry).strip()
    if "|user=" in entry:
        entry = entry.split("|user=", 1)[0]
    m = MIX_RE.match(entry)
    if not m:
        return ta.fetch_build(entry)
    partes = []
    for bid in (m.group(1), m.group(2)):
        u = resolve_url(f"https://tbhindex.com/pt/builds/{bid}") or f"https://tbhindex.com/pt/builds/{bid}"
        partes.append(ta.fetch_build(u))
    mix = misturar(partes[0], partes[1])
    mix["url"] = entry
    return mix


def load_urls() -> list:
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE, encoding="utf-8"))["urls"]
        except Exception:
            pass
    save_urls(DEFAULT_URLS)
    return list(DEFAULT_URLS)


def save_urls(urls: list) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"urls": urls}, f, indent=1)


def resolve_url(u: str):
    """Devolve a primeira variante (pt/en) que abre e tem conteudo real, ou None."""
    cands = [u]
    if "/pt/builds/" in u:
        cands.append(u.replace("/pt/builds/", "/builds/"))
    else:
        cands.append(re.sub(r"(tbhindex\.com)/builds/", r"\1/pt/builds/", u))
    for cand in cands:
        try:
            html = ta.http_get(cand)
        except Exception:
            continue
        if "Skills:" in html:
            return cand
    return None


def install_protocol() -> None:
    import winreg
    key = r"Software\Classes\tbh"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "URL:Taskbar Hero Builds")
        winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\shell\open\command") as k:
        cmd = f'"{sys.executable}" "{os.path.join(BASE, "tbh_protocol.py")}" "%1"'
        winreg.SetValueEx(k, None, 0, winreg.REG_SZ, cmd)
    print("protocolo tbh:// instalado (" + sys.executable + ")")


def handle_cli() -> list:
    raw = sys.argv[1:]
    # flags silenciosas usadas pelo farm em ciclo — não são comandos de build
    args = [a for a in raw if a not in ("--sem-abrir", "--silencioso", "--so-html")]
    urls = load_urls()
    if not args:
        return urls
    if args[0] == "--install-protocol":
        install_protocol()
    elif args[0] == "--add" and len(args) > 1:
        u = normalize_url(args[1])
        if u in urls:
            print("ja existe: " + u)
        else:
            real = resolve_url(u)
            if not real:
                print("ERRO: essa build nao existe (ou o site nao a mostra) — nada alterado")
                print("       confirma o numero da build na lista de builds do tbhindex.com")
                return urls
            if real != u:
                print("a variante pedida nao existe; a usar: " + real)
            urls.append(real)
            save_urls(urls)
            print("adicionada: " + real)
    elif args[0] == "--rm" and len(args) > 1:
        t = args[1]
        u = None
        if t.isdigit():
            i = int(t) - 1
            if 0 <= i < len(urls):
                u = urls[i]
        else:
            u = normalize_url(t)
            if u not in urls:
                u = None
        if u:
            urls.remove(u)
            save_urls(urls)
            print("removida: " + u)
        else:
            print("nao encontrei: " + t)
    elif args[0] in ("--sem-abrir", "--silencioso"):
        pass
    else:
        print("uso: python tbh_site.py [--add URL | --rm N_ou_URL | --install-protocol | --sem-abrir]")
    return urls


def _steam_users() -> dict:
    """nome da conta em baus.json -> username Steam (do cache do tbh_baus)."""
    try:
        _baus_cache_p = os.path.join(ROOT, "baus_cache.json") if os.path.exists(os.path.join(ROOT, "baus_cache.json")) else (os.path.join(ROOT, "var", "baus_cache.json") if os.path.exists(os.path.join(ROOT, "var", "baus_cache.json")) else os.path.join(BASE, "baus_cache.json"))
        c = json.load(open(_baus_cache_p, encoding="utf-8-sig"))
        out = {}
        for it in (c.get("payload") or {}).get("contas", []):
            if it.get("username"):
                out[it.get("nome")] = it["username"]
        return out
    except Exception:
        return {}


def _progresso_contas() -> dict:
    """nome da conta -> progresso (estagio/dificuldade/herois) do save local."""
    try:
        from tbh_inventario import progresso_da_conta
        _baus_p = os.path.join(ROOT, "config", "baus.json") if os.path.exists(os.path.join(ROOT, "config", "baus.json")) else (os.path.join(ROOT, "baus.json") if os.path.exists(os.path.join(ROOT, "baus.json")) else os.path.join(BASE, "baus.json"))
        cfg = json.load(open(_baus_p, encoding="utf-8-sig"))
        out = {}
        for c in cfg.get("contas", []):
            p = progresso_da_conta(c.get("save", ""))
            if p:
                out[c.get("nome") or c.get("id", "?")] = p
        return out
    except Exception:
        return {}



def _save_state_para_render(nome_conta: str, save_path: str) -> dict:
    """Devolve {"attrs": {id: lvl}, "grupos": {heroCode: n_grupos}, "runas": {id: lvl}, "ouro": int} ou {} se não conseguir ler."""
    if not nome_conta or not save_path:
        return {}
    try:
        # ler via tbh_inventario._es3_decrypt + _save_legivel (mesma leitura que o monitor)
        from tbh_inventario import _es3_decrypt, _save_legivel
        p = _es3_decrypt(_save_legivel(save_path))
    except Exception:
        return {}
    attrs = {}
    for a in p.get("attributeSaveDatas") or []:
        try:
            if a.get("Level"):
                attrs[int(a["Key"])] = int(a["Level"])
        except Exception:
            pass
    grupos = {}
    for h in p.get("heroSaveDatas") or []:
        try:
            if h.get("IsUnLock") and h.get("heroKey"):
                grupos[int(h["heroKey"])] = len(h.get("unlockedAttributeGroupKeys") or [])
        except Exception:
            pass
    runas = {}
    for r in p.get("RuneSaveData") or []:
        try:
            runas[int(r["RuneKey"])] = int(r.get("Level") or 0)
        except Exception:
            pass
    ouro = 0
    for c in p.get("currenySaveDatas") or []:
        if c.get("Key") == 100001:
            try:
                ouro = int(c.get("Quantity") or 0)
            except Exception:
                pass
    return {"attrs": attrs, "grupos": grupos, "runas": runas, "ouro": ouro}



def _itens_do_save_set(save_path: str) -> set:
    """Nomes de itens que já tens no inventário/baú (para marcar gear)."""
    if not save_path:
        return set()
    try:
        from tbh_inventario import carregar_dados_jogo, _save_legivel, _es3_decrypt, nome_de_mercado
        dados = carregar_dados_jogo()
        p = _es3_decrypt(_save_legivel(save_path))
        por_uid = {i.get("UniqueId"): i for i in p.get("itemSaveDatas", [])}
        equipados = set()
        for h in p.get("heroSaveDatas", []):
            for uid in (h.get("equippedItemIds") or []):
                if uid:
                    equipados.add(uid)
        nomes = set()
        for zona in ("stashSaveDatas", "inventorySaveDatas"):
            for slot in p.get(zona, []) or []:
                uid = slot.get("ItemUniqueId")
                if not uid or uid in equipados:
                    continue
                it = por_uid.get(uid)
                if not it:
                    continue
                nm = nome_de_mercado(it.get("ItemKey"), dados, None)
                if nm:
                    nomes.add(nm.lower())
        return nomes
    except Exception:
        return set()

def _gear_comparado(build_secs: list, itens_da_conta: set) -> list:
    """Marca gear da build vs. itens do inventário (visto no save)."""
    return build_secs  # compat: o check real é feito no template de passo a passo via overlay

def _dif_badge(txt: str, dif: str) -> str:
    """'22-2 Hell (onda 7)' + 'Hell' -> '22-2 <badge>Hell</badge> (onda 7)'"""
    if not txt:
        return ""
    if dif and dif in txt:
        head, _, tail = txt.partition(dif)
        return esc(head) + '<span class="bdif dif-' + dif.lower() + '">' + esc(dif) + "</span>" + esc(tail)
    return esc(txt)


def _alvos_da_build(build: dict, ideal: list = None) -> dict:
    """{skills: {id: nivel_alvo}, runas: [rota ideal], ordem: {id: passo}} da build
    (para o plano UPAR JÁ da conta). A ordem segue os passos do guia — assim o plano
    acompanha a build (incluindo as que trocam de heroi/especializacao) sem confundir
    o que ja esta feito com o que falta."""
    from tbh_inventario import HERO_NOMES
    import tbh_arvore as ta
    try:
        data = ta.load_game_data()
    except Exception:
        return {"skills": {}, "runas": [], "ordem": {}}
    nome_code = {v.lower(): k for k, v in HERO_NOMES.items()}
    skills = {}
    ordem = {}
    passo = 0
    for sec in build.get("sections", []):
        hnome = re.sub(r"\s*\(level \d+\)", "", sec.get("hero", "")).strip().lower()
        if nome_code.get(hnome) is None:
            continue
        try:
            m = ta.match_section(sec, data)
        except Exception:
            continue
        for st in m.get("steps", []):
            if st.get("kind") == "desconhecida" or st.get("src") is None or st.get("lvl") is None:
                continue
            k = str(st["src"])
            skills[k] = max(skills.get(k, 0), int(st["lvl"]))
            if k not in ordem:
                ordem[k] = passo
            passo += 1
    return {"skills": skills, "runas": [int(n) for n in (ideal or [])], "ordem": ordem}


def load_char_icons() -> dict:
    out = {}
    if os.path.isdir(CHAR_DIR):
        for f in os.listdir(CHAR_DIR):
            if f.endswith(".webp"):
                _pref3 = "assets/icons_chars/" if "assets" in CHAR_DIR else "icons_chars/"
                out[f[:-5].lower()] = _pref3 + f
    return out


CHAR_ICONS = {}


def char_icon(name: str) -> str:
    return CHAR_ICONS.get(name.strip().lower(), "")


def icon_img(name: str, size: int, cls: str = "cico") -> str:
    ic = char_icon(name)
    if not ic:
        return ""
    return f'<img class="{cls}" width="{size}" height="{size}" src="{ic}" alt="{esc(name)}">'


def inject_hero_pics(svg: str) -> str:
    state = {"n": 0}

    def repl(m):
        x = int(m.group(1))
        name = m.group(2)
        ic = char_icon(name)
        if not ic:
            return m.group(0)
        d = round((state["n"] % 3) * 0.6, 1)
        state["n"] += 1
        return (
            f'<circle cx="{x + 44}" cy="50" r="55" class="zoglow" style="animation-delay:{d}s"/>'
            f'<image x="{x}" y="6" width="88" height="88" href="{ic}" class="zoopic" style="animation-delay:{d}s"/>'
            f'<text x="{x + 104}" y="66" class="zonelabel">{name}</text>'
        )

    return re.sub(r'<text x="(\d+)" y="64" class="zonelabel">([A-Za-z]+)</text>', repl, svg)


def esc(s) -> str:
    return ta.esc(s)


def strip_routeline(svg: str) -> str:
    return re.sub(r'<path d="[^"]*" class="routeline"/>', "", svg)


def build_step_rows(matched: list, data: dict, save_state: dict = None) -> tuple:
    # save_state: {"attrs": {pid: lvl}, "grupos": {heroCode: n}} ou None
    save_attrs = (save_state or {}).get("attrs") or {}
    save_grupos = (save_state or {}).get("grupos") or {}
    rows = []
    hero_blocks = []
    offset = 0
    for sec in matched:
        hero_short = re.sub(r"\s*\(level \d+\)", "", sec["hero"]).strip()
        chip = icon_img(hero_short, 16, "schip") + esc(hero_short[:3].upper())
        for j, st in enumerate(sec["steps"]):
            num = offset + j + 1
            kind = st["kind"]
            icon = {"ativa": "★", "passiva": "◆", "desconhecida": "⚠"}[kind]
            if kind == "desconhecida":
                target = esc(st["name"])
                extra = " — procura manualmente na arvore"
                cls_li = "desconhecida"
                atual_txt = ""
            else:
                r = st["ref"]
                origin = ""
                if kind == "passiva" and sec["matchedCode"] and r["heroDigit"] != sec["matchedCode"] // 100:
                    origin = " (" + data["heroes"].get(r["heroDigit"] * 100, "outro heroi") + ")"
                alvo = st["lvl"]
                maxlvl = r.get("maxLevel", "?")
                if kind == "ativa" and st.get("src") in PT_ATIVAS:
                    nome = PT_ATIVAS[st["src"]]
                elif kind == "passiva":
                    nome = PT_STATS.get(r["statType"], st["name"])
                else:
                    nome = st["name"]
                if save_state is not None and alvo is not None:
                    pid = st.get("src")
                    atual = save_attrs.get(pid, 0)
                    # tier do pid (para saber se está bloqueado)
                    # precisamos achar tier índice
                    _ti = None
                    tree_tmp = data["trees"].get(sec.get("matchedCode")) or {}
                    for ti_tmp, tier_tmp in enumerate(tree_tmp.get("tiers") or []):
                        if pid in tier_tmp.get("passives", []) or pid in tier_tmp.get("actives", []):
                            _ti = ti_tmp
                            break
                    _grupos_tmp = save_grupos.get(sec.get("matchedCode"), 999)
                    _locked = (_ti is not None and _ti > _grupos_tmp)
                    if _locked:
                        lvtxt = f' <span style="color:#a89878">\U0001F512 bloqueada T{_ti+1} (sobe o her\u00f3i)</span>'
                        cls_li = "locked"
                        atual_txt = f' <span class="rec-dim">({atual}/{alvo})</span>'
                    elif atual >= alvo:
                        lvtxt = f' \u2713 <b>{atual}/{alvo}</b> FEITO'
                        cls_li = "done"
                        atual_txt = ""
                    elif atual > 0:
                        lvtxt = f' {atual}\u2192<b>{alvo}</b>/{maxlvl} <span class="rec-dim">(falta {alvo-atual})</span>'
                        cls_li = "partial"
                        atual_txt = ""
                    else:
                        lvtxt = f' 0\u2192<b>{alvo}</b>/{maxlvl}'
                        cls_li = "todo"
                        atual_txt = ""
                else:
                    if alvo is not None:
                        lvtxt = f' \u2192 sobe at\u00e9 <b>{alvo}</b>/<b>{maxlvl}</b>'
                    else:
                        lvtxt = ""
                    cls_li = ""
                    atual_txt = ""
                target = f'{esc(nome)}{lvtxt}{origin}{atual_txt}'
                extra = (" \u2014 " + esc(st["note"])) if st["note"] else ""
            rows.append(
                f'<li class="{cls_li}"><span class="badge">{num}</span>'
                f'<span class="hchip">{chip}</span><span class="kicon">{icon}</span>'
                f'<span>{target}{extra}</span></li>'
            )
        offset += len(sec["steps"])
        gear_html = ""
        if sec["gear"]:
            gear_items = []
            for g in sec["gear"]:
                if ":" in g:
                    slot, name = g.split(":", 1)
                    name = name.strip()
                    q = urllib.parse.quote(name)
                    gear_items.append(
                        f'{esc(slot.strip())}: <a class="ilink" href="https://steamcommunity.com/market/search?appid=3678970&q={q}" target="_blank">{esc(name)}</a>'
                    )
                else:
                    gear_items.append(esc(g))
            gear_html = '<div class="gear"><b>' + esc(hero_short) + ' gear:</b> ' + ", ".join(gear_items) + "</div>"
        prio_html = ""
        if sec["priority"]:
            prio_html = '<div class="gear"><b>' + esc(hero_short) + ' stat priority:</b> ' + esc(", ".join(sec["priority"])) + "</div>"
        hero_blocks.append(gear_html + prio_html)
    return rows, hero_blocks


CSS = """
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:'Segoe UI',system-ui,sans-serif; background:#0e0c0a; color:#e8dcc0; }
  .hidden { display:none !important; }

  /* ---------- HOME ---------- */
  #home { position:fixed; inset:0; overflow:auto; }
  .homewrap { max-width:960px; margin:0 auto; padding:46px 26px 80px; }
  .homewrap h1 { margin:0 0 4px; font-size:30px; color:#ffd86b; letter-spacing:2px; }
  .homewrap .sub { color:#a89878; font-size:13.5px; margin-bottom:30px; }
  .cards { display:flex; flex-direction:column; gap:14px; }
  .card { background:#161310; border:2px solid #7a6848; border-radius:14px; padding:16px 22px 16px 18px; cursor:pointer; transition:transform .12s, border-color .12s, background .12s; }
  .card:hover { transform:translateX(6px); border-color:#ffd86b; background:#1d1913; }
  .card.bcard { display:flex; align-items:center; gap:22px; flex-wrap:wrap; }
  .buser { font-weight:600; color:#a89878; font-size:11px; }
  .bprog { font-size:11px; color:#c8b890; margin-top:4px; }
  .bdif { font-weight:700; padding:1px 8px; border-radius:6px; display:inline-block; font-size:11px; }
  .bdif.dif-normal { background:#2a4a2a; color:#7ee787; }
  .bdif.dif-nightmare { background:#4a3a2a; color:#e3b341; }
  .bdif.dif-torment { background:#4a2a2a; color:#ff9d9d; }
  .bdif.dif-hell { background:#4a1f1f; color:#ff7070; }
  .bherois { display:flex; gap:5px; flex-wrap:wrap; margin-top:4px; }
  .hchip { background:#241f18; border:1px solid #5a4e38; border-radius:999px; padding:2px 9px; font-size:10.5px; color:#e8dcc0; }
  .hchip b { color:#ffd86b; }
  .cnum { flex:0 0 auto; display:inline-flex; align-items:center; justify-content:center; width:34px; height:34px; border-radius:50%; background:#ffd86b; color:#141210; font-weight:800; font-size:15px; }
  .cmain { flex:1 1 340px; min-width:240px; }
  .ctitle { font-size:17px; font-weight:700; color:#f0e6cc; line-height:1.35; margin-bottom:7px; }
  .cheroes { display:flex; gap:14px; flex-wrap:wrap; margin:0; flex:0 0 auto; }
  .herofig { display:flex; flex-direction:column; align-items:center; gap:3px; animation:floaty 3.4s ease-in-out infinite; }
  .herofig:nth-child(2) { animation-delay:.45s; }
  .herofig:nth-child(3) { animation-delay:.9s; }
  .herofig:nth-child(4) { animation-delay:1.35s; }
  .cico { display:block; border-radius:12px; border:2px solid #7a6848; background:#0e0c0a; transition:transform .15s, border-color .15s, box-shadow .15s; }
  .card:hover .cico { transform:scale(1.16) rotate(-2deg); border-color:#ffd86b; box-shadow:0 0 20px rgba(255,216,107,.5); }
  .hname { font-size:10.5px; font-weight:800; letter-spacing:1px; color:#ffd86b; }
  .hlvl { font-size:9.5px; color:#a89878; }
  @keyframes floaty { 0%,100% { transform:translateY(0); } 50% { transform:translateY(-5px); } }
  @keyframes pulsering { 0%,100% { opacity:.15; } 50% { opacity:.75; } }
  .schip { display:inline-block; vertical-align:-3px; margin-right:2px; border-radius:3px; transition:transform .12s; }
  .steps li:hover .schip { transform:scale(1.7); }
  .bvheroes { display:flex; gap:8px; flex-wrap:wrap; margin:6px 0 4px; }
  .bvhero { display:inline-flex; align-items:center; gap:6px; background:#241f18; border:1px solid #7a6848; border-radius:8px; padding:3px 10px; font-size:12px; font-weight:800; letter-spacing:1px; color:#ffd86b; animation:floaty 3.8s ease-in-out infinite, heroglow 3.8s ease-in-out infinite; }
  .bvhero:nth-child(2) { animation-delay:.5s; }
  .bvhero:nth-child(3) { animation-delay:1s; }
  .bvhero img { display:block; border-radius:5px; border:1px solid #57492f; }
  .bvhero b { color:#a89878; font-weight:600; }
  @keyframes heroglow { 0%,100% { border-color:#7a6848; box-shadow:0 0 0 rgba(255,216,107,0); } 50% { border-color:#ffd86b; box-shadow:0 0 12px rgba(255,216,107,.35); } }
  .zoopic { animation:floaty 3.2s ease-in-out infinite; transform-box:fill-box; transform-origin:center; }
  .zoglow { fill:#ffd86b; opacity:.18; animation:pulsering 3.2s ease-in-out infinite; }

  /* ---------- MEUS BAUS ---------- */
  .bausect { margin:0 0 34px; }
  .bhead { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; margin-bottom:12px; }
  .bhead h2 { margin:0; font-size:19px; color:#ffd86b; letter-spacing:2px; }
  .bsub2 { font-size:11.5px; color:#a89878; }
  .bwarn { color:#ffb0b0; }
  .btotal { background:linear-gradient(135deg,#241d10,#161310); border:2px solid #ffd86b; border-radius:14px; padding:14px 22px; margin-bottom:12px; }
  .btotal .blab { font-size:11px; font-weight:800; letter-spacing:2px; color:#a89878; }
  .btotal .bnum { font-size:34px; font-weight:800; color:#ffd86b; letter-spacing:1px; text-shadow:0 0 18px rgba(255,216,107,.35); }
  .btotal .bsub { font-size:12px; color:#c8b890; }
  .baugrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(215px,1fr)); gap:10px; }
  .baucard { background:#161310; border:2px solid #7a6848; border-radius:12px; padding:12px 14px; transition:border-color .12s, transform .12s; }
  .baucard:hover { border-color:#ffd86b; transform:translateY(-2px); }   .baucard.vazio { border-style:dashed; opacity:.85; }
   .baucard.link { cursor:pointer; }
   .baucard.link:hover { border-color:#e8b54a; transform:translateY(-2px); }
   .baucard.link::after { content:"📦 abrir inventário"; display:block; margin-top:6px; font-size:11px; color:#c9a86a; }
  .bnome { font-size:13px; font-weight:800; color:#f0e6cc; margin-bottom:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .bnome a { color:#ffd86b; text-decoration:underline; }
  .bvalor { font-size:21px; font-weight:800; color:#ffd86b; }
  .bsub { font-size:11.5px; color:#c8b890; margin-top:2px; }
  .binfo { font-size:10.5px; color:#a89878; margin-top:5px; line-height:1.45; }
  .bnote { font-size:10.5px; color:#8a7a5a; margin-top:10px; line-height:1.5; }
  .bnote a, .bsub2 a { color:#ffd86b; text-decoration:underline; }
  .cmdtxt { font-family:Consolas,monospace; background:#0e0c0a; border:1px solid #5a4e38; border-radius:5px; padding:1px 6px; color:#ffd86b; }
  .bauhint { background:#161310; border:2px dashed #7a6848; border-radius:12px; padding:13px 18px; font-size:12.5px; color:#c8b890; line-height:1.6; margin:0 0 30px; }
  .bauhint a { color:#ffd86b; text-decoration:underline; }

  /* ---------- trash / add / modal ---------- */
  .card { position:relative; }
  .trash { position:absolute; top:10px; right:10px; background:#241f18; color:#c8b890; border:1px solid #5a4e38; border-radius:8px; padding:6px 8px; cursor:pointer; opacity:0; transition:opacity .15s, color .15s, border-color .15s, background .15s; display:inline-flex; z-index:2; }
  .card:hover .trash { opacity:1; }
  .trash:hover { color:#ffb0b0; border-color:#7a4040; background:#3a2020; }
  .addcard { border-style:dashed; display:flex; flex-direction:row; align-items:center; justify-content:center; gap:14px; min-height:72px; color:#a89878; }
  .addcard:hover { color:#ffd86b; }
  .addtxt { font-size:12px; font-weight:800; letter-spacing:2px; }
  #modal { position:fixed; inset:0; background:rgba(8,6,4,.8); z-index:50; display:flex; align-items:center; justify-content:center; }
  .mbox { background:#161310; border:2px solid #7a6848; border-radius:14px; padding:22px 24px; width:min(480px, 92vw); }
  .mbox h3 { margin:0 0 10px; color:#ffd86b; font-size:15px; letter-spacing:2px; }
  .mhint { font-size:12px; color:#a89878; line-height:1.55; margin:0 0 14px; }
  #murl { width:100%; background:#0e0c0a; border:1px solid #5a4e38; border-radius:8px; color:#f0e6cc; font-size:13px; padding:10px 12px; outline:none; }
  #murl:focus { border-color:#ffd86b; }
  .mbtns { display:flex; gap:8px; margin-top:12px; }
  .mbtns button { background:#241f18; color:#ffd86b; border:1px solid #7a6848; border-radius:8px; padding:9px 16px; font-size:12.5px; font-weight:700; cursor:pointer; letter-spacing:1px; }
  .mbtns button.primary { background:#ffd86b; color:#141210; }
  .mbtns button:hover { filter:brightness(1.15); }
  .cmdbox { margin-top:14px; background:#0e0c0a; border:1px dashed #7a6848; border-radius:8px; padding:10px 12px; font-family:Consolas,monospace; font-size:12px; color:#ffd86b; word-break:break-all; cursor:pointer; user-select:all; line-height:1.5; }
  .mstatus { font-size:11.5px; color:#9fdc9f; margin-top:10px; line-height:1.5; min-height:16px; }
  #toast { position:fixed; bottom:22px; left:50%; transform:translateX(-50%); background:#161310; border:1px solid #ffd86b; color:#f0e6cc; border-radius:10px; padding:11px 18px; font-size:12.5px; z-index:60; max-width:min(560px,90vw); cursor:pointer; line-height:1.5; box-shadow:0 4px 24px rgba(0,0,0,.6); }
  .cmeta { font-size:11.5px; color:#a89878; line-height:1.5; }
  .cmeta a { color:#ffd86b; text-decoration:underline; }
  .ccat { display:inline-block; font-size:10.5px; font-weight:800; letter-spacing:1px; color:#ffd86b; border:1px solid #7a6848; border-radius:6px; padding:2px 7px; margin-right:6px; text-transform:uppercase; }

  /* ---------- BUILD VIEW ---------- */
  header { padding:12px 26px; border-bottom:2px solid #7a6848; background:#1a1712; position:fixed; top:0; left:0; right:360px; z-index:5; }
  #backBtn { background:#241f18; color:#ffd86b; border:1px solid #7a6848; border-radius:8px; padding:6px 12px; font-size:12.5px; font-weight:700; cursor:pointer; margin-bottom:6px; }
  #backBtn:hover { background:#2a2317; }
  h1#bvTitle { margin:0; font-size:18px; color:#ffd86b; }
  header .url { font-size:12px; color:#a89878; }
  .treewrap { position:fixed; top:74px; left:0; right:360px; bottom:0; overflow:hidden; background:#0e0c0a; cursor:grab; }
  .treewrap.drag { cursor:grabbing; }
  .zoomer { transform-origin:0 0; width:max-content; }
  svg.tree { display:block; }
  .zonelabel { fill:#8a7a5a; font-size:26px; font-weight:800; letter-spacing:4px; }
  .rowlabel { fill:#6b5f4a; font-size:17px; font-weight:800; }
  .edge { stroke:#3f3626; stroke-width:3; }
  .edgebridge { stroke:#57492f; stroke-width:3; stroke-dasharray:10 8; }
  .sq { fill:#1d1913; stroke:#6b5a38; stroke-width:2; }
  .sq.used { stroke:#ffd86b; stroke-width:3; fill:#2a2314; }
  .sq.done { stroke:#4ec9a3; stroke-width:3; fill:#12261e; }
  .sq.partial { stroke:#ffb84d; stroke-width:3; fill:#2a2314; }
  .sq.todo { stroke:#ffd86b; stroke-width:3; fill:#2a2314; }
  .sq.locked { stroke:#555; stroke-width:2; fill:#0f0e0c; opacity:0.65; }
  .sq.off { fill:#131009; stroke:#332b1e; }
  .glow { fill:none; stroke:#ffd86b; stroke-width:2; opacity:0.35; }
  .glow.done { stroke:#4ec9a3; opacity:0.5; }
  .glow.partial { stroke:#ffb84d; opacity:0.45; }
  .glow.todo { stroke:#ffd86b; opacity:0.35; }
  .glow.gold { stroke:#ffd86b; opacity:0.35; }
  .ringbadge { fill:#ffd86b; stroke:#141210; stroke-width:2; }
  .under.on { fill:#f0e6cc; }
  .under.off { fill:#6b5f4a; }
  .under.gold { fill:#ffd86b; }
  .under.done { fill:#7ee787; font-weight:800; }
  .under.partial { fill:#ffd86b; }
  .under.todo { fill:#ffd86b; }
  .under.locked { fill:#a89878; font-size:11px; }
  .q { fill:#a89878; font-size:22px; font-weight:800; text-anchor:middle; }
  .stepnum { fill:#141210; font-size:13px; font-weight:800; text-anchor:middle; }
  .ptsbadge { fill:#ffd86b; font-size:17px; font-weight:800; text-anchor:middle; paint-order:stroke; stroke:#141210; stroke-width:4px; stroke-linejoin:round; }
  .steps { position:fixed; top:0; right:0; bottom:0; width:360px; background:#161310; border-left:2px solid #7a6848; padding:16px; overflow:auto; z-index:6; }
  .steps h3 { color:#ffcc4d; margin:0 0 10px; font-size:14px; letter-spacing:2px; }
  .steps ol { list-style:none; margin:0 0 6px; padding:0; display:flex; flex-direction:column; gap:8px; }
  .steps li { display:flex; gap:7px; align-items:flex-start; font-size:13px; line-height:1.45; }
  .badge { flex:0 0 24px; height:24px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font-weight:800; color:#141210; background:#ffd86b; font-size:12.5px; margin-top:1px; }
  .hchip { flex:0 0 auto; font-size:10px; font-weight:800; color:#0e0c0a; background:#a89878; border-radius:5px; padding:2px 5px; margin-top:3px; letter-spacing:1px; }
  .kicon { flex:0 0 14px; text-align:center; }
  .steps li.done { opacity:0.6; text-decoration:line-through; color:#7ee787; }
  .steps li.locked { opacity:0.5; }
  .steps li.partial { border-left:3px solid #ffb84d; padding-left:5px; }
  .steps li.todo { border-left:3px solid #ffd86b; padding-left:5px; }
  .steptxt { display:inline; }
  .gear .own { color:#7ee787; font-weight:700; }
  .gear .missing { color:#a89878; }
  .gear-owned { color:#7ee787; }
  .gear { margin-top:10px; font-size:11.5px; color:#c8b890; line-height:1.5; }
  .ilink { color:#ffd86b; text-decoration:underline; }
  .ilink:hover { color:#ffffff; }
  .warn { background:#3a2020; border:1px solid #7a4040; color:#ffb0b0; padding:8px 12px; border-radius:8px; font-size:13px; margin:10px 0; }
  .notesbox { margin-top:12px; font-size:12px; color:#c8b890; background:#12100c; border:1px solid #3a3226; border-radius:8px; padding:6px 12px; line-height:1.55; }
  .notesbox summary { cursor:pointer; color:#ffcc4d; }
  #zbtns { position:fixed; left:16px; bottom:16px; z-index:7; display:flex; gap:6px; }
  #zbtns button { background:#1a1712; color:#ffd86b; border:1px solid #7a6848; border-radius:8px; padding:6px 12px; font-size:15px; cursor:pointer; }
  #zbtns button:hover { background:#2a2317; }
  #tabs { position:absolute; right:16px; top:12px; display:flex; gap:8px; }
  #tabs button { background:#241f18; color:#ffd86b; border:1px solid #7a6848; border-radius:8px; padding:8px 14px; font-size:13px; font-weight:700; cursor:pointer; letter-spacing:1px; }
  #tabs button.on { background:#ffd86b; color:#141210; }
  #rpanel { position:absolute; right:14px; top:14px; width:270px; background:rgba(22,19,16,.95); border:1px solid #7a6848; border-radius:10px; padding:12px; z-index:5; }
  #rpanel h3 { margin:0 0 8px; font-size:13px; color:#ffd86b; letter-spacing:1px; }
  #plist { list-style:none; margin:0 0 8px; padding:0; font-size:12px; display:flex; flex-direction:column; gap:5px; max-height:300px; overflow:auto; }
  #plist li { display:flex; gap:6px; line-height:1.3; }
  #plist .n { color:#ffd86b; font-weight:800; flex:0 0 20px; }
  #ptotal { font-size:15px; font-weight:800; color:#ffd86b; margin:6px 0; }
  #pclear { background:#3a2020; color:#ffb0b0; border:1px solid #7a4040; border-radius:8px; padding:6px 10px; cursor:pointer; font-size:12px; }
  #phint { font-size:11px; color:#a89878; line-height:1.4; margin:8px 0 0; }
  #idealinfo { font-size:11px; color:#9fdc9f; background:#16211a; border:1px solid #2f4a35; border-radius:8px; padding:6px 8px; margin-bottom:8px; line-height:1.4; }
  #partinfo { font-size:12px; font-weight:800; color:#ffd86b; margin:2px 0 6px; }
  #partbar { display:flex; gap:4px; flex-wrap:wrap; margin-bottom:8px; max-height:96px; overflow:auto; }
  #partbar button { background:#241f18; color:#c8b890; border:1px solid #5a4e38; border-radius:6px; padding:4px 7px; font-size:10.5px; font-weight:700; cursor:pointer; }
  #partbar button.on { background:#ffd86b; color:#141210; }
  #presets { display:flex; gap:5px; align-items:center; margin-bottom:8px; font-size:11px; color:#a89878; flex-wrap:wrap; }
  #presets button { background:#241f18; color:#ffd86b; border:1px solid #7a6848; border-radius:6px; padding:4px 8px; font-size:11px; font-weight:700; cursor:pointer; }
  #presets button.hot { background:#ffd86b; color:#141210; }
  #presets button:hover { background:#2a2317; }
  #presets button.hot:hover { background:#ffe28a; }
  .rnode.sel rect { stroke:#ffd86b; stroke-width:3; }
  .node.owned rect { stroke:#4ec9a3 !important; stroke-width:3; fill:#12261e !important; }
  .node.buyable rect { stroke:#ffb84d !important; stroke-width:3; }
  .node.locked rect { stroke:#555 !important; opacity:0.45; }
  .node.owned image { opacity:1 !important; }
  .node.buyable image { opacity:1 !important; }
  .node.locked image { opacity:0.35 !important; }
  @keyframes recpulse { 0%,100% { stroke-width:4; } 50% { stroke-width:8; } }
  .recflash rect { stroke:#7dff7d !important; stroke-width:5 !important; animation:recpulse 1.1s ease-in-out infinite; filter:drop-shadow(0 0 14px rgba(125,255,125,.85)); }
  .recflash image { opacity:1 !important; }
  .recflash text.q { fill:#7dff7d !important; }
  #farmbar { position:sticky; top:0; z-index:4; display:flex; gap:8px; align-items:center; flex-wrap:wrap;
    background:#1a160e; border:1px solid #57492f; border-radius:10px; padding:8px 10px; margin:0 0 14px; }
  #farmbar .dot { width:10px; height:10px; border-radius:50%; background:#3fb950; box-shadow:0 0 8px rgba(63,185,80,.7); display:inline-block; }
  #farmbar .dot.idle { background:#8a7a5a; box-shadow:none; }
  #farmbar .dot.warn { background:#ffb84d; box-shadow:0 0 8px rgba(255,184,77,.7); }
  #farmbar small { color:#a89878; font-size:11px; }
  #farmbar button { background:#241f18; color:#ffd86b; border:1px solid #7a6848; border-radius:7px; padding:4px 10px; font-size:11px; font-weight:700; cursor:pointer; }
  #farmbar button.on { background:#ffd86b; color:#141210; }
  #farmbar .farmwarn { font-size:11px; color:#ffb0b0; background:#3a2020; border:1px solid #7a4040; border-radius:6px; padding:2px 8px; display:none; }
  #farmbar .farmwarn.show { display:inline-block; }
  .uphead { font-size:12px; font-weight:800; color:#ffd86b; letter-spacing:1px; margin:2px 0 10px; }
  .upsec { font-size:10.5px; letter-spacing:2px; color:#a89878; margin:14px 0 5px; font-weight:800; }
  .upsec:first-child { margin-top:0; }
  .upline { display:flex; justify-content:space-between; gap:10px; font-size:12px; color:#e8dcc0; padding:6px 8px; border-bottom:1px solid #2a2317; line-height:1.5; }
  .upline.go { cursor:pointer; border-radius:6px; }
  .upline.go:hover { background:#2a2317; outline:1px solid #8a6a2a; }
  .upline.dim { color:#8a7a5a; opacity:.75; }
  .uppos { color:#8a7a5a; font-size:11px; white-space:nowrap; }
  .upempty { color:#8a7a5a; font-size:12px; padding:8px 0; }
  .updone { color:#7ee787; font-size:13px; padding:10px 0; }
  .upline.done { color:#7ee787; opacity:.85; }
  .upsec-feito { color:#7ee787; cursor:pointer; }
  .updet summary { list-style:none; }
  .updet summary::-webkit-details-marker { display:none; }
  .bstatus { display:inline-flex; align-items:center; gap:5px; border-radius:999px; padding:2px 9px; font-size:10.5px; font-weight:800; margin-right:6px; }
  .bstatus.feita { background:#12261e; border:1px solid #2f7a2a; color:#7ee787; }
  .bstatus.pend { background:#2a2314; border:1px solid #7a6848; color:#ffd86b; }

  /* ---------- FARM OP ---------- */
  .farmOp { margin:0 0 28px; background:linear-gradient(135deg,#1a160e,#161310); border:2px solid #7a6848; border-radius:14px; padding:18px 18px 14px; }
  .farmOpHead h2 { margin:0 0 6px; font-size:17px; color:#ffd86b; letter-spacing:1.5px; }
  .farmOpSub { color:#a89878; font-size:12.5px; line-height:1.55; margin:0 0 12px; }
  .fstats { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px; }
  .fstat { background:#241f18; border:1px solid #5a4e38; border-radius:8px; padding:4px 10px; font-size:11.5px; color:#c8b890; }
  .fstat b { color:#ffd86b; }
  .progbar { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:10px; }
  .progchip { background:#1d1913; border:1px solid #7a6848; border-radius:8px; padding:4px 10px; font-size:11px; color:#e8dcc0; }
  .fpick { background:linear-gradient(135deg,#2a2314,#1d1913); border:1px solid #ffd86b; border-radius:10px; padding:10px 14px; margin-bottom:12px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  .fpick-label { font-size:11px; font-weight:800; letter-spacing:1px; color:#ffd86b; }
  .fpick-name { font-weight:800; color:#ffd86b; text-decoration:underline; font-size:13px; }
  .fpick-price { background:#ffd86b; color:#141210; font-weight:800; border-radius:6px; padding:2px 8px; font-size:12px; }
  .fpick-vol,.fpick-hint { font-size:11px; color:#a89878; }
  .fpick-drop { font-size:11px; color:#c8b890; }
  .fpick-drop .bdif { margin-left:4px; }
  .fdropcol { color:#c8b890; }
  .fdrop { display:inline-flex; gap:4px; align-items:center; flex-wrap:wrap; }
  .fdrop .bdif { font-size:10px; padding:1px 6px; }
  .fdrop.muted { color:#6b5f4a; }
  .farmTabs { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:10px; }
  .ftab { background:#241f18; color:#ffd86b; border:1px solid #7a6848; border-radius:8px; padding:7px 12px; font-size:12px; font-weight:700; cursor:pointer; letter-spacing:.5px; }
  .ftab.on { background:#ffd86b; color:#141210; }
  .ftabpan { display:none; }
  .ftabpan.on { display:block; }
  .ftabhint { color:#a89878; font-size:11.5px; margin:0 0 8px; line-height:1.5; }
  .ftablewrap { overflow:auto; border:1px solid #5a4e38; border-radius:10px; max-height:520px; }
  .ftable { width:100%; border-collapse:collapse; font-size:12.5px; }
  .ftable th { position:sticky; top:0; background:#1d1913; color:#a89878; text-align:left; padding:7px 10px; border-bottom:1px solid #5a4e38; font-size:11px; white-space:nowrap; }
  .ftable td { padding:6px 10px; border-bottom:1px solid #2a2317; white-space:nowrap; }
  .ftable tr:hover td { background:#1d1913; }
  .fname a { color:#ffd86b; text-decoration:underline; }
  .fprice { color:#7ee787; font-weight:700; }
  .fbuy { background:#241f18; color:#ffd86b; border:1px solid #7a6848; border-radius:6px; padding:3px 8px; font-size:11px; text-decoration:none; display:inline-block; }
  .fbuy:hover { background:#ffd86b; color:#141210; }
  .frank { color:#a89878; font-weight:800; font-size:11px; }
  .gchip { font-size:9px; font-weight:800; padding:1px 5px; border-radius:4px; border:1px solid #5a4e38; letter-spacing:.5px; }
  .gchip.g-cosmic { background:#2a1a4a; color:#c9a6ff; border-color:#6a4aff; }
  .gchip.g-divine { background:#1a2a3a; color:#8ecbff; border-color:#3a8cff; }
  .gchip.g-celestial { background:#1a2a2a; color:#7ee787; border-color:#2da44e; }
  .gchip.g-beyond { background:#2a2210; color:#ffb84d; border-color:#8a6a0a; }
  .gchip.g-arcana { background:#2a1a1a; color:#ff9d9d; border-color:#7a4040; }
  .gchip.g-immortal { background:#1d1913; color:#e8dcc0; }
  .gchip.g-legendary { background:#1d1913; color:#c8b890; }
  .gtier { font-size:11px; }
  .vol { font-size:11px; font-weight:700; padding:1px 6px; border-radius:4px; }
  .vol-hot { background:#1a3a1a; color:#7ee787; }
  .vol-ok { background:#1d2a1d; color:#7ee787; }
  .vol-mid { color:#c8b890; }
  .vol-low { color:#a89878; }
  .vol-none { color:#6b5f4a; }
  .vdias-fast { color:#7ee787; font-size:11px; }
  .vdias-mid { color:#c8b890; font-size:11px; }
  .vdias-slow { color:#ff9d9d; font-size:11px; }
  .vdias-none { color:#6b5f4a; font-size:11px; }
  .muted { color:#6b5f4a; }
  #farmOp .guide .bdif { font-size:10px; padding:1px 6px; }
  .guide { background:#1d1913; border:1px solid #5a4e38; border-radius:10px; margin-bottom:8px; }
  .guide summary { cursor:pointer; padding:10px 14px; font-weight:800; color:#ffd86b; font-size:13px; list-style:none; }
  .guide summary::-webkit-details-marker { display:none; }
  .guidebody { padding:0 14px 12px; font-size:12.5px; line-height:1.6; color:#e8dcc0; }
  .guidebody ol,.guidebody ul { margin:6px 0 8px 18px; }
  .guidebody code { background:#0e0c0a; border:1px solid #3a3226; border-radius:4px; padding:0 4px; color:#ffd86b; font-size:11.5px; }
  .gtip { background:#12261e; border:1px solid #2f4a35; border-radius:8px; padding:6px 10px; color:#9fdc9f; font-size:11.5px; }
  .gfoot { color:#6b5f4a; font-size:11px; margin-top:10px; line-height:1.5; }
  /* ---------- FARM POSSIVEL por build (so diarios) ---------- */
  .farmBuild { margin:10px 0 14px; background:linear-gradient(135deg,#1a160e,#161310); border:1px solid #7a6848; border-radius:10px; padding:12px 12px 10px; }
  .farmBuildHead { font-size:13px; font-weight:800; color:#ffd86b; letter-spacing:1px; margin:0 0 6px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  .fbadge { background:#ffd86b; color:#141210; font-weight:800; border-radius:6px; padding:2px 8px; font-size:11px; }
  .farmBuildHint { color:#a89878; font-size:11.5px; line-height:1.5; margin:0 0 8px; }
  .farmBuild .ftablewrap.fbwrap { max-height:360px; }
  .farmBuild .fb-slot { color:#e8dcc0; font-size:12px; }
  .fb-hero { background:#241f18; border:1px solid #5a4e38; border-radius:6px; padding:1px 6px; font-size:10.5px; font-weight:800; color:#ffd86b; }
  .fb-base { color:#a89878; font-size:11px; }
  .farmBuild-empty { border-style:dashed; opacity:.92; }
  .farmFilters { display:flex; gap:6px; align-items:center; flex-wrap:wrap; margin:6px 0 8px; }
  .farmFilters span { font-size:11px; color:#a89878; font-weight:700; }
  .ffilt { background:#241f18; color:#ffd86b; border:1px solid #7a6848; border-radius:7px; padding:4px 10px; font-size:11px; font-weight:700; cursor:pointer; }
  .ffilt.on { background:#ffd86b; color:#141210; }
  .ffilt:hover { background:#2a2317; }
  .ffilt.on:hover { background:#ffe28a; }
  /* farm em baixo HORIZONTAL — faixa no fundo da build (como no jogo) */
  #farmBottom { position:fixed; left:0; right:360px; bottom:0; z-index:6;
    background: linear-gradient(180deg, rgba(26,22,14,.98) 0%, rgba(14,12,10,.98) 100%);
    border-top:2px solid #ffd86b; border-left:none; border-right:none; border-bottom:none;
    border-radius:0; padding:10px 14px 8px; max-height:38vh; overflow:auto;
    box-shadow:0 -8px 28px rgba(0,0,0,.7); }
  #farmBottom.hidden { display:none !important; }
  #farmBottom .farmBuild { margin:0; border:none; background:none; padding:0; }
  #farmBottom .ftablewrap.fbwrap { max-height:26vh; overflow:auto; }
  #farmBottom .farmBuildHead { font-size:13px; }
  /* quando a farm esta visivel, a arvore deixa espaco em baixo */
  #buildview.with-farm #viewSkills, #buildview.with-farm #viewRunes { bottom: 220px; }
  /* botoes Farmar */
  .ffarmbtn { background:#1d1913; color:#ffd86b; border:1px solid #7a6848; border-radius:6px; padding:3px 8px; font-size:11px; font-weight:800; cursor:pointer; white-space:nowrap; }
  .ffarmbtn:hover { background:#2a2317; border-color:#ffd86b; }
  .ffarmbtn.on { background:#ffd86b; color:#141210; border-color:#ffd86b; box-shadow:0 0 10px rgba(255,216,107,.4); }
  /* barra de watch (alvos activos) */
  #farmWatchBar { margin:10px 0 12px; background:linear-gradient(135deg,#1a160e,#161310); border:1px solid #7a6848; border-radius:10px; padding:10px 14px; display:none; }
  #farmWatchBar.show { display:block; }
  #farmWatchBar h4 { margin:0 0 6px; font-size:12px; color:#ffd86b; letter-spacing:1px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  #farmWatchBar .fw-tags { display:flex; gap:6px; flex-wrap:wrap; }
  .fw-tag { background:#241f18; border:1px solid #5a4e38; border-radius:999px; padding:3px 10px; font-size:11px; color:#e8dcc0; display:inline-flex; gap:6px; align-items:center; }
  .fw-tag b { color:#ffd86b; }
  .fw-tag button { background:#3a2020; color:#ffb0b0; border:1px solid #7a4040; border-radius:5px; padding:1px 6px; cursor:pointer; font-size:10px; }
  .fw-hit { background:#12261e; border:1px solid #2f7a2a; border-radius:8px; padding:6px 10px; margin-top:6px; font-size:11.5px; color:#7ee787; display:flex; align-items:center; gap:8px; flex-wrap:wrap; animation: dhl 1.4s ease-in-out infinite; }
  .fw-hit button { background:#ffd86b; color:#141210; border:none; border-radius:6px; padding:4px 10px; font-weight:800; cursor:pointer; }
  /* quando a tab nao eh skills, esconde o farm em baixo */
  /* modal mapa: pontos dourados sobre a imagem real do jogo */
  @media (max-width: 780px) { #farmBottom { right:0; max-height:42vh; } }
  @keyframes dhl { 0%,100% { box-shadow:0 0 12px rgba(255,216,107,.35); transform:scale(1); } 50% { box-shadow:0 0 18px rgba(255,216,107,.65); transform:scale(1.02); } }
  /* ===== MAPA ESTILO JOGO (Portal) ===== */
  .gm-hint { background:#241c12; border:2px solid #c98a2a; border-radius:10px; padding:10px 12px; margin:8px 0 10px; }
  .gm-hint h4 { margin:0 0 8px; font-size:12px; color:#ffd86b; letter-spacing:1px; }
  .gm-chips { display:flex; gap:8px; flex-wrap:wrap; margin:0 0 8px; }
  .gm-chip { display:inline-flex; align-items:center; gap:6px; background:#3a2a12; border:1px solid #c98a2a; color:#ffe9b0; border-radius:8px; padding:5px 10px; font-size:12px; font-weight:800; }
  .gm-steps { margin:0; padding-left:18px; color:#f0e2c0; font-size:13px; line-height:1.9; }
  .gm-steps b { color:#ffd86b; }
  .gm-painted { display:inline-block; width:14px; height:14px; border-radius:50%; background:radial-gradient(circle at 35% 32%, #b6ff9a, #35c93a 60%, #1c7a1c); border:2px solid #0d2a0d; box-shadow:0 0 8px rgba(80,255,120,.9); vertical-align:-2px; }
  .gm-maps { display:flex; gap:14px; flex-wrap:wrap; justify-content:center; align-items:flex-start; margin:8px 0; }
  .gm-frame { position:relative; width:100%; max-width:380px; flex:1 1 300px; border:3px solid #8a5a22; border-radius:10px; overflow:hidden; background:#e9d9ac; aspect-ratio:300 / 430; box-shadow:0 6px 18px rgba(0,0,0,.5); }
  .gm-frame img { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
  .gm-frame.plague { border-color:#4e8a2a; }
  .gm-ribbon { position:absolute; top:6px; left:50%; transform:translateX(-50%); background:linear-gradient(180deg,#e2762a,#b4501a); color:#fff; font-weight:900; font-size:14px; padding:5px 26px; border-radius:8px; border:2px solid #7a3a10; box-shadow:0 2px 6px rgba(0,0,0,.5); z-index:3; white-space:nowrap; }
  .gm-ribbon.green { background:linear-gradient(180deg,#7ac24a,#4e8a2a); border-color:#2e5a16; }
  .gm-ribbon.blue { background:linear-gradient(180deg,#4a7ec2,#2a4e88); border-color:#1a2e5a; }
  .gm-ribbon.purple { background:linear-gradient(180deg,#8a4ac2,#5a2a88); border-color:#3a1a5a; }
  .gm-ribbon.tan { background:linear-gradient(180deg,#c9a86a,#a8823a); border-color:#6a4a1a; }
  .gm-frame.dif-nightmare { border-color:#3a6ea8; }
  .gm-frame.dif-hell { border-color:#b4501a; }
  .gm-frame.dif-torment { border-color:#7a3aa8; }
  .gm-plaque { position:absolute; top:40px; left:50%; transform:translateX(-50%); z-index:3; background:rgba(20,16,10,.82); border:1px solid #c98a2a; color:#ffe9b0; font-weight:800; font-size:11px; padding:3px 12px; border-radius:8px; white-space:nowrap; }
  .gm-node { position:absolute; transform:translate(-13px,-50%); z-index:2; display:flex; align-items:center; gap:5px; }
  .gm-ball { width:20px; height:20px; border-radius:50%; background:radial-gradient(circle at 35% 32%, #fffdf2, #f2e6c2 55%, #c9b484); border:3px solid #5a4222; box-shadow:0 2px 4px rgba(0,0,0,.45); flex:none; }
  .gm-lab { font-size:12px; font-weight:900; color:#2a2016; text-shadow:0 1px 0 rgba(255,245,210,.95), 0 0 3px rgba(255,245,210,.95); white-space:nowrap; }
  .gm-node.boss .gm-ball { background:radial-gradient(circle at 35% 32%, #ff8a7a, #d42a1a 55%, #7a1208); border-color:#4a0c06; }
  .gm-node.boss .gm-lab { color:#c22010; }
  .gm-node.drop { z-index:4; }
  .gm-node.drop .gm-ball { background:radial-gradient(circle at 35% 32%, #b6ff9a, #35c93a 55%, #1c7a1c); border-color:#0d2a0d; box-shadow:0 0 12px rgba(80,255,120,.95), 0 0 0 4px rgba(80,255,120,.35); animation: dhl 1.4s ease-in-out infinite; }
  .gm-node.drop .gm-lab { color:#0e7a1e; }
  .gm-node.boss.drop .gm-ball { background:radial-gradient(circle at 35% 32%, #ff8a7a, #d42a1a 55%, #7a1208); border-color:#4a0c06; box-shadow:0 0 12px rgba(80,255,120,.95), 0 0 0 4px rgba(80,255,120,.35); }
  .gm-node.boss.drop .gm-lab { color:#0e7a1e; }
  .gm-flag { width:0; height:0; border-left:10px solid #d42a1a; border-top:6px solid transparent; border-bottom:6px solid transparent; filter:drop-shadow(0 1px 2px rgba(0,0,0,.5)); flex:none; }
  .gm-legend { display:flex; gap:12px; flex-wrap:wrap; justify-content:center; font-size:11px; color:#a89878; margin:2px 0 8px; }
  .gm-legend span { display:inline-flex; align-items:center; gap:5px; }
  .gm-ball.mini { width:13px; height:13px; border-width:2px; }
  .gm-ball.mini.boss { background:radial-gradient(circle at 35% 32%, #ff8a7a, #d42a1a 55%, #7a1208); border-color:#4a0c06; }
  .gm-ball.mini.drop { background:radial-gradient(circle at 35% 32%, #b6ff9a, #35c93a 55%, #1c7a1c); border-color:#0d2a0d; box-shadow:0 0 6px rgba(80,255,120,.9); }

  /* ---------- MAPA DROP ---------- */
  .fmapbtn { background:#241f18; color:#ffd86b; border:1px solid #7a6848; border-radius:6px; padding:2px 7px; font-size:10.5px; font-weight:700; cursor:pointer; white-space:nowrap; }
  .fmapbtn:hover { background:#ffd86b; color:#141210; }
  .fmapwrap { margin-left:6px; }
  /* modal mapa */
  #dropMapModal { position:fixed; inset:0; z-index:70; display:flex; align-items:center; justify-content:center; }
  #dropMapModal.hidden { display:none !important; }
  #dropMapModal .dmmask { position:absolute; inset:0; background:rgba(8,6,4,.82); }
  .dmbox { position:relative; background:#161310; border:2px solid #7a6848; border-radius:14px; width:min(960px,96vw); max-height:88vh; overflow:auto; padding:14px 16px 12px; box-shadow:0 12px 40px rgba(0,0,0,.65); }
  .dmhead { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin:0 0 6px; }
  .dmhead h3 { margin:0; color:#ffd86b; font-size:14px; letter-spacing:1px; flex:1; min-width:220px; }
  .dmclose { background:#241f18; color:#ffd86b; border:1px solid #7a6848; border-radius:8px; padding:6px 10px; cursor:pointer; font-weight:800; }
  .dmclose:hover { background:#ffd86b; color:#141210; }
  .dmsub { color:#a89878; font-size:11.5px; line-height:1.5; margin:0 0 10px; }
  .dstages { margin-top:8px; max-height:260px; overflow:auto; border:1px solid #5a4e38; border-radius:8px; }
  .dstages table { width:100%; border-collapse:collapse; font-size:11.5px; }
  .dstages th { position:sticky; top:0; background:#1d1913; color:#a89878; text-align:left; padding:6px 8px; border-bottom:1px solid #5a4e38; font-size:10px; white-space:nowrap; }
  .dstages td { padding:5px 8px; border-bottom:1px solid #2a2317; white-space:nowrap; }
  .dmtip { color:#6b5f4a; font-size:11px; margin-top:6px; line-height:1.5; }
  .dm-toplinks { display:flex; gap:8px; flex-wrap:wrap; margin:6px 0 0; }
  .dm-toplinks a { color:#ffd86b; border:1px solid #7a6848; border-radius:6px; padding:3px 8px; font-size:11px; text-decoration:none; background:#241f18; }
  .dm-toplinks a:hover { background:#ffd86b; color:#141210; }
"""

JS = r"""
function makeZoom(wrapId,mvId,MW,start){
 const wrap=document.getElementById(wrapId),mv=document.getElementById(mvId);
 let scale=start,tx=20,ty=20,drag=null;
 function apply(){mv.style.transform=`translate(${tx}px,${ty}px) scale(${scale})`;}
 function zoom(f){const r=wrap.getBoundingClientRect(),mx=r.width/2,my=r.height/2;tx=mx-(mx-tx)*f;ty=my-(my-ty)*f;scale*=f;apply();}
 function fit(){scale=Math.min(1,(wrap.clientWidth-20)/MW);tx=(wrap.clientWidth-MW*scale)/2;ty=14;apply();}
 wrap.addEventListener('wheel',e=>{e.preventDefault();const f=e.deltaY<0?1.15:1/1.15;
  const r=wrap.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
  tx=mx-(mx-tx)*f; ty=my-(my-ty)*f; scale*=f; apply();},{passive:false});
 wrap.addEventListener('mousedown',e=>{drag={x:e.clientX,y:e.clientY,tx,ty};wrap.classList.add('drag');});
 window.addEventListener('mousemove',e=>{if(!drag)return;tx=drag.tx+e.clientX-drag.x;ty=drag.ty+e.clientY-drag.y;apply();});
 window.addEventListener('mouseup',()=>{drag=null;wrap.classList.remove('drag');});
 function goTo(nx,ny,ns){scale=ns;tx=nx;ty=ny;apply();}
 return {apply,zoom,fit,goTo};
}

const B=__DATA__;
const DROP_MAP=__DROP_MAP__;
const MAP_POS=__MAP_POS__;
window.__FARM_WATCH__=__FARM_WATCH_JSON__;
const N=B.titles.length;
const zS=B.w.map((w,i)=>makeZoom('viewSkills','skz'+i,w,0.7));
const zR=makeZoom('viewRunes','runesZoomer',B.rw,0.5);
let cur=-1,tab='S';

function showHome(){
 // devolve farm ao sidebar antes de esconder buildview
 if(cur>=0) restoreFarmToSidebar(cur);
 cur=-1;
 document.getElementById('home').classList.remove('hidden');
 document.getElementById('buildview').classList.add('hidden');
 var fb2=document.getElementById('farmBottom'); if(fb2) fb2.classList.add('hidden');
}
function syncRunes(i){
 const rs = (B.runeSync && B.runeSync[i]) || null;
 const owned = new Set((rs && rs.owned || []).map(String));
 const buyable = new Set((rs && rs.buyable || []).map(String));
 document.querySelectorAll('#viewRunes .node').forEach(g=>{
  const id=g.dataset.id;
  g.classList.remove('owned','buyable','locked');
  if(owned.has(id)) g.classList.add('owned');
  else if(buyable.has(id)) g.classList.add('buyable');
  else if(rs) g.classList.add('locked');
 });
 if(rs){
  const nOwned=owned.size, nBuy=buyable.size;
  const el=document.getElementById('runeSyncInfo');
  if(el) el.textContent=' · '+nOwned+' compradas · '+nBuy+' alcançadas por comprar';
 }
}
function showBuild(i){
 cur=i;
 document.getElementById('home').classList.add('hidden');
 document.getElementById('buildview').classList.remove('hidden');
 document.getElementById('tabU').classList.toggle('hidden', !B.up[i]);
 document.getElementById('bvTitle').textContent=B.titles[i];
 document.getElementById('bvUrl').textContent=B.urls[i];
 document.getElementById('bvHeroes').innerHTML=B.heroes[i].map(h=>{
  const parts=h.split(' · ');
  const ic=B.charIcons[parts[0].toLowerCase()]||'';
  return '<span class="bvhero">'+(ic?'<img src="'+ic+'" width="30" height="30">':'')+parts[0].toUpperCase()+(parts[1]?'<b> · '+parts[1]+'</b>':'')+'</span>';
 }).join('');
 document.querySelectorAll('#viewSkills .zoomer').forEach(e=>e.classList.add('hidden'));
 document.getElementById('skz'+i).classList.remove('hidden');
 document.querySelectorAll('#stepsS .sw').forEach(e=>e.classList.add('hidden'));
 document.getElementById('sw'+i).classList.remove('hidden');
 document.querySelectorAll('#stepsU .sw').forEach(e=>e.classList.add('hidden'));
 const uwEl=document.getElementById('uw'+i);if(uwEl)uwEl.classList.remove('hidden');
 const ic=document.getElementById('idealcat');
 ic.textContent=B.cats[i]?(' — '+B.cats[i]):'';
 setTab('S');
 zS[i].fit();
 loadRoute(i);
 syncRunes(i);
 // farm horizontal em baixo se estiver em SKILLS
 relocateFarmToBottom(i);
 if(tab!=='S') document.getElementById('farmBottom').classList.add('hidden');
}
function setTab(t){
 tab=t;
 document.getElementById('viewSkills').classList.toggle('hidden',t!=='S');
 document.getElementById('stepsS').classList.toggle('hidden',t!=='S');
 document.getElementById('viewRunes').classList.toggle('hidden',t!=='R');
 document.getElementById('stepsR').classList.toggle('hidden',t!=='R');
 document.getElementById('stepsU').classList.toggle('hidden',t!=='U');
 document.getElementById('tabS').classList.toggle('on',t==='S');
 document.getElementById('tabR').classList.toggle('on',t==='R');
 document.getElementById('tabU').classList.toggle('on',t==='U');
 var fb=document.getElementById('farmBottom');
 if(fb){
   if(t==='S' && cur>=0) fb.classList.remove('hidden'); else fb.classList.add('hidden');
 }
 if(t==='R')zR.fit();
}
document.getElementById('tabS').addEventListener('click',()=>setTab('S'));
document.getElementById('tabR').addEventListener('click',()=>setTab('R'));
document.getElementById('backBtn').addEventListener('click',showHome);
document.getElementById('zin').addEventListener('click',()=>{if(tab==='U')return;(tab==='S'?zS[cur]:zR).zoom(1.25)});
document.getElementById('zout').addEventListener('click',()=>{if(tab==='U')return;(tab==='S'?zS[cur]:zR).zoom(1/1.25)});
document.getElementById('zfit').addEventListener('click',()=>{if(tab==='U')return;(tab==='S'?zS[cur]:zR).fit()});

/* ---------- ir para runa/skill a partir das recomendacoes ---------- */
window.recGo=function(linha){
 const conta=linha.dataset.conta||'';
 const b=linha.dataset.build;
 if(b===undefined||b===''){
  if(conta)toast('A conta "'+conta+'" ainda nao tem build atribuida — adiciona |user='+conta+' ao URL no builds.json');
  return;
 }
 if(linha.dataset.runa){
  irPara(+b,'R','.node[data-id="'+linha.dataset.runa+'"]',true);
 }else if(linha.dataset.skill){
  irPara(+b,'S','g[data-key="'+linha.dataset.skill+'"]',false);
 }
 if(conta)toast('A abrir a build da conta '+conta+' no local certo');
};
function focusNodo(zi,sel,runa){
 const z=zi==='R'?zR:zS[zi];const wrap=document.getElementById(zi==='R'?'viewRunes':'viewSkills');
 const mv=document.getElementById(zi==='R'?'runesZoomer':'skz'+zi);
 const g=mv.querySelector(sel);if(!g)return;
 const m=g.getAttribute('transform').match(/translate\(([-\d.]+)[, ]+([-\d.]+)\)/);
 const tx0=m?+m[1]:0,ty0=m?+m[2]:0;
 const cx=tx0+32,cy=ty0+32;
 const wr=wrap.getBoundingClientRect();
 const sc=0.85;
 z.goTo(wr.width/2-cx*sc, wr.height/2-cy*sc, sc);
 const hl=g.cloneNode(true);hl.classList.add('recflash');hl.setAttribute('transform',g.getAttribute('transform'));
 const svg=mv.querySelector('svg');if(svg)svg.appendChild(hl);
}
function irPara(i,tabAlvo,sel,runa){
 if(cur!==i)showBuild(i);
 if(tabAlvo&&tab!==tabAlvo)setTab(tabAlvo);
 setTimeout(()=>focusNodo(runa?'R':i,sel,runa),60);
}
document.getElementById('tabU').addEventListener('click',()=>setTab('U'));


/* ---------- runas ---------- */
const routeEl=document.getElementById('runeroute'),fullEl=document.getElementById('runefull'),badgeLayer=document.getElementById('badgeLayer'),plist=document.getElementById('plist'),ptotal=document.getElementById('ptotal');
const pickedArr=[];
let part=0;const PER=15;
const centers={};
document.querySelectorAll('#viewRunes .node').forEach(g=>{
 const m=g.getAttribute('transform').match(/translate\(([-\d.]+),([-\d.]+)\)/);
 centers[g.dataset.id]=[parseFloat(m[1])+32,parseFloat(m[2])+32];
 g.addEventListener('click',()=>toggle(g.dataset.id));
});
function rkey(i){return 'tbh_site_rota_v3_'+i+'_'+encodeURIComponent((B.urls&&B.urls[i])||'')}
function save(){localStorage.setItem(rkey(cur),JSON.stringify(pickedArr[cur]))}
function loadRoute(i){
 while(pickedArr.length<=i)pickedArr.push([]);
  let v=null;try{v=JSON.parse(localStorage.getItem(rkey(i))||'null')}catch(e){}
 pickedArr[i]=(v&&v.length)?v.map(String):((B.ideals[i]&&B.ideals[i].length?B.ideals[i]:B.presets.farm||[]).map(String));
 part=0;renderR();
}
function toggle(id){const p=pickedArr[cur];const i=p.indexOf(id);if(i>=0)p.splice(i,1);else p.push(id);part=0;renderR();}
function costOf(id){
 const tEl=document.querySelector('#viewRunes .node[data-id="'+id+'"] title');
 const t=tEl?tEl.textContent.split('|'):['?','?','max 0','0'];
 return {name:t[0].trim(),costTxt:t[3].trim(),num:parseFloat(t[3].replace(/[^\d]/g,''))||0,max:parseInt((t[2]||'').replace(/[^\d]/g,''))||0};
}
function renderR(){
 const picked=pickedArr[cur]||[];
 save();
 const n=Math.max(1,Math.ceil(picked.length/PER));
 if(part>=n)part=n-1;
 document.querySelectorAll('#viewRunes .node').forEach(g=>g.classList.toggle('sel',picked.includes(g.dataset.id)));
 const bar=document.getElementById('partbar');bar.innerHTML='';
 for(let i=0;i<n;i++){
  const b=document.createElement('button');b.textContent='PARTE '+(i+1);
  if(i===part)b.classList.add('on');
  b.addEventListener('click',()=>{part=i;renderR();});
  bar.appendChild(b);
 }
 document.getElementById('partinfo').textContent='Parte '+(part+1)+' de '+n+' — runas '+(picked.length?(part*PER+1)+' a '+Math.min(picked.length,(part+1)*PER):'0');
 const seg=picked.slice(part*PER,(part+1)*PER);
 let d='',dFull='',pTotal=0,tTotal=0;
 plist.innerHTML='';
 picked.forEach(id=>{
  const p=centers[id];if(!p)return;
  dFull+=(dFull?' L ':'M ')+p[0]+' '+p[1];
  tTotal+=costOf(id).num;
 });
 seg.forEach((id,i)=>{
  const p=centers[id];if(!p)return;
  d+=(i?' L ':'M ')+p[0]+' '+p[1];
  const c=costOf(id);
  const li=document.createElement('li');li.innerHTML='<span class="n">'+(i+1)+'</span><span>'+c.name+' — '+c.costTxt+' · <b>'+c.max+' níveis</b></span>';plist.appendChild(li);
  pTotal+=c.num;
 });
 routeEl.setAttribute('d',d);
 fullEl.setAttribute('d',dFull);
 badgeLayer.innerHTML='';
 seg.forEach((id,i)=>{
  const p=centers[id];if(!p)return;
  const c=document.createElementNS('http://www.w3.org/2000/svg','circle');
  c.setAttribute('cx',p[0]);c.setAttribute('cy',p[1]);c.setAttribute('r',14);c.setAttribute('class','ringbadge');
  const t=document.createElementNS('http://www.w3.org/2000/svg','text');
  t.setAttribute('x',p[0]);t.setAttribute('y',p[1]+5);t.setAttribute('class','stepnum');t.textContent=i+1;
  badgeLayer.appendChild(c);badgeLayer.appendChild(t);
  const pt=document.createElementNS('http://www.w3.org/2000/svg','text');
  pt.setAttribute('x',p[0]);pt.setAttribute('y',p[1]-42);pt.setAttribute('class','ptsbadge');pt.textContent='×'+costOf(id).max;
  badgeLayer.appendChild(pt);
 });
 ptotal.innerHTML='Parte: <b>'+pTotal.toLocaleString('pt-PT')+'</b> ouro · Rota total: <b>'+tTotal.toLocaleString('pt-PT')+'</b> ouro';
}
document.getElementById('pclear').addEventListener('click',()=>{pickedArr[cur]=[];part=0;renderR();});
document.querySelectorAll('#presets button').forEach(b=>b.addEventListener('click',()=>{
 const g=b.dataset.g;
 pickedArr[cur]=(g==='ideal'?(B.ideals[cur]||[]):(B.presets[g]||[])).map(String);
 part=0;renderR();
}));

/* ---------- apagar / importar ---------- */
const HKEY='tbh_hidden_v2';
function getHidden(){try{return JSON.parse(localStorage.getItem(HKEY)||'[]')}catch(e){return[]}}
function setHidden(h){localStorage.setItem(HKEY,JSON.stringify(h))}
function applyHidden(){
 const hid=getHidden();let n=0;
 document.querySelectorAll('.card.bcard').forEach(c=>{
  const h=hid.includes(c.dataset.url);
  c.classList.toggle('hidden',h);
  if(!h){n++;c.querySelector('.cnum').textContent=n;}
 });
}
function copyText(t){
 if(navigator.clipboard&&navigator.clipboard.writeText){
  return navigator.clipboard.writeText(t).then(()=>true).catch(()=>false);
 }
 return Promise.resolve(false);
}
let toastTimer=null;
function toast(msg,cmd){
 const t=document.getElementById('toast');
 t.innerHTML=msg+(cmd?'<br><span class="ilink">'+cmd+'</span>':'');
 t.classList.remove('hidden');
 t.onclick=cmd?()=>copyText(cmd).then(ok=>{if(ok)toast('Comando copiado! Cola no terminal na pasta do projeto.')}):null;
 clearTimeout(toastTimer);
 toastTimer=setTimeout(()=>t.classList.add('hidden'),cmd?9000:4000);
}
function delBuild(i){
 const url=B.urls[i];
 if(!confirm('Apagar esta build do site?'))return;
 const hid=getHidden();
 if(!hid.includes(url))hid.push(url);
 setHidden(hid);
 applyHidden();
 toast('Build apagada deste site. (Para a recuperar: limpa a storage do browser ou remove-a de builds.json e regenera.)','python tbh_site.py --rm '+url);
}
function openImport(){
 document.getElementById('modal').classList.remove('hidden');
 document.getElementById('murl').focus();
}
function closeImport(){
 document.getElementById('modal').classList.add('hidden');
}
function normUrl(u){
 u=(u||'').trim();
 if(!u)return '';
 if(!u.startsWith('http'))u='https://'+u;
 u=u.split('?')[0].split('#')[0];
 if(!/tbhindex\.com\/(pt\/)?builds\/\d+/.test(u)&&!confirm('O link nao parece uma build do tbhindex.com. Continuar mesmo assim?'))return '';
 return u;
}
function doImport(){
 const u=normUrl(document.getElementById('murl').value);
 const st=document.getElementById('mstatus');
 if(!u){st.textContent='';return;}
 const cmd='python tbh_site.py --add '+u;
 const box=document.getElementById('mcmd');
 box.textContent=cmd;
 box.classList.remove('hidden');
 box.onclick=()=>copyText(cmd).then(()=>toast('Comando copiado!'));
 try{location.href='tbh://add?url='+encodeURIComponent(u);}catch(e){}
 copyText(cmd).then(ok=>{
  st.textContent=ok
   ?'A ABRIR O PYTHON — se o browser perguntar, clica ABRIR. O site regenera e abre sozinho com a build nova. Se nao abriu nada, corre UMA VEZ no terminal: python tbh_site.py --install-protocol (ou usa o comando abaixo).'
   :'Se nao abriu o Python, corre UMA VEZ no terminal: python tbh_site.py --install-protocol — ou cola o comando abaixo no terminal.';
 });
}
document.getElementById('mgo').addEventListener('click',doImport);
document.getElementById('mclose').addEventListener('click',closeImport);
document.getElementById('modal').addEventListener('click',e=>{if(e.target.id==='modal')closeImport();});
document.getElementById('murl').addEventListener('keydown',e=>{if(e.key==='Enter')doImport();if(e.key==='Escape')closeImport();});
applyHidden();
renderFarmWatchBar(window.__FARM_WATCH__);

/* ---------- modo FARM em ciclo: auto-reload a cada 2 min (só na HOME, sem perder build aberta) ---------- */
(function(){
  var LS='tbh_autoreload';
  var dot=document.getElementById('farmdot');
  var txt=document.getElementById('farmtxt');
  var btn=document.getElementById('farmtoggle');
  var warnEl=document.getElementById('farmwarn');
  function enabled(){ return localStorage.getItem(LS)!=='off'; }
  function set(on){ localStorage.setItem(LS, on?'on':'off'); syncUI(); }
  function parseGerado(){
    try{
      var el=document.querySelector('.bausect .btotal .bsub');
      if(!el) return null;
      var m=el.textContent.match(/(\d{2}\/\d{2} \d{2}:\d{2})/); // regex data dd/mm hh:mm
      if(!m) return null;
      var p=m[1].split(/[^\d]+/);
      var d=new Date(); d.setDate(+p[0]); d.setMonth(+p[1]-1);
      d.setHours(+p[2]); d.setMinutes(+p[3]); d.setSeconds(0);
      if(d.getTime()>Date.now()+12*3600*1000) d.setFullYear(d.getFullYear()-1);
      return d;
    }catch(e){ return null; }
  }
  function syncUI(){
    var on=enabled();
    var g=parseGerado();
    var stale=g && (Date.now()-g.getTime()>18*60*1000);
    if(dot){ dot.classList.toggle('idle', !on); dot.classList.toggle('warn', on && stale); }
    if(txt) txt.textContent= on ? (stale ? '⚠ parado há '+(Math.round((Date.now()-g.getTime())/60000))+' min — reabre atualizar_baus_agora.bat' : 'a atualizar sozinho a cada 15 min — deixa o farm a correr') : 'pausado — clica para voltar a atualizar sozinho';
    if(warnEl){ warnEl.classList.toggle('show', !!(on && stale)); }
    if(btn){ btn.textContent= on ? '⏸ pausar' : '▶ retomar'; btn.classList.toggle('on', on); }
  }
  if(btn) btn.addEventListener('click', function(){ set(!enabled()); });
  syncUI();
  setInterval(syncUI, 30*1000);
  // heartbeat visível: quando o .bat reescreve minhas_builds.html a página recarrega e volta com o dot verde
  setInterval(function(){
    if(!enabled()) return;
    // só recarrega na HOME; se estiver dentro de uma build não interrompe o farm a ver a árvore
    if(document.getElementById('home').classList.contains('hidden')) return;
    location.reload();
  }, 120*1000);
})();

/* ---------- filtros farm: mais caros / vender / drop / equilibrio ---------- */
window.farmSort=function(btn){
  var mode=btn.getAttribute('data-sort');
  var wrap=btn.closest('.farmBuild, .ftabpan, #farmBottom, .farmOp');
  var table = wrap ? wrap.querySelector('table.ftable') : null;
  if(!table) table=document.querySelector('#farmBottom table.ftable') || document.querySelector('.farmBuild table.ftable');
  if(!table) return;
  var tbody=table.tBodies[0]; if(!tbody) return;
  var rows=[].slice.call(tbody.rows);
  var getVal=function(tr, key){ return parseFloat(tr.getAttribute('data-'+key))||0; };
  rows.sort(function(a,b){
    if(mode==='caros') return getVal(b,'sell')-getVal(a,'sell');
    if(mode==='venda') return getVal(b,'vol')-getVal(a,'vol');
    if(mode==='drop') return getVal(a,'lvl')-getVal(b,'lvl');
    return getVal(b,'hybrid')-getVal(a,'hybrid');
  });
  rows.forEach(function(r){ tbody.appendChild(r); });
  // toggle on
  var siblings = btn.parentElement.querySelectorAll('.ffilt');
  siblings.forEach(function(x){ x.classList.toggle('on', x===btn); });
};
window.farmToggle=function(btn){
  var name=btn.getAttribute('data-farm')||'';
  if(!name) return;
  var conta=btn.getAttribute('data-conta')||'';
  // curBuild identifica a build aberta para fallback |user= se data-conta vier vazio
  try{ if(!conta && typeof cur!=='number') cur=-1; if(!conta && cur>=0 && B.urls && B.urls[cur]){ var u=B.urls[cur]||''; var m=u.match(/\|user=([^|]+)/); if(m) conta=m[1]; } }catch(e){}
  var on = btn.classList.contains('on');
  var action = on ? 'rm' : 'add';
  var url = 'tbh://farm?'+action+'='+encodeURIComponent(name) + (conta ? '&conta='+encodeURIComponent(conta) : '');
  var cmd = 'python src\\tbh_farm_alert.py --'+action+' "'+name.replace(/"/g,'')+'"' + (conta ? ' --conta "'+conta.replace(/"/g,'')+'"' : '');
  // O protocolo só regista/remove o alvo; o vigia contínuo corre no run.bat principal.
  try{ location.href=url; }catch(e){}
  // feedback visual imediato (optimistic)
  if(on){
    btn.classList.remove('on'); btn.textContent='🎯 Farmar'; btn.title='Farmar — vigia saves a cada 2s e toca alarme';
    toast('A remover: '+name+(conta?' @ '+conta:'')+'\nSe o protocolo nao abriu, corre: '+cmd, cmd);
    // limpa optimistic across builds se tirar
    document.querySelectorAll('.ffarmbtn[data-farm="'+name.replace(/"/g,'\\"')+'"]').forEach(function(b){ b.classList.remove('on'); b.textContent='🎯 Farmar'; });
  } else {
    btn.classList.add('on'); btn.textContent='✅ Farmando'; btn.title='Ja a farmar — clica para parar' + (conta?' @ '+conta:'');
    var msgConta = conta ? ('Conta: '+conta+' — vigia só essa.') : 'A vigiar TODAS — deteta sozinho qual conta droppou.';
    toast('Alerta registado: '+name+'\n'+msgConta+' O run.bat verifica os saves a cada 2s; deixa-o aberto.', conta ? ('run.bat — '+conta+' + 🔔') : 'run.bat — todas as contas + 🔔');
    // optimistic: marca todos botões com mesmo nome (várias tabs, FARM POSSÍVEL + FARM OP)
    document.querySelectorAll('.ffarmbtn[data-farm="'+name.replace(/"/g,'\\"')+'"]').forEach(function(b){ b.classList.add('on'); b.textContent='✅ Farmando'; });
    if(navigator.clipboard) navigator.clipboard.writeText('python src/tbh_farm_alert.py --add "'+name+'"'+(conta?' --conta "'+conta+'"':'')).catch(()=>{});
  }
  copyText(cmd).catch(()=>{});
  setTimeout(refreshFarmWatchBar, 900);
};
window.farmSortGlobal=function(btn){
  var mode=btn.getAttribute('data-sort');
  var pan = btn.closest('.ftabpan');
  var table = pan ? pan.querySelector('table.ftable') : null;
  if(!table) return;
  var tbody=table.tBodies[0]; if(!tbody) return;
  var rows=[].slice.call(tbody.rows);
  var getVal=function(tr,k){ return parseFloat(tr.getAttribute('data-'+k))||0; };
  rows.sort(function(a,b){
    if(mode==='caros') return getVal(b,'sell')-getVal(a,'sell');
    if(mode==='venda') return getVal(b,'vol')-getVal(a,'vol');
    if(mode==='drop') return getVal(a,'lvl')-getVal(b,'lvl');
    return getVal(b,'hybrid')-getVal(a,'hybrid');
  });
  rows.forEach(function(r){ tbody.appendChild(r); });
  pan.querySelectorAll('.ffilt').forEach(function(x){ x.classList.toggle('on', x===btn); });
};

/* ---------- farm horizontal em baixo das builds ---------- */
function relocateFarmToBottom(i){
  var src = document.getElementById('sw'+i);
  if(!src) return;
  var farmEl = src.querySelector('.farmBuild');
  var dst = document.getElementById('farmBottom');
  if(!farmEl || !dst) return;
  // move para faixa horizontal em baixo (como no jogo)
  dst.innerHTML='';
  dst.appendChild(farmEl);
  dst.classList.remove('hidden');
  document.getElementById('buildview').classList.add('with-farm');
  // ajusta altura da faixa para a arvore nao ficar por baixo (max 38vh)
  // deixa treewrap respirar — com-farm ja tem bottom 220px no CSS
}
function restoreFarmToSidebar(i){
  var dst = document.getElementById('farmBottom');
  var src = document.getElementById('sw'+i);
  if(!dst || !src) return;
  var farmEl = dst.querySelector('.farmBuild');
  if(farmEl){
    var h3 = src.querySelector('h3');
    if(h3) src.insertBefore(farmEl, h3);
    else src.prepend(farmEl);
  }
  dst.classList.add('hidden');
  document.getElementById('buildview').classList.remove('with-farm');
}
function refreshFarmWatchBar(){
  try{
    // farm_watch.json nao e legivel do browser file:// — tenta fetch se http, senao usa B meta se injected
    var bar=document.getElementById('farmWatchBar');
    if(!bar) return;
    // se B tiver farmWatch meta (injectado pelo python), renderiza
    if(window.__FARM_WATCH__){
      renderFarmWatchBar(window.__FARM_WATCH__);
    }
  }catch(e){}
}
function renderFarmWatchBar(w){
  var bar=document.getElementById('farmWatchBar');
  if(!bar||!w) return;
  var t=w.targets||[], h=(w.hits||[]).filter(x=>!x.acknowledged);
  if(!t.length && !h.length){ bar.classList.remove('show'); bar.innerHTML=''; return; }
  var html='<h4>🎯 FARM WATCH — <span style="color:#7ee787">'+t.length+' alvo(s)</span> · verifica de 2 em 2s no run.bat <button onclick="location.reload()" style="background:#241f18;color:#ffd86b;border:1px solid #7a6848;border-radius:6px;padding:2px 8px;font-size:11px;cursor:pointer;margin-left:8px;">↻ actualizar</button></h4>';
  if(t.length){
    html+='<div class="fw-tags">';
    t.forEach(function(x){
      var n=x.name||'?';
      var c=x.conta?(' @ '+x.conta):' @ todas (deteta sozinho)';
      var tip = x.conta ? ('vigia só '+x.conta) : 'vigia todas — quando dropar grava a conta real';
      html+='<span class="fw-tag" title="'+tip.replace(/"/g,'&quot;')+'"><b>'+n.replace(/</g,'&lt;')+'</b><span style="color:#a89878">'+c.replace(/</g,'&lt;')+'</span> <button onclick="location.href=\'tbh://farm?rm='+encodeURIComponent(n)+'\'">✕ parar</button></span>';
    });
    html+='</div>';
    html+='<div style="margin-top:6px;font-size:11px;color:#a89878;">Alvos em <code>var/farm_watch.json</code> — o <code>run.bat</code> lê os saves de 2 em 2 segundos e mostra popup quando encontrar o item (<span style="color:#ff9d9d">🔔 até confirmares OK</span>).</div>';
  }
  if(h.length){
    h.slice(-3).forEach(function(hit){
      html+='<div class="fw-hit">🔔 <b>'+(hit.name||'?').replace(/</g,'&lt;')+'</b> @ '+(hit.conta||'?').replace(/</g,'&lt;')+' ×'+(hit.qtd||1)+' — vai buscar! <button onclick="location.href=\'tbh://farm?ack='+encodeURIComponent(hit.name||'')+'\'">\u2705 OK parar alarme</button></div>';
    });
  }
  bar.innerHTML=html;
  bar.classList.add('show');
}
// fecha IIFE do FARM EM CICLO já fechado acima — mantém escopo limpo
/* ---------- FARM OP tabs ---------- */
(function(){
  var tabs=document.querySelectorAll('.ftab');
  var pans=document.querySelectorAll('.ftabpan');
  if(!tabs.length) return;
  tabs.forEach(function(b){
    b.addEventListener('click', function(){
      var id=b.getAttribute('data-tab');
      tabs.forEach(function(x){x.classList.toggle('on', x===b);});
      pans.forEach(function(p){ p.classList.toggle('on', p.id==='ftab-'+id); });
    });
  });
})();

/* ---------- DROP: ver no mapa ---------- */
function _diffPtIdx(i){ return ['Normal','Pesadelo','Inferno','Tormento'][i]||'Normal'; }
function _diffClsIdx(i){ return ['normal','nightmare','hell','torment'][i]||'normal'; }
function _unpackStage(a){ if(!Array.isArray(a)) return a; return {act:a[0],no:a[1],level:a[2],diff:['NORMAL','NIGHTMARE','HELL','TORMENT'][a[3]]||'NORMAL',diff_idx:a[3],name_pt:a[4],waves:a[5],waveMonsters:a[6],monsterBoxRate:a[7],bossBoxRate:a[8],isPlague:!!a[9]}; }
function _diffPt(d){ return ({NORMAL:'Normal',NIGHTMARE:'Pesadelo',HELL:'Inferno',TORMENT:'Tormento'}[d]||d); }
function _escapeHtml(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
window.openDropMap=function(itemName){
  var raw = DROP_MAP[itemName] || DROP_MAP[itemName+' A'] || [];
  var stages = raw.map(_unpackStage);
  var modal=document.getElementById('dropMapModal');
  var titleEl=document.getElementById('dmTitle');
  var mapEl=document.getElementById('dmMap');
  var tblEl=document.getElementById('dmStagesBody');
  var hintEl=document.getElementById('dmHint');
  var linksEl=document.getElementById('dmLinks');
  if(!modal||!titleEl||!mapEl||!tblEl) return;
  titleEl.textContent='Onde dropa: '+itemName;
  // normaliza campos de dificuldade
  stages.forEach(function(s){ s.diff_pt=s.diff_pt||_diffPt(s.diff)||_diffPtIdx(s.diff_idx); s.diff_cls=s.diff_cls||({NORMAL:'normal',NIGHTMARE:'nightmare',HELL:'hell',TORMENT:'torment'}[s.diff]||_diffClsIdx(s.diff_idx)||'normal'); });
  // ===== MAPA ESTILO JOGO (Portal) =====
  var _actImg = {1:'assets/maps/Act1.png', 2:'assets/maps/Act2.png', 3:'assets/maps/Act3.png', 21:'assets/maps/Plague1.png', 22:'assets/maps/Plague2.png', 23:'assets/maps/Plague3.png'};
  var _plagueModo = {21:'Pesadelo', 22:'Inferno', 23:'Tormento'};
  // atos relevantes (só onde o item dropa)
  var _actsRelevantes = (function(){
    if(!stages.length) return [1];
    return [...new Set(stages.map(function(s){return s.act;}))].sort(function(a,b){return a-b;});
  })();
  // ---- TOPO: modo + lugar do item + passo-a-passo para burros ----
  var mods=[...new Set(stages.map(s=>s.diff_pt))].join(' / ');
  var lugares=[...new Set(stages.map(function(s){
    return s.isPlague
      ? ('Terras da Peste \u00b7 Andar '+s.no+' \u00b7 n\u00edvel '+s.level)
      : ('Ato '+s.act+' \u00b7 ['+s.act+'-'+s.no+'] \u00b7 n\u00edvel '+s.level);
  }))];
  var first=stages[0]||{};
  var steps='';
  if(stages.length){
    steps='<li>Abre o <b>PORTAL</b> no jogo.</li>'
      +'<li>Em cima, escolhe o modo <b>'+_escapeHtml((mods||'').toUpperCase())+'</b>.</li>';
    if(first.isPlague){
      steps+='<li>Clica no separador verde <b>TERRAS DA PESTE</b>.</li>'
        +'<li>Se o jogo pedir, ajusta a <b>Intensidade da peste</b> (a mais alta que aguentares).</li>'
        +'<li>Entra no <b>ANDAR '+first.no+'</b> (n\u00edvel '+first.level+') \u2014 a <span class="gm-painted"></span> bola pintada de verde no mapa.</li>';
    } else {
      steps+='<li>Clica no separador <b>ATO '+first.act+'</b>.</li>'
        +'<li>Entra no andar <b>['+first.act+'-'+first.no+']</b> (n\u00edvel '+first.level+') \u2014 a <span class="gm-painted"></span> bola pintada de verde no mapa.</li>';
    }
    if(stages.length>1) steps+='<li>Os outros andares com bola pintada tamb\u00e9m d\u00e3o o item: <b>'+_escapeHtml(lugares.slice(1).join(' \u00b7 '))+'</b>.</li>';
  } else {
    steps='<li>Sem dados de drop para este item.</li>';
  }
  if(hintEl){
    hintEl.innerHTML='<div class="gm-hint">'
      +'<h4>\ud83c\udfaf COMO FARMAR ESTE ITEM (passo a passo)</h4>'
      +'<div class="gm-chips">'
      +'<span class="gm-chip">\ud83d\udc79 MODO: '+_escapeHtml(mods||'-')+'</span>'
      +'<span class="gm-chip">\ud83d\udccd LUGAR DO ITEM: '+_escapeHtml(lugares[0]||'-')+'</span>'
      +'</div>'
      +'<ol class="gm-steps">'+steps+'</ol>'
      +'</div>';
  }
  // ---- MAPAS ESTILO JOGO: bolas alinhadas + etiquetas [X-Y] à direita ----
  function _gameMapaHtml(act){
    var isPlague = act>=21;
    var img = _actImg[act] || _actImg[1];
    var pkey = isPlague ? ((act-20)+'_plague') : String(act);
    var posList = MAP_POS[pkey] || (isPlague ? (MAP_POS['1_plague']||[]) : []);
    var maxNo = isPlague?20:10;
    var nodes='';
    for(var no=1; no<=maxNo; no++){
      var p=posList[no-1]; if(!p) continue;
      var hit=null;
      for(var i=0;i<stages.length;i++){ if(stages[i].act===act && stages[i].no===no){ hit=stages[i]; break; } }
      var cls='gm-node'+((no===10&&!isPlague)?' boss':'')+(hit?' drop':'');
      var lab= isPlague ? ('Andar '+no) : ('['+act+'-'+no+']');
      var tip= (isPlague ? ('Terras da Peste \u00b7 Andar '+no) : ('Ato '+act+' \u00b7 ['+act+'-'+no+']')) + (hit ? (' \u00b7 n\u00edvel '+hit.level+' \u00b7 '+hit.diff_pt) : '');
      nodes+='<div class="'+cls+'" style="left:'+(p[0]/300*100).toFixed(2)+'%;top:'+(p[1]/430*100).toFixed(2)+'%" title="'+_escapeHtml(tip)+'">'
        +'<i class="gm-ball"></i>'+(hit?'<i class="gm-flag"></i>':'')+'<span class="gm-lab">'+lab+'</span></div>';
    }
    var ribbon = isPlague ? 'Terras da Peste' : ('Ato '+act);
    // tema da dificuldade como no jogo: Normal=tan, Pesadelo=azul, Inferno=laranja, Tormento=roxo
    var dcls = (stages[0]&&stages[0].diff_cls) || 'normal';
    var theme = {nightmare:'blue', hell:'', torment:'purple', normal:'tan'}[dcls] || 'tan';
    var lvAct = null;
    for(var j=0;j<stages.length;j++){ if(stages[j].act===act){ lvAct=stages[j].level; break; } }
    var plaque = isPlague ? '<div class="gm-plaque">Terras da Peste do '+(_plagueModo[act]||'')+' \u00b7 n\u00edvel '+(lvAct||'?')+'</div>' : '';
    return '<div class="gm-frame'+(isPlague?' plague':' dif-'+dcls)+'">'
      +'<img src="'+img+'" alt="'+ribbon+'" loading="lazy">'
      +'<div class="gm-ribbon'+(isPlague?' green':' '+theme)+'">'+ribbon+'</div>'
      +plaque+nodes+'</div>';
  }
  mapEl.innerHTML='<div class="gm-maps">'+_actsRelevantes.map(_gameMapaHtml).join('')+'</div>'
    +'<div class="gm-legend">'
    +'<span><i class="gm-ball mini"></i> andar normal</span>'
    +'<span><i class="gm-ball mini boss"></i> boss [X-10]</span>'
    +'<span><i class="gm-ball mini drop"></i> ONDE FARMAR (bola pintada)</span>'
    +'</div>';
  if(linksEl){
    var q=encodeURIComponent(itemName);
    var linksHtml='';
    linksHtml+='<a href="https://www.taskbarherowiki.com/map" target="_blank">🗺️ mapa interativo (wiki)</a>';
    linksHtml+='<a href="https://tbh.city/map" target="_blank">🧭 atlas — 120 stages</a>';
    linksHtml+='<a href="https://probonk.com/tbh-task-bar-hero/stages" target="_blank">📦 stages & baús (drops)</a>';
    linksHtml+='<a href="https://steamcommunity.com/app/3678970/guides/?searchtext='+q+'" target="_blank">🖼️ guias Steam com prints</a>';
    linksEl.innerHTML=linksHtml;
  }
  // tabela detalhada
  tblEl.innerHTML='';
  stages.forEach(function(s){
    var tr=document.createElement('tr');
    var _dp = s.diff_pt||_diffPt(s.diff), _dc=s.diff_cls||({NORMAL:'normal',NIGHTMARE:'nightmare',HELL:'hell',TORMENT:'torment'}[s.diff]||'normal');
    var zona = s.isPlague ? ('Terras da Peste '+s.act+'.'+s.no+' '+_dp) : ('Ato '+s.act+'.'+s.no+' '+_dp);
    tr.innerHTML='<td>'+_escapeHtml(zona)+'</td>'
      +'<td>'+_escapeHtml(s.name_pt||'')+'</td>'
      +'<td>'+_escapeHtml(s.name_en||'-')+'</td>'
      +'<td>nv'+s.level+'</td>'
      +'<td><span class="bdif dif-'+_dc+'">'+_escapeHtml(_dp)+'</span></td>'
      +'<td>'+(s.waves||0)+' x '+ (s.waveMonsters||0)+'</td>'
      +'<td style="font-size:10px;color:#a89878;">M '+(_escapeHtml(s.monsterBox||"-"))+' ('+(s.monsterBoxRate||"-")+') · B '+_escapeHtml(s.bossBox||"-")+ ' ('+(s.bossBoxRate||"-") +')</td>';
    tblEl.appendChild(tr);
  });
  modal.classList.remove('hidden');
};
window.closeDropMap=function(){ var m=document.getElementById('dropMapModal'); if(m) m.classList.add('hidden'); };
(function(){
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeDropMap(); });
  document.addEventListener('click', function(e){
    var m=document.getElementById('dropMapModal');
    if(!m||m.classList.contains('hidden')) return;
    if(e.target.id==='dropMapModal' || e.target.classList.contains('dmmask')) closeDropMap();
  });
})();
"""


def main() -> None:
    urls = handle_cli()
    try:
        import tbh_baus
        baus_html = "<!--BAUS-START-->" + tbh_baus.render_section() + "<!--BAUS-END-->"
    except Exception as e:
        baus_html = ('<div class="bauhint">Seção MEUS BAÚS indisponível agora ('
                     + esc(str(e)[:100]) + ").</div>")
    ta.HERO_ICONS.update(ta.load_hero_icons())
    CHAR_ICONS.update(load_char_icons())
    load_game_icons()
    ta.ensure_data_files()
    data = ta.load_game_data()
    for aid, a in data["actives"].items():
        ta.DISPLAY_NAMES[aid] = PT_ATIVAS.get(aid, a["name"])
    for pid, p in data["passives"].items():
        ta.DISPLAY_NAMES[pid] = PT_STATS.get(p["statType"], p["label"])

    mp = tm.ensure_map()
    runes = tm.load_runes()
    costs = tm.load_costs()
    presets = ta.compute_route_presets(mp, runes, costs)

    rsvg, RW = ta.build_runes_svg((mp, runes, costs))

    cards = []
    sk_containers = []
    step_wraps = []
    uw_containers = []
    uw_wraps = []
    meta = {"titles": [], "urls": [], "cats": [], "heroes": [], "w": [], "rw": RW,
            "presets": presets, "ideals": [], "charIcons": CHAR_ICONS, "up": [], "runeSync": []}

    _users = _steam_users()
    _progs = _progresso_contas()
    _saves = {}
    try:
        _cfgb_p = os.path.join(ROOT, "config", "baus.json") if os.path.exists(os.path.join(ROOT, "config", "baus.json")) else (os.path.join(ROOT, "baus.json") if os.path.exists(os.path.join(ROOT, "baus.json")) else os.path.join(BASE, "baus.json"))
        _cfgb = json.load(open(_cfgb_p, encoding="utf-8-sig"))
        _saves = {c.get("nome"): c.get("save", "") for c in _cfgb.get("contas", [])}
    except Exception:
        pass
    try:
        import tbh_recomendar as _tr
    except Exception:
        _tr = None

    for i, url in enumerate(urls):
        try:
            build = carregar_build(url)
            if not build["sections"]:
                raise RuntimeError("pagina sem builds (soft 404?)")
        except Exception as e:
            print("AVISO: saltei " + url + " (" + str(e) + ") — remove com: python tbh_site.py --rm " + url)
            continue
        # estado real da conta vinculada a esta build (se houver |user=)
        base_url_pre = str(url)
        tag_user_pre = ""
        if "|user=" in base_url_pre:
            tag_user_pre = base_url_pre.split("|user=", 1)[1].split("|", 1)[0]
        save_state_pre = _save_state_para_render(tag_user_pre, _saves.get(tag_user_pre, "")) if tag_user_pre else {}
        _owned_r = []
        _buyable_r = []
        if save_state_pre and "runas" in save_state_pre:
            for _k, _v in save_state_pre["runas"].items():
                if str(_k) not in mp["nodes"]:
                    continue
                if _v > 0:
                    _owned_r.append(int(_k))
                elif _v == 0:
                    _buyable_r.append(int(_k))
        matched = [ta.match_section(sec, data) for sec in build["sections"]]
        svg, W = ta.render_build_svg(matched, data, save_state_pre if save_state_pre else None)
        svg = strip_routeline(svg)
        svg = inject_hero_pics(svg)

        # prioridades de stats DA BUILD (sec priority) — a rota de runas fica ideal POR BUILD
        _prio = []
        for _sec_p in build.get("sections", []):
            for _p in (_sec_p.get("priority") or []):
                _pt = str(_p).strip()
                if _pt and _pt.lower() not in [x.lower() for x in _prio]:
                    _prio.append(_pt)
        ideal = ta.compute_ideal_route(mp, runes, costs, build.get("category", ""), build.get("notes", ""), priority=_prio)

        rows, hero_blocks = build_step_rows(matched, data, save_state_pre if save_state_pre else None)
        has_unknown = any(s["kind"] == "desconhecida" for sec in matched for s in sec["steps"])
        warn = '<div class="warn">Algumas skills nao foram encontradas na arvore — ve os passos com ⚠</div>' if has_unknown else ""
        legend_html = ""
        if save_state_pre:
            legend_html = ('<div class="warn" style="background:#12261e;border-color:#4ec9a3;color:#7ee787">'
                'LEGENDA SINCRONIZADA COM O TEU SAVE: <span style="color:#7ee787">\u25A0 verde = feito</span> \u00b7'
                ' <span style="color:#ffb84d">\u25A0 laranja = parcial</span> \u00b7'
                ' <span style="color:#ffd86b">\u25A0 dourado = por fazer</span> \u00b7'
                ' <span style="color:#a89878">\U0001F512 cinza = bloqueado</span>'
                ' \u2014 n\u00edveis mostram <b>TU</b> (do save) \u2192 alvo da build perfeita.</div>')
        else:
            legend_html = ('<div class="warn" style="background:#1a160e;border-color:#7a6848;color:#a89878">'
                'Sem conta vinculada: a mostrar s\u00f3 os alvos da build. Vincula com <code>|user=Nome</code> no builds.json.</div>')
        notes_html = ""
        if build["notes"]:
            short = esc(build["notes"][:900]) + ("…" if len(build["notes"]) > 900 else "")
            notes_html = f'<details class="notesbox"><summary>Notas do autor da build</summary><p>{short.replace(chr(10), "<br>")}</p></details>'

        heroes = [re.sub(r"\s*\(level (\d+)\)", r" · nv \1", sec["hero"]).strip() for sec in build["sections"]]
        n_skills = sum(len(sec["steps"]) for sec in matched)

        meta["titles"].append(build["title"])
        meta["urls"].append(url)
        meta["cats"].append(build.get("category", ""))
        meta["heroes"].append(heroes)
        meta["w"].append(W)
        meta["ideals"].append(ideal)
        meta["runeSync"].append({"owned": _owned_r, "buyable": _buyable_r})

        figs = ""
        for k, h in enumerate(heroes):
            parts = h.split(" · ")
            nm = esc(parts[0].upper())
            lvl = f'<span class="hlvl">{esc(parts[1])}</span>' if len(parts) > 1 else ""
            figs += (
                f'<div class="herofig" style="animation-delay:{round(k * 0.45, 2)}s">'
                f'{icon_img(parts[0], 64, "cico")}'
                f'<span class="hname">{nm}</span>{lvl}</div>'
            )
        cat_chip = f'<span class="ccat">{esc(build["category"])}</span>' if build.get("category") else ""
        trash = ('<button class="trash" title="Apagar esta build" onclick="event.stopPropagation();delBuild('
                 + str(i) + ')"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6"/></svg></button>')
        # ‘|user=Nome da Conta’ no fim do URL liga a build a uma conta Steam;
        # a build em si carrega sempre do URL limpo
        base_url, tag_user = str(url), ""
        if "|user=" in base_url:
            tag_user = base_url.split("|user=", 1)[1].split("|", 1)[0]
            base_url = base_url.split("|user=", 1)[0]
        mm = MIX_RE.match(base_url)
        if mm:
            orig_links = (
                f'<a href="https://tbhindex.com/pt/builds/{mm.group(1)}" target="_blank" onclick="event.stopPropagation()">ver {mm.group(1)}</a>'
                f' · <a href="https://tbhindex.com/pt/builds/{mm.group(2)}" target="_blank" onclick="event.stopPropagation()">ver {mm.group(2)}</a>'
                f' · <b style="color:#7dff7d">MISTURA</b>'
            )
        else:
            orig_links = f'<a href="{esc(base_url)}" target="_blank" onclick="event.stopPropagation()">ver original</a>'
        # aba UPAR JÁ: plano da conta atribuída vs. alvos desta build
        status_chip = ""
        _uw = '<div class="upempty">Esta build não tem conta atribuída (|user=) — o plano de upgrades é por conta.</div>'
        if _tr and tag_user and _saves.get(tag_user):
            try:
                _plano = _tr.plano_completo(_saves[tag_user], _alvos_da_build(build, ideal))
                _uw = ('<div class="uphead">📌 DESTA BUILD: <b>' + esc(build['title']) + '</b>'
                       '<br><span style="font-weight:400">' + esc(tag_user) + ' · '
                       + esc(_plano.get("resumo", "")) + ' · equipa: ' + esc(' + '.join(heroes)) + '</span></div>'
                       + _tr.aba_up_html(_plano, tag_user))
                _n_pend = len(_plano.get("skills") or [])
                if _n_pend == 0:
                    status_chip = '<span class="bstatus feita">\u2713 BUILD FEITA</span>'
                else:
                    status_chip = '<span class="bstatus pend">\u26a1 ' + str(_n_pend) + ' por fazer</span>'
            except Exception as _e2:
                _uw = '<div class="upempty">Plano indisponível: ' + esc(str(_e2)[:80]) + '</div>'
        uw_containers.append(_uw)
        meta["up"].append(bool(_tr and tag_user and _saves.get(tag_user)))
        # alvos desta build em cache (para o monitor refrescar a aba UPAR JÁ sem refetch)
        try:
            _alvos_c = _tr._alvos_cache_load()
            _alvos_c[str(i)] = {"conta": tag_user, "alvos": _alvos_da_build(build, ideal)}
            _tr._alvos_cache_save(_alvos_c)
        except Exception:
            pass

        # badge do user Steam + progresso da conta ligada por '|user=Nome da Conta'
        user_tags = ""
        if tag_user:
            uname = _users.get(tag_user, tag_user)
            user_tags += (' <span class="buser" title="Conta atribu\u00edda a esta build">\U0001F464 '
                          + esc(uname) + "</span>")
            prog = _progs.get(tag_user)
            if prog:
                bits = []
                at = _dif_badge(prog.get("atual") or "", prog.get("atual_dif") or "")
                if at:
                    bits.append("\U0001F4CD " + at)
                mx = _dif_badge(prog.get("max") or "", prog.get("max_dif") or "")
                if mx:
                    bits.append("\U0001F3C6 " + mx)
                if prog.get("plague"):
                    bits.append('<span class="hchip">\U0001F9A0' + esc(prog["plague"].replace(" · ", " ").strip()) + "</span>")
                if bits:
                    user_tags += '<div class="bprog">' + " · ".join(bits) + "</div>"
                herois = [h for h in (prog.get("herois") or []) if h.get("lvl")]
                if herois:
                    user_tags += '<div class="bherois">' + "".join(
                        '<span class="hchip">' + esc(h["nome"]) + " <b>nv " + str(h["lvl"]) + "</b></span>"
                        for h in herois) + "</div>"
        cards.append(
            f'<div class="card bcard" data-url="{esc(base_url)}" onclick="showBuild({i})">'
            f'{trash}'
            f'<div class="cnum">{i + 1}</div>'
            f'<div class="cmain">'
            f'<div class="ctitle">{esc(build["title"])}</div>'
            f'<div class="cmeta">{cat_chip}{status_chip}{n_skills} skills · {len(heroes)} heroi{"s" if len(heroes) != 1 else ""} · {orig_links}</div>'
            f'{user_tags}'
            f'</div>'
            f'<div class="cheroes">{figs}</div>'
            f'</div>'
        )

        sk_containers.append(f'<div class="zoomer hidden" id="skz{i}">{svg}</div>')
        uw_wraps.append(f'<div class="sw hidden" id="uw{i}">{_uw}<!--uw-end--></div>')
        try:
            import tbh_farm as _farm_build_mod
            _farm_build_html = _farm_build_mod.render_farm_para_build(build, tag_user)
        except Exception as _e_fb:
            _farm_build_html = '<div class="farmBuild farmBuild-empty"><p class="muted">FARM POSS\u00cdVEL indispon\u00edvel (' + esc(str(_e_fb)[:60]) + ')</p></div>'
        step_wraps.append(
            f'<div class="sw hidden" id="sw{i}">{_farm_build_html}<h3>PASSO A PASSO</h3><ol>{"".join(rows)}</ol>{"".join(hero_blocks)}{warn}{legend_html}{notes_html}</div>'
        )

        print(f"build {i + 1}/{len(urls)} ok: {build['title']} ({n_skills} skills, rota ideal {len(ideal)} runas)")

    cards.append(
        '<div class="card addcard" onclick="openImport()" title="Importar build nova">'
        '<svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>'
        '<span class="addtxt">IMPORTAR BUILD</span></div>'
    )

    data_json = json.dumps(meta)
    # payload mapa drop: itemName -> [stages completos]
    try:
        import tbh_farm as _farm_drop_mod
        # todos itens que aparecem nas builds + top farm do dia (para cobrir farm OP)
        _need_names = set()
        for _b_url in urls:
            try:
                _b = carregar_build(_b_url)
                for _sec in (_b.get("sections") or []):
                    for _g in (_sec.get("gear") or []):
                        if ":" in _g:
                            _, _nm = _g.split(":", 1)
                            _need_names.add(_nm.strip())
            except Exception:
                pass
        # também TODO o FARM OP do dia (são só ~84 itens, map -> 19 ficaram só 10 stages cada = 30KB aceitável)
        try:
            _dnames, _dmap, _rank, _t = _farm_drop_mod._get_daily_cached()
            for _k in list(_dmap.keys()):
                _need_names.add(_k)
        except Exception:
            pass
        _drop_payload = _farm_drop_mod.drop_payload_for_names(_need_names)
        # slim: limita a 5 stages por item (array slim = 50% menos que 10)
        for _k in list(_drop_payload.keys()):
            if len(_drop_payload[_k]) > 5:
                _drop_payload[_k] = _drop_payload[_k][:5]
        drop_json = json.dumps(_drop_payload, ensure_ascii=False, separators=(',', ':'))
    except Exception as _e_dp:
        print("AVISO drop payload falhou: "+str(_e_dp))
        _drop_payload = {}
        drop_json = "{}"

    # --- FARM OP ---
    try:
        import tbh_farm as _farm
        farm_html = _farm.render_farm_op_section()
    except Exception as _e_farm:
        farm_html = '<section id="farmOp" class="farmOp"><div class="farmOpHead"><h2>FARM OP</h2><p class="muted">indisponivel agora ('+ _esc(str(_e_farm)[:80]) + ')</p></div></section>'
        print("AVISO farmOp falhou: " + str(_e_farm))

    doc = """<!DOCTYPE html>
<html lang="pt"><head><meta charset="utf-8">
<title>Taskbar Hero — As Minhas Builds</title>
<style>__CSS__</style><style>#visitasPanel{position:fixed;bottom:22px;right:22px;z-index:40;background:#1d1913;border:1px solid #a89878;border-radius:10px;padding:10px 12px;min-width:160px;font-size:12px;color:#a89878;box-shadow:0 4px 14px rgba(0,0,0,.45)}#visitasPanel .vp-head{display:flex;align-items:center;gap:6px;margin-bottom:6px;color:#ffd86b;font-weight:600}#visitasPanel .vp-dot{width:8px;height:8px;border-radius:50%;background:#7ee787;box-shadow:0 0 6px #7ee787}#visitasPanel .vp-row{display:flex;justify-content:space-between;gap:14px;padding:2px 0}#visitasPanel .vp-row b{color:#f0e6cc}#visitasPanel a{margin-left:auto;color:#7ee787;text-decoration:none;border:1px solid #7ee787;border-radius:6px;padding:1px 6px;font-size:11px;line-height:1.4}#visitasPanel a:hover{background:#7ee787;color:#0d2a0d}</style></head>
<body>

<div id="home">
  <div class="homewrap">
    <h1>AS MINHAS BUILDS</h1>
    <div class="sub">Clica numa build para ver a arvore de skills (ordem na coluna direita) e o mapa de runas com o caminho perfeito desta build.</div>
    <div id="farmbar"><span id="farmdot" class="dot"></span><b style="font-size:12px;color:#ffd86b;">FARM EM CICLO</b><small id="farmtxt">a atualizar sozinho a cada 15 min — deixa o farm a correr</small><span id="farmwarn" class="farmwarn">⚠ FARM PARADO — reabre atualizar_baus_agora.bat</span><span style="flex:1"></span><button id="farmtoggle" type="button">⏸ pausar</button></div>
    <div id="farmWatchBar"></div>
    <div id="farmRunHint" style="font-size:11px;color:#a89878;margin:6px 0 8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;"><span>Queres ser avisado quando dropar?</span> <span style="background:#1d1913;border:1px solid #5a4e38;border-radius:6px;padding:2px 8px;">1) Clica <b style="color:#ffd86b">🎯 Farmar</b> no item → <small style="color:#a89878">regista o item no alerta do run.bat</small></span> <span style="background:#1d1913;border:1px solid #5a4e38;border-radius:6px;padding:2px 8px;">2) Mantém o <b style="color:#ffd86b">run.bat aberto</b> · verifica os saves a cada <b style="color:#7ee787">2s</b> e mostra popup quando encontrar o item.</span></div>
    __BAUS__
    __FARMOP__
    <div class="cards">__CARDS__</div>
  </div>
</div>

<div id="buildview" class="hidden">
  <header>
    <button id="backBtn">← TODAS AS BUILDS</button>
    <h1 id="bvTitle"></h1>
    <div id="bvHeroes" class="bvheroes"></div>
    <div class="url"><span id="bvUrl"></span> — SKILLS: ordem completa na coluna direita · dourado = comprar · RUNAS: caminho perfeito auto-aplicado, clica para ajustar</div>
    <div id="tabs"><button id="tabS" class="on">SKILLS DO HEROI</button><button id="tabR">MAPA DE RUNAS</button><button id="tabU" class="hidden">⚡ UPAR JÁ</button></div>
  </header>
  <div class="treewrap" id="viewSkills">__SKSVGS__</div>
  <div class="treewrap hidden" id="viewRunes"><div class="zoomer" id="runesZoomer">__RUNESVG__</div>
    <div id="rpanel">
      <h3>A ROTA DE RUNAS DESTA BUILD</h3>
      <div id="idealinfo">Caminho PERFEITO desta build auto-aplicado<span id="idealcat"></span><span id="runeSyncInfo"></span> · ajusta clicando nas runas</div>
      <div id="presets"><span>Rotas:</span><button data-g="ideal" class="hot">PERFEITA DESTA BUILD</button><button data-g="farm">FARM / END GAME</button><button data-g="ouro">OURO</button><button data-g="exp">EXP</button><button data-g="combate">COMBATE</button></div>
      <div id="partinfo"></div>
      <div id="partbar"></div>
      <ol id="plist"></ol>
      <div id="ptotal"></div>
      <button id="pclear">Limpar rota</button>
      <p id="phint">O caminho perfeito equilibra progressao (waves, combate, exp, ouro) consoante as notas da build. Dividido em PARTES de 15 runas · sobre cada runa da parte: <b>×N</b> = niveis a comprar. Fica guardado no browser por build.</p>
    </div>
  </div>
  <aside class="steps" id="stepsS">__STEPLISTS__</aside>
  <aside class="steps hidden" id="stepsU">__UPWRAPS__</aside>
  <div id="farmBottom" class="hidden"></div>
  <aside class="steps hidden" id="stepsR">
    <h3>MAPA DE RUNAS</h3>
    <ol>
      <li>Este e o mapa completo das 241 runas globais (o mesmo do jogo, partilhado por todos os herois).</li>
      <li>O caminho perfeito desta build ja vem aplicado — a linha dourada numerada.</li>
      <li>CLICA nas runas para ajustar a ordem; hover mostra nome, max e custo total em ouro.</li>
      <li>Scroll = zoom · arrastar = mover · a rota fica guardada mesmo se fechares.</li>
    </ol>
  </aside>
  <div id="zbtns"><button id="zin">+</button><button id="zout">−</button><button id="zfit">⤢ ajustar</button></div>
</div>

<div id="modal" class="hidden">
  <div class="mbox">
    <h3>IMPORTAR BUILD NOVA</h3>
    <p class="mhint">Cola o link da build do tbhindex.com e o Python corre SOZINHO: confirma ABRIR se o browser perguntar. (Se nunca abriu nada, corre uma vez no terminal: <b>python tbh_site.py --install-protocol</b>.) O comando manual fica em baixo, para o caso de precisares.</p>
    <input id="murl" type="url" placeholder="https://tbhindex.com/pt/builds/NNN" spellcheck="false">
    <div class="mbtns">
      <button id="mgo" class="primary">GERAR COMANDO</button>
      <button id="mclose">Fechar</button>
    </div>
    <div id="mcmd" class="cmdbox hidden" title="Clica para copiar"></div>
    <div id="mstatus"></div>
  </div>
</div>

<div id="visitasPanel">
  <div class="vp-head"><span class="vp-dot"></span>Visitas<a id="tbhGithub" href="https://github.com/SEU-USER/tbh" target="_blank" rel="noopener" title="Repositorio no GitHub">GitHub</a></div>
  <div class="vp-row"><span>Visitas</span><b id="vpTotal">-</b></div>
  <div class="vp-row"><span>Online agora</span><b id="vpOnline">-</b></div>
  <div class="vp-row"><span>IPs</span><b id="vpIps">-</b></div>
</div>
<div id="toast" class="hidden"></div>
<div id="dropMapModal" class="hidden"><div class="dmmask"></div><div class="dmbox"><div class="dmhead"><h3 id="dmTitle">Onde dropa</h3><button class="dmclose" type="button" onclick="closeDropMap()">✕ fechar</button></div><p class="dmsub">Mapa igual ao do jogo. A <b style="background:#35c93a;color:#0d2a0d;border-radius:4px;padding:0 4px;">bola pintada de verde</b> \u00e9 o andar onde este item dropa. Segue o passo a passo acima e entra no andar indicado. Passa o rato nas bolas para ver n\u00edvel e ondas.</p><div id="dmHint"></div><div id="dmMap"></div><div id="dmLinks" class="dm-toplinks"></div><div class="dstages"><table><thead><tr><th>Zona</th><th>Andar (PT)</th><th>Andar (EN)</th><th>nv</th><th>Dificuldade</th><th>Ondas</th><th>Ba\u00fas / taxa</th></tr></thead><tbody id="dmStagesBody"></tbody></table></div><p class="dmtip">Fonte: <code>data/tbhdata/tbhStages.js</code> (189 stages reais do jogo) + <code>assets/maps/Act*_Bg.png</code> (extra\u00eddo do jogo via UnityPy, id\u00eantico \u00e0 wiki). Caixas: <code>910xxx</code> Monstro \u00b7 <code>920xxx</code> Boss \u00b7 Peste <code>915xxx/925xxx</code>. Taxa baixa = mais ba\u00fas/hora. Tip: na Peste foca andar 15-20. Posi\u00e7\u00f5es do ponto dourado em <code>assets/maps/positions.json</code> (ajust\u00e1vel).</p></div></div>

<script>
__JS__
</script>
<script>
(function(){
  var VB_URL = (location.protocol === 'http:' || location.protocol === 'https:') ? location.origin + '/api/visitas' : 'http://localhost:8765/api/visitas';
  function vbDid(){
    try{
      var d = localStorage.getItem('tbh_did');
      if(d) return d;
      d = 'dev-' + Date.now().toString(36) + '-' + Math.random().toString(36).substring(2, 10);
      localStorage.setItem('tbh_did', d);
      return d;
    }catch(e){ return 'dev-anon'; }
  }
  function vbRender(s){
    var el;
    if(s){
      if((el = document.getElementById('vpTotal'))) el.textContent = s.total_visitas;
      if((el = document.getElementById('vpOnline'))) el.textContent = s.online_agora;
      if((el = document.getElementById('vpIps'))) el.textContent = s.ips_online;
    }
  }
  function vbSend(ev){
    try{
      fetch(VB_URL, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({device:vbDid(), event:ev})})
        .then(function(r){ return r.json(); })
        .then(function(j){ if(j && j.stats) vbRender(j.stats); })
        .catch(function(){});
    }catch(e){}
  }
  function vbRefresh(){
    try{
      fetch(VB_URL).then(function(r){ return r.json(); }).then(function(s){ vbRender(s); }).catch(function(){});
    }catch(e){}
  }
  var vbLink = document.getElementById('tbhGithub');
  if(vbLink){
    vbLink.addEventListener('click', function(e){
      e.preventDefault();
      vbSend('github_click');
      window.open(vbLink.href, '_blank');
    });
  }
  vbSend('visit');
  setInterval(function(){ vbSend('ping'); }, 45000);
  setInterval(vbRefresh, 30000);
})();
</script>
</body></html>"""

    try:
        _mp = os.path.join(ROOT,"assets","maps","positions.json")
        if not os.path.exists(_mp): _mp = os.path.join(ROOT,"assets","maps_from_game","positions.json")
        if not os.path.exists(_mp):
            for _alt in [os.path.join(ROOT,"positions.json"), os.path.join(BASE,"positions.json")]:
                if os.path.exists(_alt): _mp=_alt; break
        map_pos_json = open(_mp,encoding="utf-8").read() if os.path.exists(_mp) else "{}"
        # valida JSON
        json.loads(map_pos_json)
    except Exception: map_pos_json="{}"
    # farm watch payload (targets + hits pendentes) — para a barra no topo
    try:
        _wf_path = os.path.join(ROOT, "var", "farm_watch.json")
        if not os.path.exists(_wf_path):
            for _alt in [os.path.join(ROOT, "farm_watch.json"), os.path.join(BASE, "farm_watch.json")]:
                if os.path.exists(_alt): _wf_path=_alt; break
        if os.path.exists(_wf_path):
            _wf = json.load(open(_wf_path, encoding="utf-8-sig"))
            # só manda targets + hits não confirmados (para barra)
            _wf_mini = {"targets": _wf.get("targets",[]), "hits": [h for h in _wf.get("hits",[]) if not h.get("acknowledged")]}
            farm_watch_json = json.dumps(_wf_mini, ensure_ascii=False, separators=(',', ':'))
        else:
            farm_watch_json = "{\\\"targets\\\":[],\\\"hits\\\":[]}"
    except Exception as _e_fw:
        farm_watch_json = "{\\\"targets\\\":[],\\\"hits\\\":[]}"
    _js2 = JS.replace("__DATA__", data_json).replace("__DROP_MAP__", drop_json).replace("__MAP_POS__", map_pos_json).replace("__FARM_WATCH_JSON__", farm_watch_json)
    doc = (doc
           .replace("__CSS__", CSS)
           .replace("__FARMOP__", farm_html)
           .replace("__BAUS__", baus_html)
           .replace("__CARDS__", "\n".join(cards))
           .replace("__SKSVGS__", "\n".join(sk_containers))
           .replace("__RUNESVG__", rsvg)
           .replace("__STEPLISTS__", "\n".join(step_wraps))
           .replace("__UPWRAPS__", "\n".join(uw_wraps))
           .replace("__JS__", _js2))

    # nas linhas de recomendação da secção MEUS BAÚS, injectar a build a abrir
    try:
        import tbh_recomendar
        doc = tbh_recomendar.ligar_builds(doc, urls)
        print("linhas de recomendação ligadas a builds: " + str(doc.count('data-build="')))
    except Exception as _e:
        print("AVISO ligacao rec->build falhou: " + str(_e))



    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print("OK: " + OUT + " (" + str(round(os.path.getsize(OUT) / 1024)) + " KB)")
    # em ciclo (--sem-abrir/--silencioso) NÃO abre janela — quem manda é o .bat
    if "--sem-abrir" not in sys.argv and "--silencioso" not in sys.argv:
        try:
            os.startfile(OUT)
        except Exception:
            pass


if __name__ == "__main__":
    main()
