r"""
FARM OP — dashboard que responde "o que vale a pena farmar AGORA?"

Usa tbhdata/precos_cache.json (sell / vol / med / hist ao vivo do Mercado Steam)
e tbhdata/tbhStages.js (para mapear zonas) + baus_cache.json (progresso das 5 contas).

Gera HTML puro (sem dependência de API) com:
  - TOP HÍBRIDO (valor × liquidez)  — o melhor equilíbrio para farmar
  - BALEIAS (preço puro)            — chase items lendários
  - LÍQUIDOS (sell ≥1 € com volume) — o que vende HOJE
  - MOEDINHAS (alto volume barato)  — farm de quantidade
  - GUIAS passo-a-passo: GOLD / EXP / ITENS / PROGRESSÃO
  - NOVA COLUNA "Dropa em" por item: zona x-x + dificuldade (Normal/Pesadelo/Inferno/Tormento) + Plague
    Mapeia ItemKey/grade/nível (via tbhdata gear) -> caixas 91xxx/92xxx -> stages act/no/diff
"""
import os
import json
import math
import re
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
def _cfg_path(*parts):
    p = os.path.join(ROOT, *parts)
    if os.path.exists(p): return p
    # fallbacks legacy
    for alt in [os.path.join(ROOT, parts[-1]), os.path.join(BASE, *parts), os.path.join(BASE, parts[-1])]:
        if os.path.exists(alt): return alt
    return p
def _dir_first(*cands):
    for c in cands:
        if os.path.isdir(c): return c
    return cands[0]
PRECO_CACHE = _cfg_path("data", "tbhdata", "precos_cache.json")
# fallback tbhdata legado
if not os.path.exists(PRECO_CACHE):
    for alt in [os.path.join(ROOT, "tbhdata", "precos_cache.json"), os.path.join(BASE, "tbhdata", "precos_cache.json")]:
        if os.path.exists(alt): PRECO_CACHE = alt; break
STAGES_JS = _cfg_path("data", "tbhdata", "tbhStages.js")
if not os.path.exists(STAGES_JS):
    for alt in [os.path.join(ROOT, "tbhdata", "tbhStages.js"), os.path.join(BASE, "tbhdata", "tbhStages.js")]:
        if os.path.exists(alt): STAGES_JS = alt; break
CACHE_BAUS = _cfg_path("baus_cache.json")
if not os.path.exists(CACHE_BAUS):
    for alt in [os.path.join(ROOT, "var", "baus_cache.json"), os.path.join(BASE, "baus_cache.json")]:
        if os.path.exists(alt): CACHE_BAUS = alt; break

MARKET_URL = "https://steamcommunity.com/market/listings/3678970/"
WATCH_FILE = _cfg_path("var", "farm_watch.json")
# compat var/farm_watch fallback
if not os.path.exists(WATCH_FILE):
    for _alt in [os.path.join(ROOT, "var", "farm_watch.json"), os.path.join(ROOT, "farm_watch.json"), os.path.join(BASE, "farm_watch.json")]:
        if os.path.exists(_alt): WATCH_FILE = _alt; break
_FARM_TARG_CACHE = None
def _farm_targets_set():
    global _FARM_TARG_CACHE
    if _FARM_TARG_CACHE is not None:
        return _FARM_TARG_CACHE
    try:
        if os.path.exists(WATCH_FILE):
            d = json.load(open(WATCH_FILE, encoding="utf-8-sig"))
            s = {t.get("name") for t in d.get("targets",[]) if t.get("name")}
            _FARM_TARG_CACHE = s
            return s
    except: pass
    _FARM_TARG_CACHE = set()
    return _FARM_TARG_CACHE
def _farm_targets_map():
    """{nome: conta_ou_None} para saber se já está a farmar."""
    try:
        if os.path.exists(WATCH_FILE):
            d = json.load(open(WATCH_FILE, encoding="utf-8-sig"))
            return {t.get("name"): t.get("conta") for t in d.get("targets",[]) if t.get("name")}
    except: pass
    return {}
def _farm_btn_html(name: str, conta: str = None) -> str:
    esc_name = _esc(name)
    is_on = name in _farm_targets_set()
    # data-conta permite ao JS mandar a conta certa (auto-deteção: se vier da build |user=Conta)
    conta_attr = f' data-conta="{_esc(conta)}"' if conta else ''
    if is_on:
        return f'<button type="button" class="ffarmbtn on" data-farm="{esc_name}"{conta_attr} onclick="farmToggle(this)" title="Alerta registado; o run.bat tem de estar aberto para vigiar os saves. Clica para parar.">🔔 Alerta registado</button>'
    else:
        return f'<button type="button" class="ffarmbtn" data-farm="{esc_name}"{conta_attr} onclick="farmToggle(this)" title="Farmar — vigia saves a cada 2s e toca alarme (auto-deteta a conta)">🎯 Farmar</button>'


# ── helpers ──────────────────────────────────────────────────────────

def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def _fmt_eur(v) -> str:
    try:
        return f"€{v:.2f}".replace(".", ",")
    except Exception:
        return str(v)

def _vol_badge(vol: int) -> str:
    if vol >= 500: return '<span class="vol vol-hot">🔥 ' + str(vol) + '</span>'
    if vol >= 50:  return '<span class="vol vol-ok">✓ ' + str(vol) + '</span>'
    if vol >= 5:   return '<span class="vol vol-mid">' + str(vol) + '</span>'
    if vol >= 1:   return '<span class="vol vol-low">' + str(vol) + '</span>'
    return '<span class="vol vol-none">—</span>'

def _dias_txt(vol) -> str:
    if not vol or vol <= 0:
        return '<span class="vdias vdias-none">sem dados</span>'
    d = 1 / vol
    if d < 1:
        return '<span class="vdias vdias-fast">~&lt;1 dia</span>'
    if d <= 3:
        return '<span class="vdias vdias-fast">~1–3 dias</span>'
    if d <= 14:
        return '<span class="vdias vdias-mid">~' + str(int(round(d))) + ' dias</span>'
    return '<span class="vdias vdias-slow">~' + str(int(round(d))) + ' dias · lento</span>'

def _load_precos():
    try:
        j = json.load(open(PRECO_CACHE, encoding="utf-8"))
        itens = j.get("itens") or j
        t = j.get("t", 0)
        return itens, t
    except Exception:
        return {}, 0

def _grade_of(name: str) -> str:
    m = re.search(r"\(([^)]+)\)\s*[A-C]$", name)
    return m.group(1) if m else ""

def _tier_emoji(grade: str) -> str:
    mp = {
        "Cosmic": "🌌", "Divine": "✨", "Celestial": "☄️",
        "Beyond": "🔮", "Arcana": "🪄", "Immortal": "💎",
        "Legendary": "🥇", "Rare": "🥈", "Uncommon": "—", "Common": "—",
    }
    return mp.get(grade, "·")

def _market_link(name: str) -> str:
    import urllib.parse
    return MARKET_URL + urllib.parse.quote(name)

# ── drop zone helpers ──────────────────────────────────────────────
# Cache para stages/boxes e gear reverse
_STAGES_CACHE = None
_BOX_MAP = None
_BOX_RANGES = None
_GEAR_DATA = None
_REV_MAP = None

DIFF_PT = {"NORMAL": "Normal", "NIGHTMARE": "Pesadelo", "HELL": "Inferno", "TORMENT": "Tormento"}
DIFF_CLASS = {"NORMAL": "normal", "NIGHTMARE": "nightmare", "HELL": "hell", "TORMENT": "torment"}

def _diff_por_nivel(lv) -> str:
    try:
        lv = int(lv)
    except Exception:
        return None
    if 1 <= lv <= 32:
        return "NORMAL"
    if 33 <= lv <= 52:
        return "NIGHTMARE"
    if 53 <= lv <= 77:
        return "HELL"
    if lv >= 78:
        return "TORMENT"
    return None

def drop_stages_for_name(name: str):
    """Lista compacta de stages onde este item dropa — formato array slim para poupar KB."""
    info = _info_for_market_name(name)
    if not info:
        return []
    lvl = info.get("l")
    if lvl is None or info.get("tp") == "MATERIAL":
        return []
    try:
        lvl = int(lvl)
    except Exception:
        return []
    stages, box_map, box_ranges = _load_stages_cached()
    if not box_ranges:
        return []
    esperado = _diff_por_nivel(lvl)
    matching_boxes = [b for b, (mn, mx) in box_ranges.items() if mn <= lvl <= mx]
    if not matching_boxes:
        return []
    all_stages = []
    for b in matching_boxes:
        all_stages.extend(box_map.get(b, []) or [])
    if esperado:
        filt = [s for s in all_stages if s.get("diff") == esperado]
        if filt:
            all_stages = filt
    uniq = {}
    for s in all_stages:
        uniq[s.get("key")] = s
    order = {"NORMAL": 0, "NIGHTMARE": 1, "HELL": 2, "TORMENT": 3}
    lst = sorted(uniq.values(), key=lambda s: (order.get(s.get("diff"), 9), s.get("act", 0), s.get("no", 0)))
    out = []
    for s in lst:
        nm = s.get("name") or {}
        pt = nm.get("pt") if isinstance(nm, dict) else str(nm)
        # slim: [act,no,level,diff_idx,name_pt,waves,waveMonsters,monsterRate,bossRate,isPlague]
        diff_idx = {"NORMAL": 0, "NIGHTMARE": 1, "HELL": 2, "TORMENT": 3}.get(s.get("diff"), 0)
        out.append([s.get("act"), s.get("no"), s.get("level"), diff_idx, pt, s.get("waves") or 0, s.get("waveMonsters") or 0, s.get("monsterBoxRate") or 0, s.get("bossBoxRate") or 0, 1 if int(s.get("act", 0)) >= 21 else 0])
    return out

def drop_payload_for_names(names):
    out = {}
    for n in names:
        try:
            lst = drop_stages_for_name(n)
            if lst:
                out[n] = lst
        except Exception:
            pass
    return out

def _load_stages_cached():
    global _STAGES_CACHE, _BOX_MAP, _BOX_RANGES
    if _STAGES_CACHE is not None:
        return _STAGES_CACHE, _BOX_MAP, _BOX_RANGES
    try:
        txt = open(STAGES_JS, encoding="utf-8", errors="replace").read()
        m = re.search(r"JSON\.parse\(`(\{.*?\})`\)", txt, re.S)
        data = json.loads(m.group(1)) if m else {"stages": []}
        stages = data.get("stages", [])
    except Exception:
        stages = []
    # box -> list stages
    from collections import defaultdict
    box_map = defaultdict(list)
    for s in stages:
        for bkey in ("monsterBox", "bossBox"):
            b = s.get(bkey)
            if b:
                box_map[b].append(s)
        # also consider plague bossBox 925xxx/935xxx already covered
    # ranges per box: min/max level among its stages
    box_ranges = {}
    for b, lst in box_map.items():
        try:
            mn = min(x.get("level", 999) for x in lst)
            mx = max(x.get("level", 0) for x in lst)
            box_ranges[b] = (mn, mx)
        except Exception:
            pass
    _STAGES_CACHE = stages
    _BOX_MAP = box_map
    _BOX_RANGES = box_ranges
    return stages, box_map, box_ranges

def _load_gear_cached():
    global _GEAR_DATA, _REV_MAP
    if _REV_MAP is not None:
        return _GEAR_DATA, _REV_MAP
    try:
        from tbh_inventario import carregar_dados_jogo, nome_de_mercado
        dados = carregar_dados_jogo()
        rev = {}
        for k, info in dados["gear"].items():
            try:
                nm = nome_de_mercado(int(k), dados, None)
                if nm and nm not in rev:
                    rev[nm] = (k, info)
            except Exception:
                pass
        _GEAR_DATA = dados
        _REV_MAP = rev
        return dados, rev
    except Exception:
        _GEAR_DATA = {}
        _REV_MAP = {}
        return {}, {}

def _info_for_market_name(name: str):
    """(g, l, t) info do gear para o nome de mercado; suporta variante C via fallback A/B."""
    try:
        _, rev = _load_gear_cached()
        if not rev:
            return None
        if name in rev:
            return rev[name][1]
        if name.endswith(" C"):
            base = name[:-2]
            cand = base + " A"
            if cand in rev:
                return rev[cand][1]
            cand = base + " B"
            if cand in rev:
                return rev[cand][1]
        # material exato já tratado; se não achou e nome tem (Grade) mas variante C inexistia, tenta A/B genérico
        # fallback já fez
        return None
    except Exception:
        return None

def _drop_map_btn(name: str) -> str:
    info = _info_for_market_name(name)
    if not info or info.get("l") is None or info.get("tp") == "MATERIAL" or "Synthesis Stone" in name:
        return ""
    return f' <button type="button" class="fmapbtn" data-drop="{_esc(name)}" title="Ver no mapa — onde dropa este item" onclick="openDropMap(this.dataset.drop)">🗺️ ver no mapa</button>'

def _drop_html_for_name(name: str) -> str:
    """Gera HTML compacto para coluna 'Dropa em' + botão ver no mapa.
    Formato pedido: Normal / Pesadelo / Inferno / Tormento + Terras da Peste andar 1..20.
    """
    # síntese / craft ?
    if "Synthesis Stone" in name:
        return '<span class="fdrop muted" title="Item de síntese — crafta na forja, não dropa de baú">Síntese</span>'
    info = _info_for_market_name(name)
    grade = _grade_of(name)
    # sem info (não está no gear) — genérico
    if not info:
        if grade:
            hint_map = {
                "Common": "Normal · Ato 1",
                "Uncommon": "Normal · Ato 1",
                "Rare": "Pesadelo · Ato 1-2",
                "Legendary": "Pesadelo · Ato 1-3",
                "Immortal": "Pesadelo/Inferno · Ato 2-3",
                "Arcana": "Inferno · Ato 2-3",
                "Beyond": "Inferno · Ato 2-3",
                "Celestial": "Tormento · Ato 1-2",
                "Divine": "Tormento · Ato 2-3",
                "Cosmic": "Tormento · Ato 2-3 + Terras da Peste Tormento",
            }
            h = hint_map.get(grade, "")
            if h:
                diff_cls = {"Common":"normal","Uncommon":"normal","Rare":"nightmare","Legendary":"nightmare","Immortal":"nightmare","Arcana":"hell","Beyond":"hell","Celestial":"torment","Divine":"torment","Cosmic":"torment"}.get(grade,"normal")
                return f'<span class="fdrop"><span class="bdif dif-{diff_cls}" title="Estimado por grade {grade}">{_esc(h)}</span></span>'
        if not re.search(r"\(", name):
            return '<span class="fdrop muted" title="Material — dropa de monstros em qualquer ato/baú">Material</span>'
        return '<span class="fdrop muted">—</span>'
    g = info.get("g")
    lvl = info.get("l")
    tp = info.get("tp")
    if tp == "MATERIAL" or lvl is None:
        grade_hint = ""
        if g:
            pt_grade = {"COM":"Common","UNC":"Uncommon","RAR":"Rare","LEG":"Legendary","IMM":"Immortal","ARC":"Arcana","BEY":"Beyond","CEL":"Celestial","DIV":"Divine","COS":"Cosmic"}.get(g, g)
            diff_hint = {"COM":"normal","UNC":"normal","RAR":"nightmare","LEG":"nightmare","IMM":"nightmare","ARC":"hell","BEY":"hell","CEL":"torment","DIV":"torment","COS":"torment"}.get(g, "normal")
            grade_hint = f'<span class="bdif dif-{diff_hint}" title="Material {pt_grade}">{_esc(pt_grade)}</span> '
        return f'<span class="fdrop muted">{grade_hint}Material</span>'
    try:
        _, box_map, box_ranges = _load_stages_cached()
        if not box_ranges:
            return '<span class="fdrop muted">—</span>'
        lvl = int(lvl)
        # Esperado pelo nível: 1-32 Normal, 33-52 Pesadelo, 53-77 Inferno, 78-95 Tormento (100 -> Tormento)
        def _diff_por_nivel(lv: int):
            if 1 <= lv <= 32:
                return "NORMAL"
            if 33 <= lv <= 52:
                return "NIGHTMARE"
            if 53 <= lv <= 77:
                return "HELL"
            if 78 <= lv <= 95 or lv >= 90:
                return "TORMENT"
            if lv >= 100:
                return "TORMENT"
            return None
        esperado = _diff_por_nivel(lvl)
        matching_boxes = [b for b, (mn, mx) in box_ranges.items() if mn <= lvl <= mx]
        if not matching_boxes:
            # fallback: nível mais próximo
            try:
                stages_tmp, _, _ = _load_stages_cached()
                levels = sorted(set(s.get("level") for s in stages_tmp if s.get("level") is not None))
                prox = min(levels, key=lambda x: abs(x - lvl))
                return f'<span class="fdrop"><span class="bdif dif-normal">Ato ? · nv{lvl} (prox nv{prox})</span></span>'
            except Exception:
                return f'<span class="fdrop"><span class="bdif dif-normal">Ato ? · nv{lvl}</span></span>'
        all_stages = []
        for b in matching_boxes:
            all_stages.extend(box_map.get(b, []))
        if not all_stages:
            return '<span class="fdrop muted">—</span>'
        # Filtra só pela dificuldade esperada para o nível (evita contaminação cruzada: ex. 910651 usado em Inferno e Tormento)
        if esperado:
            filtrados = [s for s in all_stages if s.get("diff") == esperado]
            # se filtragem esvaziar (caso raro de box partilhada sem diff esperada), volta a todos
            if filtrados:
                all_stages = filtrados
        if not all_stages:
            return '<span class="fdrop muted">—</span>'
        from collections import defaultdict
        # como já filtrámos por diff, só há um diff presente; mantemos loop para facilitar plague/normal
        diffs_present = sorted(set(s.get("diff") for s in all_stages if s.get("diff")))
        order = ["NORMAL","NIGHTMARE","HELL","TORMENT"]
        diffs_present = sorted(diffs_present, key=lambda d: order.index(d) if d in order else 9)
        parts = []
        tooltips = []
        for diff in diffs_present:
            lst = [s for s in all_stages if s.get("diff")==diff]
            normal = [s for s in lst if s.get("act",0) <= 10]
            plague = [s for s in lst if s.get("act",0) >= 21]
            pt = DIFF_PT.get(diff, diff)
            cls = DIFF_CLASS.get(diff, "normal")
            if normal:
                from collections import defaultdict as _dd
                by_act = _dd(list)
                for _s in normal:
                    by_act[_s.get("act")].append(_s)
                # ato(s) + andar(es) exatos onde esta caixa aparece
                act_details = []  # lista (ato, nos_sorted, lvls_sorted)
                for _act in sorted(by_act):
                    _ss = by_act[_act]
                    _nos = sorted(set(x.get("no") for x in _ss if x.get("no") is not None))
                    _lvls_act = sorted(set(x.get("level") for x in _ss if x.get("level") is not None))
                    act_details.append((_act, _nos, _lvls_act))
                # badge: se só 1 ato, mostra andar exato (ex: Ato 3 andar 5-9); se vários atos, resume Ato X-Y
                acts = sorted(by_act.keys())
                if len(acts) == 1:
                    _act, _nos, _ = act_details[0]
                    if _nos == list(range(1, 11)):
                        act_str = f"Ato {_act}"
                    elif len(_nos) == 1:
                        act_str = f"Ato {_act} andar {_nos[0]}"
                    elif _nos == list(range(min(_nos), max(_nos) + 1)):
                        act_str = f"Ato {_act} andar {min(_nos)}-{max(_nos)}"
                    else:
                        act_str = f"Ato {_act} andar {','.join(map(str, _nos))}"
                else:
                    # vários atos: verifica se todos são 1-10 completos e consecutivos -> "Ato 1-3"
                    all_full = all(_nos == list(range(1, 11)) for _, _nos, _ in act_details)
                    if all_full and acts == list(range(min(acts), max(acts) + 1)):
                        act_str = f"Ato {min(acts)}-{max(acts)}"
                    else:
                        # resumo curto sem andar; andar vai no tooltip
                        act_str = f"Ato {min(acts)}-{max(acts)}"
                lvls = [s.get("level") for s in normal if s.get("level") is not None]
                lv_str = f" nv{min(lvls)}-{max(lvls)}" if lvls else ""
                # tooltip detalhado com andar por ato (sempre completo)
                detail_parts = []
                for _act, _nos, _lv_act in act_details:
                    if _nos == list(range(1, 11)):
                        detail_parts.append(f"Ato {_act} 1-10 nv{min(_lv_act)}-{max(_lv_act)}" if len(_lv_act) > 1 else f"Ato {_act} 1-10 nv{_lv_act[0]}")
                    elif len(_nos) == 1:
                        detail_parts.append(f"Ato {_act} andar {_nos[0]} nv{_lv_act[0] if len(_lv_act)==1 else f'{min(_lv_act)}-{max(_lv_act)}'}")
                    elif _nos == list(range(min(_nos), max(_nos) + 1)):
                        detail_parts.append(f"Ato {_act} andar {min(_nos)}-{max(_nos)} nv{min(_lv_act)}-{max(_lv_act)}" if len(_lv_act) > 1 else f"Ato {_act} andar {min(_nos)}-{max(_nos)} nv{_lv_act[0]}")
                    else:
                        detail_parts.append(f"Ato {_act} andar {','.join(map(str,_nos))} nv{min(_lv_act)}-{max(_lv_act)}")
                tip_detail = " | ".join(detail_parts)
                parts.append(f'<span class="bdif dif-{cls}" title="{act_str} {pt}{lv_str} • { _esc(tip_detail)} • caixa {matching_boxes[0] if matching_boxes else ""}">{_esc(act_str)} { _esc(pt)}</span>')
                tooltips.append(f"{act_str} {pt}{lv_str} ({tip_detail})")
            if plague:
                acts_p = sorted(set(s.get("act") for s in plague))
                for pa in acts_p:
                    sub = [s for s in plague if s.get("act")==pa]
                    nos = sorted(set(s.get("no") for s in sub if s.get("no") is not None))
                    if nos:
                        if len(nos)==1:
                            andar_str = f"andar {nos[0]}"
                        elif len(nos)==20:
                            andar_str = "andar 1-20"
                        else:
                            andar_str = f"andar {min(nos)}-{max(nos)}"
                    else:
                        andar_str = "andar 1-20"
                    label = f"Terras da Peste {andar_str} {pt}"
                    parts.append(f'<span class="bdif dif-{cls}" title="Terras da Peste {andar_str} {pt} • nv{lvl} — baús 915xxx/925xxx">{_esc(label)}</span>')
                    tooltips.append(label)
        if len(parts) > 3:
            shown = " ".join(parts[:2])
            more = len(parts)-2
            shown += f' <span class="muted">+{more}</span>'
            full = " · ".join(tooltips)
            return f'<span class="fdrop" title="{_esc(full)}">{shown}<span class="fmapwrap">{_drop_map_btn(name)}</span></span>'
        if parts:
            full = " · ".join(tooltips)
            return f'<span class="fdrop" title="{_esc(full)}">' + " ".join(parts) + f'<span class="fmapwrap">{_drop_map_btn(name)}</span></span>'
        return '<span class="fdrop muted">—</span>'
    except Exception:
        return '<span class="fdrop muted">—</span>'

# ── ranking ──────────────────────────────────────────────────────────

def _rank(itens: dict):
    vend = [(k, v) for k, v in itens.items() if v.get("sell") not in (None, 0, 0.0, "")]
    def hybrid(v):
        return (v.get("sell") or 0) * (math.log10((v.get("vol") or 0) + 1) + 1)
    top_hybrid = sorted(vend, key=lambda kv: hybrid(kv[1]), reverse=True)[:36]
    baleias    = sorted(vend, key=lambda kv: kv[1].get("sell") or 0, reverse=True)[:24]
    liquidos   = [kv for kv in vend if (kv[1].get("sell") or 0) >= 1.0 and (kv[1].get("vol") or 0) >= 10]
    liquidos   = sorted(liquidos, key=lambda kv: (kv[1].get("vol") or 0), reverse=True)[:30]
    # equilíbrio: sell >=0.5 e vol >=20 — sweet spot farm diário
    sweet      = [kv for kv in vend if (kv[1].get("sell") or 0) >= 0.5 and (kv[1].get("vol") or 0) >= 20]
    sweet      = sorted(sweet, key=lambda kv: hybrid(kv[1]), reverse=True)[:24]
    # moedinhas: volume altíssimo barato (para comparação)
    moedinhas  = sorted(vend, key=lambda kv: kv[1].get("vol") or 0, reverse=True)[:14]
    return {
        "vend_total": len(vend),
        "top_hybrid": top_hybrid,
        "baleias": baleias,
        "liquidos": liquidos,
        "sweet": sweet,
        "moedinhas": moedinhas,
    }

def _hybrid_score(v) -> float:
    try:
        return (v.get("sell") or 0) * (math.log10((v.get("vol") or 0) + 1) + 1)
    except Exception:
        return 0.0

_DAILY_CACHE = None  # (set nomes, dict nome->valor, rank dict, t)

def _get_daily_cached():
    global _DAILY_CACHE
    if _DAILY_CACHE is not None:
        return _DAILY_CACHE
    itens, t = _load_precos()
    if not itens:
        _DAILY_CACHE = (set(), {}, {"vend_total": 0, "top_hybrid": [], "baleias": [], "liquidos": [], "sweet": [], "moedinhas": []}, 0)
        return _DAILY_CACHE
    rank = _rank(itens)
    daily_names = set()
    for lst in (rank["top_hybrid"], rank["sweet"], rank["liquidos"], rank["baleias"]):
        for k, _v in lst:
            daily_names.add(k)
    daily_map = {k: itens[k] for k in daily_names if k in itens}
    _DAILY_CACHE = (daily_names, daily_map, rank, t)
    return _DAILY_CACHE

def daily_set() -> set:
    """Conjunto de nomes do mercado que estão no farm diário (união 36+24+30+24 ≈82 únicos)."""
    s, _, _, _ = _get_daily_cached()
    return set(s)

def itens_diarios_para_build(build: dict):
    """Devolve [(hero, slot, base, best_name, valor), ...] só itens desta build cuja base tem variante no diário. Ordenado por hybrid desc."""
    daily_names, daily_map, _, _ = _get_daily_cached()
    if not daily_map:
        return []
    cands = []
    for sec in (build.get("sections") or []):
        hero_raw = sec.get("hero", "")
        hero_short = re.sub(r"\s*\(level \d+\)", "", hero_raw).strip() or "Hero"
        for g in (sec.get("gear") or []):
            if ":" not in g:
                continue
            slot, name = g.split(":", 1)
            base = name.strip()
            if not base:
                continue
            prefix = base + " ("
            # todas variantes da base que estão no diário
            matches = [(k, daily_map[k]) for k in daily_map if k.startswith(prefix)]
            if not matches:
                continue
            best = max(matches, key=lambda kv: _hybrid_score(kv[1]))
            cands.append((hero_short, slot.strip(), base, best[0], best[1]))
    # ordenar: híbrido mais valioso primeiro
    cands.sort(key=lambda x: _hybrid_score(x[4]), reverse=True)
    return cands

def render_farm_para_build(build: dict, conta: str = None) -> str:
    """Bloco FARM POSSÍVEL compacto para injetar dentro da página da build (PASSO A PASSO).
    Se conta vier preenchida (ex: |user=Conta 1), o botão Farmar já leva &conta=Conta 1
    e a vigia só olha para essa conta; se None vigia todas e deteta sozinha qual droppou."""
    # auto-extrai |user da URL se não foi passado
    if not conta:
        try:
            _u = str(build.get("url", ""))
            if "|user=" in _u:
                conta = _u.split("|user=", 1)[1].split("|", 1)[0].strip() or None
        except: conta = None
    daily_names, _, rank, _ = _get_daily_cached()
    cands = itens_diarios_para_build(build)
    if not cands:
        return (
            '<div class="farmBuild farmBuild-empty">'
            '<div class="farmBuildHead">\U0001F33E FARM POSSÍVEL <span class="muted">só diários</span></div>'
            '<p class="farmBuildHint muted">Nenhum gear desta build está entre os itens diários (top_hybrid/sweet/líquidos/baleias) hoje. '
            'O gear é vendável noutros dias — foca <b>progressão/EXP/Ouro</b> por agora. '
            f'União do dia: {len(daily_names)} itens únicos.</p>'
            '</div>'
        )
    rows = ""
    for hero, slot, base, best_name, v in cands:
        grade = _grade_of(best_name)
        gchip = f'<span class="gchip g-{grade.lower()}">{_esc(grade)}</span>' if grade else ""
        link = _market_link(best_name)
        drop = _drop_html_for_name(best_name)
        med = v.get("med")
        med_s = _fmt_eur(med) if med else '<span class="muted">—</span>'
        # data attrs for sorting filters
        info = _info_for_market_name(best_name) or {}
        lvl = info.get("l") if info else 999
        try: lvl_n = int(lvl) if lvl is not None else 999
        except: lvl_n = 999
        hybrid = _hybrid_score(v)
        sell_n = v.get("sell") or 0
        vol_n = v.get("vol") or 0
        rows += (
            f'<tr data-sell="{sell_n}" data-vol="{vol_n}" data-lvl="{lvl_n}" data-hybrid="{hybrid:.2f}">'
            f'<td class="fb-slot"><span class="fb-hero">{_esc(hero)}</span> <span class="muted">{_esc(slot)}</span>'
            f'<br><span class="fb-base">{_esc(base)}</span></td>'
            f'<td class="fname"><a href="{link}" target="_blank">{_esc(best_name)}</a> {gchip}</td>'
            f'<td class="fdropcol">{drop}</td>'
            f'<td class="fprice">{_fmt_eur(v.get("sell"))}</td>'
            f'<td class="fvol">{_vol_badge(v.get("vol") or 0)}</td>'
            f'<td class="fmed">{med_s}</td>'
            f'<td><a class="fbuy" href="{link}" target="_blank">ver</a> {_farm_btn_html(best_name, conta)}</td>'
            f'</tr>'
        )
    n = len(cands)
    return (
        '<div class="farmBuild" data-farmbuild="1">'
        f'<div class="farmBuildHead">\U0001F33E FARM POSSÍVEL <span class="fbadge">{n} itens desta build no FARM DO DIA</span> <span class="muted" style="font-size:10.5px;font-weight:600">· dia:{len(daily_names)} un. diarios</span></div>'
        '<p class="farmBuildHint">Só itens diários — <b>top_hybrid 36 + sweet 24 + líquidos 30 + baleias 24</b> (união). Ordenado por <b>€/tempo</b> (hybrid = preço × (log10(vol+1)+1)). A coluna <b>Dropa em</b> mostra <b>Ato 1-3 Normal/Pesadelo/Inferno/Tormento</b> + <b>Terras da Peste andar 1-20</b>.</p>'
        '<div class="farmFilters" role="toolbar" aria-label="Ordenar farm possível"><span style="font-size:11px;color:#a89878;font-weight:700;">Ordenar:</span>'
        '<button type="button" class="ffilt on" data-sort="equilibrio" onclick="farmSort(this)">⚖️ Equilíbrio</button>'
        '<button type="button" class="ffilt" data-sort="caros" onclick="farmSort(this)">💰 Mais caros</button>'
        '<button type="button" class="ffilt" data-sort="venda" onclick="farmSort(this)">💧 Mais fácil de vender</button>'
        '<button type="button" class="ffilt" data-sort="drop" onclick="farmSort(this)">🎯 Mais fácil de drop</button></div>'
        f'<div class="ftablewrap fbwrap"><table class="ftable"><thead><tr><th>Peça (build)</th><th>Item diário (melhor variante)</th><th>Dropa em</th><th>Preço</th><th>Vol.24h</th><th>Mediana</th><th style="min-width:140px">Ações</th></tr></thead><tbody>{rows}</tbody></table></div>'
        '</div>'
    )

def _row_html(kv, rank=None, show_grade=True):
    name, v = kv
    sell = v.get("sell")
    vol = v.get("vol") or 0
    med = v.get("med")
    hist = v.get("hist") or 0
    grade = _grade_of(name)
    gchip = f'<span class="gchip g-{grade.lower()}">{_esc(grade)}</span>' if grade and show_grade else ""
    link = _market_link(name)
    sell_s = _fmt_eur(sell) if sell else "—"
    med_s = _fmt_eur(med) if med else '<span class="muted">—</span>'
    rk = f'<span class="frank">#{rank}</span>' if rank else ""
    drop_html = _drop_html_for_name(name)
    info = _info_for_market_name(name) or {}
    lvl = info.get("l") if info else 999
    try: lvl_n = int(lvl) if lvl is not None else 999
    except: lvl_n = 999
    hybrid = _hybrid_score(v)
    sell_n = sell or 0
    return (
        f'<tr data-sell="{sell_n}" data-vol="{vol}" data-lvl="{lvl_n}" data-hybrid="{hybrid:.2f}">'
        f'<td class="fname">{rk} <a href="{link}" target="_blank">{_esc(name)}</a> {gchip} '
        f'<span class="gtier">{_tier_emoji(grade)}</span></td>'
        f'<td class="fdropcol">{drop_html}</td>'
        f'<td class="fprice">{sell_s}</td>'
        f'<td class="fvol">{_vol_badge(vol)}</td>'
        f'<td class="fmed">{med_s}</td>'
        f'<td><a class="fbuy" href="{link}" target="_blank">ver</a> {_farm_btn_html(name)}</td>'
        f'</tr>'
    )

def _table_html(rows, rank_start=1):
    body = "".join(_row_html(kv, rank_start + i) for i, kv in enumerate(rows))
    return (
        '<div class="ftablewrap"><table class="ftable"><thead><tr>'
        '<th>Item</th><th>Dropa em</th><th>Preço (cliente paga)</th><th>Vol. 24h</th>'
        '<th>Mediana</th><th style="min-width:140px">Ações</th>'
        '</tr></thead><tbody>' + body + '</tbody></table></div>'
    )

# ── progresso das contas (para guia PROGRESSÃO) ─────────────────────

def _progresso_resumo() -> str:
    try:
        c = json.load(open(CACHE_BAUS, encoding="utf-8-sig"))
        contas = (c.get("payload") or {}).get("contas") or []
        if not contas:
            return ""
        # ordena por progresso: Hell > Nightmare > Normal > lvl
        order = {"Hell": 3, "Nightmare": 2, "Normal": 1, "": 0}
        def key(x):
            p = x.get("progresso") or {}
            return (order.get(p.get("max_dif") or "", 0), len(p.get("herois") or []))
        contas = sorted(contas, key=key, reverse=True)
        chips = []
        for ct in contas[:5]:
            p = ct.get("progresso") or {}
            nm = (ct.get("nome") or "?").split("(")[0].strip()
            mx = p.get("max") or p.get("atual") or "—"
            dif = (p.get("max_dif") or p.get("atual_dif") or "").lower()
            dcls = f" dif-{dif}" if dif else ""
            hero_lvl = ""
            herois = p.get("herois") or []
            if herois:
                hero_lvl = " · " + ", ".join(f'{h.get("nome","?")} nv{h.get("lvl","?")}' for h in herois[:3])
            chips.append(
                f'<span class="progchip"><b>{_esc(nm)}</b> '
                f'<span class="bdif{dcls}">{_esc(mx)}</span>'
                f'<span class="muted">{_esc(hero_lvl)}</span></span>'
            )
        return '<div class="progbar">' + " ".join(chips) + '</div>'
    except Exception:
        return ""

# ── guias passo-a-passo ─────────────────────────────────────────────

GUIDE_GOLD = r"""
<details class="guide" open><summary>💰 GOLD — como farmar ouro rápido</summary>
<div class="guidebody">
<p><b>Objetivo:</b> maximizar ouro por hora para comprar runas (o gargalo real do jogo).</p>
<ol>
  <li><b>Ativa as runas de OURO primeiro.</b> No mapa: <code>Rune of Wealth</code> (+ ouro do boss, 3 níveis, 1.000 ouro total),
      e depois <code>Rune of Opening / Containment</code> (abrir baús em massa). Estão no centro-direita do mapa; custo baixo, retorno imediato.</li>
  <li><b>Farma o estágio MAIS ALTO que limpas em ≤ 2 min.</b> Mais <code>waves</code> + <code>waveMonsters</code> + boss com <code>gold ×3</code> = mais ouro.
      Não adianta forçar Hell 3-6 se demoras 8 min: volta 1 dificuldade abaixo e limpa 3× mais rápido.</li>
  <li><b>Não pares para vender no meio.</b> Deixa o jogo em ciclo (o <code>atualizar_baus_agora.bat</code> já corre a cada 15 min). Ouro entra por boss + baús; vender itens é bónus.</li>
  <li><b>Vende SÓ o que tem venda ATIVA.</b> Abre <a href="inventario.html" target="_blank">inventario.html</a> → tabela <i>Só vendáveis</i>. O resto (Common/Uncommon, sem oferta) não conta — guarda ou descarta.</li>
  <li><b>Reinveste.</b> Cada 1.000 ouro em runas de ouro paga-se em poucas horas. Depois foca <code>Rune of Growth</code> (EXP) e <code>waves</code> para limpar ainda mais rápido.</li>
</ol>
<p class="gtip">💡 Dica: a Conta 1 já está em Hell 3-6 — é a tua mula de ouro. Puxa as outras até Hell para desbloquear o mesmo multiplicador.</p>
</div></details>
"""

GUIDE_EXP = r"""
<details class="guide"><summary>⚡ EXP — como subir de nível rápido (desbloquear a árvore)</summary>
<div class="guidebody">
<ol>
  <li><b>Runa de EXP primeiro.</b> <code>Rune of Growth</code> (+ EXP do boss, 3 níveis, 1.000 ouro) — ao lado da de ouro. Sem ela estás a perder ~30% de EXP por boss.</li>
  <li><b>Estágio com mais waves, não necessariamente mais difícil.</b> Cada wave = monstros = EXP. Um Normal 3-10 com 16 waves pode dar mais EXP/h que um Nightmare 3-5 onde morres.</li>
  <li><b>3 heróis a subir ao mesmo tempo.</b> O jogo divide EXP mas as tuas builds em mistura precisam de 3–4 heróis. Não foques só no main — alterna.</li>
  <li><b>Plague só quando já limpas Hell confortável.</b> Plague dá mais EXP mas exige build imortal (priest com leech). Forçar cedo = wipes = menos EXP/h.</li>
</ol>
<p class="gtip">💡 Atalho: na aba <b>UPAR JÁ</b> de cada build vês exatamente que skill falta subir (com tier e posição na árvore). Clica e vai direto ao nó.</p>
</div></details>
"""

GUIDE_ITENS = r"""
<details class="guide"><summary>📦 ITENS — o que vale a pena farmar (e o que é lixo) · com zonas de drop</summary>
<div class="guidebody">
<p><b>Regra de ouro do Mercado Steam:</b> só conta o <code>lowest_sell_order</code> (cliente paga agora). Mediana e volume sozinhos não pagam contas.</p>
<ul>
  <li><b>Common / Uncommon</b> — <span style="color:#ff8b8b">nunca vendável</span>. Nem tentes listar; o jogo não deixa. Dropa em <b>Ato 1 Normal</b> mas não vale nada.</li>
  <li><b>Rare / Legendary / Immortal (A/B)</b> — 90% vale <code>€0,03</code> mas com volume 10k–130k. Vende em &lt;1 dia, mas precisas de centenas para fazer €1. Dropa em <b>Ato 1-2 Pesadelo</b> (33-49).</li>
  <li><b>Arcana / Beyond</b> — sweet spot. Ex.: <code>Ancient Arrow (Beyond) C €0,82 vol 741</code>, <code>Eternal Armor (Celestial) C €0,76 vol 683</code>. Vendem hoje e pagam 20× mais que lixo. Dropa em <b>Ato 1-2 Inferno (53-65) + Terras da Peste andar 1-20 Inferno</b> (Plague 22).</li>
  <li><b>Celestial / Divine / Cosmic</b> — baleias. <code>Eclipse Amulet (Cosmic) A €1.173 vol 3</code>, <code>Eternal Bow (Cosmic) C €207 vol 12</code>. Drop raríssimo, mas um paga o mês. Dropa só em <b>Ato 1-3 Tormento (78-95) + Terras da Peste andar 1-20 Tormento</b> (Plague 23). Boss Boxes têm chance maior que Monster Boxes.</li>
</ul>
<p><b>Dropa em:</b> <span class="bdif dif-normal">Normal nv1-32</span> <span class="bdif dif-nightmare">Pesadelo nv33-52</span> <span class="bdif dif-hell">Inferno nv53-77</span> <span class="bdif dif-torment">Tormento nv78-95</span> — passa o rato no badge (nv + caixa).</p>
<p><b>Como farmar itens de valor:</b></p>
<ol>
  <li>Joga nos <b>Atos mais altos</b> e na <b>Terras da Peste andar mais alto</b> que conseguires (ato 3 Inferno/Tormento + Peste andar 15-20).</li>
  <li><b>Boss Boxes</b> têm chance maior de Cosmic/Divine. Prioriza estágios com <code>bossBoxRate</code> baixo (mais caixas por hora).</li>
  <li>Filtra pelo dashboard abaixo: <b>TOP Híbrido</b> = melhor €/tempo real. <b>Líquidos</b> = o que vende hoje. <b>Baleias</b> = lotaria. A coluna <b>Dropa em</b> já te diz onde focar (Ato x + Normal/Pesadelo/Inferno/Tormento e Terras da Peste andar 1-20).</li>
</ol>
<p class="gtip">💡 Dica: Se o item mostra <span class="bdif dif-torment">Terras da Peste andar 1-20 Tormento</span>, só vale farmar quando já limpas Inferno confortável — senão foca <span class="bdif dif-hell">Ato 2-3 Inferno / Terras da Peste Inferno</span> para sweet spot.</p>
</div></details>
"""

GUIDE_PROG = r"""
<details class="guide"><summary>🗺️ PROGRESSÃO — como chegar ao 23-20 Torment (Plague endgame)</summary>
<div class="guidebody">
<p><b>Meta:</b> <code>23-20 Torment Plaguelands</code> (nível 90, 25 waves, 24 monstros/wave). É onde caem os Cosmics baleia.</p>
<ol>
  <li><b>Empurra a campanha em Hell.</b> Cada ato tem 10 estágios; o boss do ato 10 (ex.: 1110 Throne of Darkness) desbloqueia o próximo ato. Não precisas de Plague para progredir.</li>
  <li><b>Build imortal obrigatória a partir do Ato 4–5 Hell.</b> Priest com <code>Attack Speed + Life Leech</code> (sem Wrath of Heaven) + DPS que mate em &lt;2 min. As tuas misturas 214+153 e 214+253 já são isso.</li>
  <li><b>Plague é NG+ por ato.</b> Só entra quando Hell do mesmo ato já é farm estável. Plague 21-1 repete o mapa do Ato 1 mas com monstros 30071+ e caixas 915xxx.</li>
  <li><b>Checklist por conta</b> (vê abaixo): se ainda estás em Normal 3-9/3-10, foca subir heróis para nv 50–60 e fechar runas de waves/dano antes de forçar Nightmare.</li>
</ol>
</div></details>
"""

# ── render principal ───────────────────────────────────────────────

def render_farm_op_section() -> str:
    itens, t = _load_precos()
    if not itens:
        return '<section id="farmOp" class="farmOp"><div class="farmOpHead"><h2>🌟 FARM OP</h2><p class="muted">Sem dados de mercado (precos_cache.json vazio). Corre o inventário uma vez.</p></div></section>'

    rank = _rank(itens)
    # data do cache
    try:
        dt = datetime.fromtimestamp(t).astimezone().strftime("%d/%m %H:%M") if t else "—"
    except Exception:
        dt = "—"

    prog_html = _progresso_resumo()

    # tabelas — limite 15 por tab para nao inchar pagina (confusa)
    html_top   = _table_html(rank["top_hybrid"][:15], 1)
    html_bale  = _table_html(rank["baleias"][:15], 1)
    html_liq   = _table_html(rank["liquidos"][:15], 1)
    html_sweet = _table_html(rank["sweet"][:15], 1) if rank["sweet"] else '<p class="muted">Nenhum item no sweet spot agora.</p>'

    # resumo números
    n_vend = rank["vend_total"]
    n_ge1  = len([kv for kv in itens.items() if (kv[1].get("sell") or 0) >= 1])
    n_bale = len([kv for kv in itens.items() if (kv[1].get("sell") or 0) >= 20])

    badges = (
        f'<span class="fstat"><b>{n_vend}</b> vendáveis agora</span>'
        f'<span class="fstat"><b>{n_ge1}</b> ≥ €1</span>'
        f'<span class="fstat"><b>{n_bale}</b> ≥ €20 (baleias)</span>'
        f'<span class="fstat muted">cache { _esc(dt) }</span>'
    )

    # Farm do dia — melhor hibrido com sweet spot
    pick = rank["sweet"][0] if rank["sweet"] else (rank["top_hybrid"][0] if rank["top_hybrid"] else None)
    pick_html = ""
    if pick:
        name, v = pick
        vol = v.get("vol") or 0
        dias_plain = "<1 dia" if vol and (1/vol) < 1 else (str(int(round(1/vol))) + " dias" if vol else "sem dados")
        drop_pick = _drop_html_for_name(name)
        pick_html = (
            '<div class="fpick">'
            '<div class="fpick-label">&#11088; FARM DO DIA — melhor &euro;/tempo hoje</div>'
            f'<a href="{_market_link(name)}" target="_blank" class="fpick-name">{_esc(name)}</a>'
            f'<span class="fpick-price">{_fmt_eur(v.get("sell"))}</span>'
            f'<span class="fpick-vol">vol {vol}</span>'
            f'<span class="fpick-hint">vende em ~{dias_plain} &middot; mediana {_fmt_eur(v.get("med")) if v.get("med") else "—"}</span>'
            f'<span class="fpick-drop">Dropa em: {drop_pick}</span>'
            '</div>'
        )

    return (
        '<section id="farmOp" class="farmOp">'
        '<div class="farmOpHead">'
        '<h2>🌟 FARM OP — O QUE VALE A PENA FARMAR AGORA</h2>'
        '<p class="farmOpSub">Ranking ao vivo por <b>preço × volume</b> (o que paga E vende). Clica no item para abrir no Mercado Steam. '
        'Dica: Common/Uncommon nunca vendem; foca Arcana+ com volume. Coluna <b>Dropa em</b> mostra <b>Ato 1-3 + Normal / Pesadelo / Inferno / Tormento</b> e <b>Terras da Peste andar 1-20 Pesadelo/Inferno/Tormento</b>.</p>'
        f'<div class="fstats">{badges}</div>'
        f'{prog_html}'
        f'{pick_html}'
        '</div>'

        '<div class="farmTabs" role="tablist">'
        '<button class="ftab on" data-tab="top">🏆 TOP HÍBRIDO</button>'
        '<button class="ftab" data-tab="sweet">⚖️ SWEET SPOT</button>'
        '<button class="ftab" data-tab="liq">💧 LÍQUIDOS (≥€1)</button>'
        '<button class="ftab" data-tab="bale">🐋 BALEIAS</button>'
        '<button class="ftab" data-tab="guias">📖 GUIAS PASSO-A-PASSO</button>'
        '</div>'

        f'<div class="ftabpan on" id="ftab-top"><p class="ftabhint">Melhor equilíbrio <b>valor × liquidez</b>: score = preço × (log10(vol+1)+1). É o ranking mais honesto para farm diário. Coluna <b>Dropa em</b> = <b>Ato 1-3 Normal/Pesadelo/Inferno/Tormento</b> + <b>Terras da Peste andar 1-20</b>.</p>'
        f'<div class="farmFilters"><span style="font-size:11px;color:#a89878;font-weight:700;">Ordenar:</span>'
        f'<button type="button" class="ffilt on" data-sort="equilibrio" onclick="farmSortGlobal(this)">⚖️ Equilíbrio</button>'
        f'<button type="button" class="ffilt" data-sort="caros" onclick="farmSortGlobal(this)">💰 Mais caros</button>'
        f'<button type="button" class="ffilt" data-sort="venda" onclick="farmSortGlobal(this)">💧 Mais fácil de vender</button>'
        f'<button type="button" class="ffilt" data-sort="drop" onclick="farmSortGlobal(this)">🎯 Mais fácil de drop</button></div>{html_top}</div>'
        f'<div class="ftabpan" id="ftab-sweet"><p class="ftabhint">Sweet spot: <b>€0,50+ e vol ≥20</b> — pagam bem E vendem hoje. É onde o ouro/hora é maior sem depender de lotaria.</p>'
        f'<div class="farmFilters"><span style="font-size:11px;color:#a89878;font-weight:700;">Ordenar:</span>'
        f'<button type="button" class="ffilt on" data-sort="equilibrio" onclick="farmSortGlobal(this)">⚖️ Equilíbrio</button>'
        f'<button type="button" class="ffilt" data-sort="caros" onclick="farmSortGlobal(this)">💰 Mais caros</button>'
        f'<button type="button" class="ffilt" data-sort="venda" onclick="farmSortGlobal(this)">💧 Mais fácil de vender</button>'
        f'<button type="button" class="ffilt" data-sort="drop" onclick="farmSortGlobal(this)">🎯 Mais fácil de drop</button></div>{html_sweet}</div>'
        f'<div class="ftabpan" id="ftab-liq"><p class="ftabhint">Só itens <b>≥ €1 com vol ≥10</b>, ordenados por volume (quem vende mais rápido primeiro).</p>'
        f'<div class="farmFilters"><span style="font-size:11px;color:#a89878;font-weight:700;">Ordenar:</span>'
        f'<button type="button" class="ffilt on" data-sort="equilibrio" onclick="farmSortGlobal(this)">⚖️ Equilíbrio</button>'
        f'<button type="button" class="ffilt" data-sort="caros" onclick="farmSortGlobal(this)">💰 Mais caros</button>'
        f'<button type="button" class="ffilt" data-sort="venda" onclick="farmSortGlobal(this)">💧 Mais fácil de vender</button>'
        f'<button type="button" class="ffilt" data-sort="drop" onclick="farmSortGlobal(this)">🎯 Mais fácil de drop</button></div>{html_liq}</div>'
        f'<div class="ftabpan" id="ftab-bale"><p class="ftabhint">Chase items — preço puro. Drop raríssimo, volume 1–3. Um paga o mês, mas podes farmar semanas sem ver um.</p>'
        f'<div class="farmFilters"><span style="font-size:11px;color:#a89878;font-weight:700;">Ordenar:</span>'
        f'<button type="button" class="ffilt on" data-sort="equilibrio" onclick="farmSortGlobal(this)">⚖️ Equilíbrio</button>'
        f'<button type="button" class="ffilt" data-sort="caros" onclick="farmSortGlobal(this)">💰 Mais caros</button>'
        f'<button type="button" class="ffilt" data-sort="venda" onclick="farmSortGlobal(this)">💧 Mais fácil de vender</button>'
        f'<button type="button" class="ffilt" data-sort="drop" onclick="farmSortGlobal(this)">🎯 Mais fácil de drop</button></div>{html_bale}</div>'

        '<div class="ftabpan" id="ftab-guias">'
        '<p class="ftabhint">Quatro guias práticos — segue na ordem: ouro → exp → itens → progressão.</p>'
        f'{GUIDE_GOLD}{GUIDE_EXP}{GUIDE_ITENS}{GUIDE_PROG}'
        '<p class="gfoot">Dados: <code>precos_cache.json</code> + <code>baus_cache.json</code> · <code>tbhStages.js</code> (189 stages). Atualiza a cada 15 min via <code>run.bat</code>.</p>'
        '</div>'

        '</section>'
    )

# CLI teste
if __name__ == "__main__":
    html = render_farm_op_section()
    open(os.path.join(ROOT, "_farm_preview.html"), "w", encoding="utf-8").write(
        "<!doctype html><meta charset=utf-8><style>"
        "body{background:#0e0c0a;color:#e8dcc0;font-family:system-ui;padding:24px} a{color:#ffd86b}"
        "</style>" + html
    )
    print("OK preview em _farm_preview.html —", len(html), "chars")
