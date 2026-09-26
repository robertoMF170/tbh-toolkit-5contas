import os
import re
import sys
import io
import json
import base64
import collections
import html as htmlmod
import urllib.parse
import tbh_mapa as tm
from urllib.request import urlopen, Request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
# compat: suporta tanto nova estrutura (data/tbhdata, assets/) como legacy na raiz
def _first_dir(*cands):
    for p in cands:
        if os.path.isdir(p): return p
    return cands[0]
DATA_DIR = _first_dir(os.path.join(ROOT, "data", "tbhdata"), os.path.join(ROOT, "tbhdata"), os.path.join(BASE, "tbhdata"))
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

ASSET_NAMES = ["tbhSkillTree", "tbhRunes", "tbhRuneCosts", "heroMeta"]


def http_get(url: str) -> str:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def ensure_data_files() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    have = os.listdir(DATA_DIR)
    for key in ASSET_NAMES:
        if any(f.startswith(key) for f in have):
            continue
        home = http_get("https://tbhindex.com/pt")
        m = re.search(r'/assets/' + key + r'-[A-Za-z0-9_-]+\.js', home)
        if not m:
            raise RuntimeError("Nao encontrei o asset " + key + " no site")
        url = "https://tbhindex.com" + m.group(0)
        name = m.group(0).split("/")[-1]
        with open(os.path.join(DATA_DIR, name), "w", encoding="utf-8") as f:
            f.write(http_get(url))
        print("(descarregado: " + name + ")")


def read_asset(key: str) -> str:
    for f in os.listdir(DATA_DIR):
        if f.startswith(key):
            with open(os.path.join(DATA_DIR, f), "r", encoding="utf-8") as fh:
                return fh.read()
    raise RuntimeError("asset em falta: " + key)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def pretty_stat(stat: str) -> str:
    out = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", stat)
    return out[0].upper() + out[1:]


def load_game_data() -> dict:
    s = read_asset("tbhSkillTree")

    heroes = {}
    for m in re.finditer(r"(\d{3}):\{name:`([A-Za-z]+)`,tiers:\[", s):
        heroes[int(m.group(1))] = m.group(2)

    actives = {}
    for m in re.finditer(r"(\d{5}):\{name:`([^`]+)`", s):
        aid, aname = int(m.group(1)), m.group(2)
        chunk = s[m.start():m.start() + 700]
        ml = re.search(r"maxLevel:(\d+)", chunk)
        actives[aid] = {"name": aname, "maxLevel": int(ml.group(1)) if ml else 1, "heroDigit": aid // 10000}

    passives = {}
    for m in re.finditer(r"(\d{6}):\{statType:`([A-Za-z]+)`", s):
        pid, st = int(m.group(1)), m.group(2)
        chunk = s[m.start():m.start() + 300]
        ml = re.search(r"maxLevel:(\d+)", chunk)
        mv = re.search(r"value:([-\d.e]+)", chunk)
        mt = re.search(r"modType:`([A-Za-z]+)`", chunk)
        passives[pid] = {
            "statType": st,
            "label": pretty_stat(st),
            "maxLevel": int(ml.group(1)) if ml else 1,
            "value": float(mv.group(1)) if mv else 0,
            "modType": mt.group(1) if mt else "",
            "heroDigit": pid // 100000,
        }

    trees = {}
    hero_pos = [(m.start(), int(m.group(1)), m.group(2))
                for m in re.finditer(r"(\d{3}):\{name:`([A-Za-z]+)`,tiers:\[", s)]
    for idx, (pos, code, name) in enumerate(hero_pos):
        end = hero_pos[idx + 1][0] if idx + 1 < len(hero_pos) else pos + 6000
        chunk = s[pos:end]
        tiers = []
        for tm in re.finditer(r"\{groupKey:\d+,passives:\[([\d,]*)\],actives:\[([\d,]*)\]\}", chunk):
            pv = [int(x) for x in tm.group(1).split(",") if x]
            av = [int(x) for x in tm.group(2).split(",") if x]
            tiers.append({"passives": pv, "actives": av})
        trees[code] = {"name": name, "tiers": tiers}

    return {"heroes": heroes, "actives": actives, "passives": passives, "trees": trees}


def fetch_build(url: str) -> dict:
    raw = http_get(url)
    c = raw.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')

    mtitle = re.search(r"<h1[^>]*>(.*?)</h1>", c, re.S)
    title = re.sub(r"<[^>]+>", "", mtitle.group(1)).strip() if mtitle else "build"

    paras = [(m.start(), re.sub(r"<[^>]+>", "", m.group(1)).strip()) for m in re.finditer(r"<p(?![a-z])[^>]*>(.*?)</p>", c, re.S)]
    h2s = [(m.start(), re.sub(r"<[^>]+>", "", m.group(1)).strip()) for m in re.finditer(r"<h2(?![a-z])[^>]*>(.*?)</h2>", c, re.S)]
    lis = [(m.start(), re.sub(r"<[^>]+>", "", m.group(1)).strip()) for m in re.finditer(r"<li(?![a-z])[^>]*>(.*?)</li>", c, re.S)]

    notes = ""
    category = ""
    for pos, p in paras + lis:
        hp = [h for h in h2s if h[0] < pos]
        cur = hp[-1][1] if hp else ""
        if cur == "Notes":
            notes += p + "\n\n"
        elif cur == "Build Stats" and not category and p.startswith("Category"):
            category = p[len("Category"):].strip()
    notes = notes.strip()

    hero_sections = []
    hero_headers = [(pos, h) for pos, h in h2s if re.match(r".+\(level \d+\)", h)]
    for i, (pos, h) in enumerate(hero_headers):
        end = hero_headers[i + 1][0] if i + 1 < len(hero_headers) else len(c)
        sec = {"hero": h, "gear": [], "skills": [], "priority": []}
        for ppos, p in paras:
            if not (pos < ppos < end):
                continue
            if p.startswith("Gear:"):
                sec["gear"] = [g.strip() for g in p[5:].split(",") if g.strip()]
            elif p.startswith("Skills:"):
                for item in p[7:].split(","):
                    item = item.strip()
                    sm = re.match(r"(.+?)\s+(\d+)$", item)
                    if sm:
                        sec["skills"].append((sm.group(1).strip(), int(sm.group(2))))
                    elif item:
                        sec["skills"].append((item, None))
            elif p.startswith("Stat priority:"):
                sec["priority"] = [g.strip() for g in p[14:].split(",") if g.strip()]
        hero_sections.append(sec)

    return {"title": title, "url": url, "notes": notes, "category": category, "sections": hero_sections}


def match_section(sec: dict, data: dict) -> dict:
    hero_name = re.sub(r"\s*\(level \d+\)", "", sec["hero"]).strip().lower()
    code = next((k for k, v in data["heroes"].items() if v.lower() == hero_name), None)

    used_p = set()
    used_a = set()
    steps = []
    for name, lvl in sec["skills"]:
        n = norm(name)
        step = {"name": name, "lvl": lvl, "kind": "?", "ref": None, "note": ""}

        cands = [a for a in data["actives"].items() if norm(a[1]["name"]) == n]
        if cands:
            free = [c for c in cands if c[0] not in used_a]
            pick = (free or cands)[0]
            aid, a = pick
            used_a.add(aid)
            step.update(kind="ativa", ref=a, src=aid)
            if lvl is not None and lvl > a["maxLevel"]:
                step["note"] = "maximo e " + str(a["maxLevel"])
                step["lvl"] = a["maxLevel"]
            if pick in cands and not free:
                step["note"] = (step["note"] + " " if step["note"] else "") + "repetida"
            steps.append(step)
            continue

        pool_order = []
        if code:
            pool_order.append(code)
        pool_order += [k for k in sorted(data["trees"]) if k != code]

        picked = None
        for pc in pool_order:
            digit = pc // 100
            nodes = [(pid, p) for pid, p in data["passives"].items() if p["heroDigit"] == digit and norm(p["statType"]) == n]
            if not nodes:
                continue
            if lvl is not None:
                exact = [x for x in nodes if x[0] not in used_p and x[1]["maxLevel"] == lvl]
                fits = [x for x in nodes if x[0] not in used_p and x[1]["maxLevel"] > (lvl or 0)]
                partial = [x for x in nodes if x[0] not in used_p]
            else:
                exact, fits, partial = [], [], [x for x in nodes if x[0] not in used_p]
            picklist = exact or fits or partial or nodes
            picklist.sort(key=lambda x: (x[1]["maxLevel"], x[0]))
            picked = picklist[0]
            if pc != code:
                step["note"] = "passiva de outro heroi (" + data["heroes"].get(pc, "?") + ")"
            break

        if picked:
            pid, p = picked
            used_p.add(pid)
            step.update(kind="passiva", ref=p, src=pid)
            if lvl is not None and lvl > p["maxLevel"]:
                step["note"] = (step["note"] + " " if step["note"] else "") + "maximo e " + str(p["maxLevel"])
                step["lvl"] = p["maxLevel"]
        else:
            step.update(kind="desconhecida", ref=None, src=None)
            step["note"] = "nao encontrei na arvore"
        steps.append(step)

    sec = dict(sec)
    sec["matchedCode"] = code
    sec["steps"] = steps
    return sec


def load_hero_icons() -> dict:
    d = _first_dir(os.path.join(ROOT, "assets", "icons_hero"), os.path.join(ROOT, "icons_hero"), os.path.join(BASE, "icons_hero"))
    prefix = "assets/icons_hero/" if "assets" in d else "icons_hero/"
    # fallback adicional para data icone legado
    out = {}
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.endswith(".png"):
                out[f[:-4]] = prefix + f
    return out


HERO_ICONS = {}
SKILL_ICONS = {}
DISPLAY_NAMES = {}


def esc(s) -> str:
    return htmlmod.escape(str(s))


def color_for_step(i: int, total: int) -> str:
    hue = int(120 - 120 * (i / max(1, total - 1)))
    return f"hsl({hue},85%,55%)"


def render_build_svg(matched: list, data: dict, save_state: dict = None) -> str:
    node_w, col_w, sq = 190, 250, 64
    save_attrs = (save_state or {}).get("attrs") or {}
    save_grupos = (save_state or {}).get("grupos") or {}
    gap = 170
    H = 660

    ref_to_step = {}
    offset = 0
    for sec in matched:
        for j, st in enumerate(sec["steps"]):
            if st["src"] is not None:
                ref_to_step.setdefault(st["src"], []).append(offset + j + 1)
        offset += len(sec["steps"])

    lvl_by_src = {}
    for sec in matched:
        for st in sec["steps"]:
            if st["src"] is not None and st["lvl"] is not None:
                lvl_by_src[st["src"]] = st["lvl"]

    clusters = []
    x0 = 40
    for sec in matched:
        code = sec.get("matchedCode")
        tree = data["trees"].get(code) if code else None
        if not tree:
            clusters.append(None)
            continue
        tiers = tree["tiers"]
        rows = []
        max_slots = 0
        for ti, tier in enumerate(tiers):
            slots = []
            if tier["passives"]:
                slots.append((tier["passives"][0], "p"))
            if len(tier["passives"]) > 1:
                slots.append((tier["passives"][1], "p"))
            for aid in tier["actives"]:
                slots.append((aid, "a"))
            for k, (nid, kind) in enumerate(slots):
                slots[k] = (nid, kind, x0 + 90 + k * 78, 130 + ti * 128)
            max_slots = max(max_slots, len(slots))
            rows.append(slots)
        cw = 110 + max_slots * 78 + 60
        clusters.append({"sec": sec, "rows": rows, "x0": x0, "w": cw})
        x0 += cw + gap
    W = x0 - gap + 20
    H = 130 + 8 * 128 + 60
    if W <= 0:
        return "<p>Sem arvores para desenhar</p>"

    parts = []
    parts.append(f'<svg class="tree" width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">')

    pos_by_src = {}
    prev_cl = None
    for cl in clusters:
        if not cl:
            prev_cl = None
            continue
        rows = cl["rows"]
        hero_name = re.sub(r"\s*\(level \d+\)", "", cl["sec"]["hero"]).strip()
        parts.append(f'<text x="{cl["x0"]}" y="64" class="zonelabel">{esc(hero_name.upper())}</text>')
        if prev_cl:
            px = prev_cl["x0"] + prev_cl["w"] - 20
            parts.append(f'<line x1="{px}" y1="330" x2="{cl["x0"] - 10}" y2="330" class="edgebridge"/>')
        for ti, slots in enumerate(rows):
            ry = 130 + ti * 128
            parts.append(f'<text x="{cl["x0"] + 20}" y="{ry + 40}" class="rowlabel">T{ti + 1}</text>')
            if ti < len(rows) - 1 and slots:
                parts.append(f'<line x1="{slots[0][2] + 32:.0f}" y1="{ry + 66:.0f}" x2="{slots[0][2] + 32:.0f}" y2="{ry + 128 + 62:.0f}" class="edge"/>')
            for pid, kind, bx, by in slots:
                nums = ref_to_step.get(pid, [])
                # data-key: permite a dashboard saltar para este nó (recomendações)
                parts.append(f'<g data-key="{pid}" transform="translate({bx:.0f},{by:.0f})">')
                used = bool(nums)
                if used:
                    pos_by_src[pid] = (bx + 32, by + 32)
                if kind == "p":
                    info = data["passives"].get(pid)
                    if not info:
                        continue
                    tip_base = f'{DISPLAY_NAMES.get(pid, info["label"])} +{info["value"]:g} · max {info["maxLevel"]}'
                    ic = HERO_ICONS.get(info["statType"].lower())
                    letters = esc(info["label"][:2].upper())
                    maxlvl = info["maxLevel"]
                    alvo = lvl_by_src.get(pid)
                    atual = save_attrs.get(pid, 0)
                    _code_tmp = cl["sec"].get("matchedCode")
                    _grupos_tmp = save_grupos.get(_code_tmp, 999) if save_state is not None else 999
                    _locked = (ti > _grupos_tmp) if save_state is not None else False
                    if not used:
                        tip = tip_base
                        sub = f'max {maxlvl}'
                        cls_sq = "off"
                        cls_under = "off"
                        cls_glow = None
                    else:
                        if save_state is not None:
                            if atual >= (alvo or 0):
                                tip = tip_base + f' · \u2713 FEITO {atual}/{alvo}'
                                sub = f'\u2713 {atual}/{alvo} FEITO'
                                cls_sq = "done"
                                cls_under = "done"
                                cls_glow = "done"
                            elif _locked:
                                tip = tip_base + f' · \U0001F512 BLOQUEADA T{ti+1} (sobe her\u00f3i)'
                                sub = f'\U0001F512 T{ti+1} bloqueada'
                                cls_sq = "locked"
                                cls_under = "locked"
                                cls_glow = None
                            elif atual > 0:
                                tip = tip_base + f' · {atual}\u2192{alvo} (falta {alvo-atual})'
                                sub = f'{atual}\u2192{alvo}/{maxlvl}'
                                cls_sq = "partial"
                                cls_under = "partial"
                                cls_glow = "partial"
                            else:
                                tip = tip_base + f' · \u2192{alvo} por fazer'
                                sub = f'\u2192 {alvo}/{maxlvl}'
                                cls_sq = "todo"
                                cls_under = "todo"
                                cls_glow = "todo"
                        else:
                            tip = tip_base
                            sub = f'\u2192 nv {alvo}/{maxlvl}'
                            cls_sq = "used"
                            cls_under = "gold"
                            cls_glow = "gold"
                else:
                    info = data["actives"].get(pid)
                    if not info:
                        continue
                    tip_base = f'{DISPLAY_NAMES.get(pid, info["name"])} \u00b7 ativa \u00b7 max {info["maxLevel"]}'
                    ic = SKILL_ICONS.get(pid)
                    letters = esc(info["name"][:2].upper())
                    maxlvl = info["maxLevel"]
                    alvo = lvl_by_src.get(pid)
                    atual = save_attrs.get(pid, 0)
                    _code_tmp = cl["sec"].get("matchedCode")
                    _grupos_tmp = save_grupos.get(_code_tmp, 999) if save_state is not None else 999
                    _locked = (ti > _grupos_tmp) if save_state is not None else False
                    if not used:
                        tip = tip_base
                        sub = f'max {maxlvl}'
                        cls_sq = "off"
                        cls_under = "off"
                        cls_glow = None
                    else:
                        if save_state is not None:
                            if atual >= (alvo or 0):
                                tip = tip_base + f' \u00b7 \u2713 FEITO {atual}/{alvo}'
                                sub = f'\u2713 {atual}/{alvo} FEITO'
                                cls_sq = "done"
                                cls_under = "done"
                                cls_glow = "done"
                            elif _locked:
                                tip = tip_base + f' \u00b7 \U0001F512 BLOQUEADA T{ti+1} (sobe her\u00f3i)'
                                sub = f'\U0001F512 T{ti+1} bloqueada'
                                cls_sq = "locked"
                                cls_under = "locked"
                                cls_glow = None
                            elif atual > 0:
                                tip = tip_base + f' \u00b7 {atual}\u2192{alvo} (falta {alvo-atual})'
                                sub = f'{atual}\u2192{alvo}/{maxlvl}'
                                cls_sq = "partial"
                                cls_under = "partial"
                                cls_glow = "partial"
                            else:
                                tip = tip_base + f' \u00b7 \u2192{alvo} por fazer'
                                sub = f'\u2192 {alvo}/{maxlvl}'
                                cls_sq = "todo"
                                cls_under = "todo"
                                cls_glow = "todo"
                        else:
                            tip = tip_base
                            sub = f'\u2192 nv {alvo}/{maxlvl}'
                            cls_sq = "used"
                            cls_under = "gold"
                            cls_glow = "gold"
                parts.append(f'<title>{esc(tip)}</title>')
                if cls_glow:
                    parts.append(f'<rect x="-6" y="-6" width="76" height="76" rx="19" class="glow {cls_glow}"/>')
                parts.append(f'<rect width="64" height="64" rx="14" class="sq {cls_sq}"/>')
                if ic and used:
                    parts.append(f'<image x="12" y="12" width="40" height="40" href="{ic}"/>')
                elif ic and not used:
                    # off nodes: sem imagem base64 (economia ~100KB) — só mostra letra
                    parts.append(f'<text x="32" y="40" class="q">{letters}</text>')
                else:
                    parts.append(f'<text x="32" y="40" class="q">{letters}</text>')
                for k, num in enumerate(nums):
                    cx = 64 - 8 - k * 26
                    parts.append(f'<circle cx="{cx}" cy="4" r="13" class="ringbadge"/>')
                    parts.append(f'<text x="{cx}" y="9" class="stepnum">{num}</text>')
                parts.append(f'<text x="32" y="80" class="under {cls_under}">{esc(sub)}</text>')
                parts.append("</g>")
        prev_cl = cl

    route = []
    for sec in matched:
        for st in sec["steps"]:
            pt = pos_by_src.get(st.get("src"))
            if pt and (not route or route[-1] != pt):
                route.append(pt)
    if len(route) > 1:
        d = " L ".join(f"{int(px)} {int(py)}" for px, py in route)
        parts.append(f'<path d="M {d}" class="routeline"/>')

    parts.append("</svg>")
    return "\n".join(parts), W


def build_runes_svg(runedata: tuple) -> tuple:
    mp, runes, costs = runedata[:3]
    nodes = mp["nodes"]
    edges = mp["edges"]
    xs = [v[0] for v in nodes.values()]
    ys = [v[1] for v in nodes.values()]
    pad = 90
    minx, maxx, miny, maxy = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    W, H = maxx - minx, maxy - miny

    def sx(x):
        return x - minx

    def sy(y):
        return maxy - y

    parts = []
    parts.append(f'<svg class="tree" width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">')
    for src, tid in edges:
        if str(src) not in nodes or str(tid) not in nodes:
            continue
        parts.append(
            f'<line x1="{sx(nodes[str(src)][0]):.0f}" y1="{sy(nodes[str(src)][1]):.0f}" '
            f'x2="{sx(nodes[str(tid)][0]):.0f}" y2="{sy(nodes[str(tid)][1]):.0f}" class="edge"/>'
        )
    for nid_str, (x, y) in sorted(nodes.items(), key=lambda kv: int(kv[0])):
        nid = int(nid_str)
        r = runes.get(nid, {})
        c = costs.get(nid, {})
        icon = r.get("icon", "")
        href = tm.icon_path(icon)
        label = r.get("label", "?")
        stat = r.get("stat", "?")
        mx = c.get("maxLevel", "?")
        tot = c.get("total", 0)
        tip = f"{label} | {stat} | max {mx} | custo total {tot:,} ouro".replace(",", ".")
        cx, cy = sx(x), sy(y)
        parts.append(f'<g class="node" data-id="{nid}" transform="translate({cx - 32:.0f},{cy - 32:.0f})"><title>{esc_html(tip)}</title><rect width="64" height="64" rx="14" class="box"/>')
        if href:
            parts.append(f'<image x="10" y="10" width="44" height="44" href="{href}"/>')
        else:
            parts.append('<text x="32" y="40" class="q">?</text>')
        parts.append("</g>")
    parts.append('<path id="runefull" fill="none" stroke="#ffd86b" stroke-width="2" stroke-dasharray="2 10" opacity="0.25"/>')
    parts.append('<path id="runeroute" fill="none" stroke="#ffd86b" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" opacity="0.95"/>')
    parts.append('<g id="badgeLayer"></g>')
    parts.append("</svg>")
    return "\n".join(parts), W


def walk_route(mp: dict, root: int, ordered: list) -> list:
    nodes = {int(k): v for k, v in mp["nodes"].items()}
    adj = collections.defaultdict(set)
    for a, b in mp["edges"]:
        if a in nodes and b in nodes:
            adj[a].add(b)
            adj[b].add(a)
    if root not in nodes:
        root = min(nodes)
    owned = {root}
    route = [root]
    for tgt in ordered:
        if tgt in owned or tgt not in nodes:
            continue
        par = {}
        dist = {n: 0 for n in owned}
        q = collections.deque(owned)
        while q:
            cur = q.popleft()
            if cur == tgt:
                break
            for nb in adj[cur]:
                if nb not in dist:
                    dist[nb] = dist[cur] + 1
                    par[nb] = cur
                    q.append(nb)
        if tgt not in dist:
            continue
        path = []
        n = tgt
        while n not in owned:
            path.append(n)
            n = par[n]
        path.reverse()
        for n in path:
            route.append(n)
            owned.add(n)
    return route


def compute_route_presets(mp: dict, runes: dict, costs: dict) -> dict:
    nodes = {int(k) for k in mp["nodes"]}
    root = 1 if 1 in nodes else min(nodes)

    def stat_of(nid):
        return runes.get(nid, {}).get("stat", "")

    def cost_of(nid):
        return costs.get(nid, {}).get("total", 10 ** 9)

    def ordered(groups):
        out = []
        done = {root}
        for pred in groups:
            tg = [nid for nid in nodes if nid not in done and pred(stat_of(nid))]
            tg.sort(key=cost_of)
            for nid in tg:
                out.append(nid)
                done.add(nid)
        return out

    presets = {}
    single = {
        "ouro": lambda s: "gold" in s.lower(),
        "exp": lambda s: "exp" in s.lower(),
        "combate": lambda s: s.lower().startswith("all hero"),
    }
    for goal, pred in single.items():
        presets[goal] = walk_route(mp, root, ordered([pred]))
    presets["farm"] = walk_route(mp, root, ordered([
        lambda s: "gold" in s.lower() or "exp" in s.lower() or "wave" in s.lower(),
        lambda s: "move speed" in s.lower() or "skill slot" in s.lower() or "attack" in s.lower() or "armor" in s.lower(),
        lambda s: any(k in s.lower() for k in ("drop chance", "auto open", "inventory", "max amount", "stash", "arrange")),
        lambda s: "offline" in s.lower() or "cube" in s.lower(),
    ]))
    return presets


def compute_ideal_route(mp: dict, runes: dict, costs: dict, category: str = "", notes: str = "") -> list:
    nodes = {int(k) for k in mp["nodes"]}
    root = 1 if 1 in nodes else min(nodes)

    def stat(nid):
        return runes.get(nid, {}).get("stat", "").lower()

    def cost(nid):
        return costs.get(nid, {}).get("total", 10 ** 9)

    text = ((category or "") + " " + (notes or "")).lower()

    def pick(preds, exclude):
        out = []
        for nid in nodes:
            if nid in exclude:
                continue
            s = stat(nid)
            if any(p(s) for p in preds):
                out.append(nid)
        return out

    exp_first = any(k in text for k in ("exp", "level", "xp", "speed"))
    gold_first = any(k in text for k in ("gold", "sell", "money", "budget", "farm"))
    plague_early = "plague" in text
    boss_early = "boss" in text and "act" in text

    tiers = []
    tiers.append([lambda s: "wave" in s])
    tiers.append([lambda s: "skill slot" in s])
    tiers.append([lambda s: "move speed" in s])
    if plague_early:
        tiers.append([lambda s: "plague" in s])
    tiers.append([lambda s: "all hero" in s and "attack damage" in s])
    if gold_first:
        tiers.append([lambda s: "gold" in s])
    if exp_first:
        tiers.append([lambda s: "exp" in s])
    if not gold_first and not exp_first:
        tiers.append([lambda s: "gold" in s or "exp" in s])
    if exp_first and gold_first:
        tiers.append([lambda s: "gold" in s or "exp" in s])
    if boss_early:
        tiers.append([lambda s: "act boss" in s])
    tiers.append([lambda s: "auto open" in s])
    tiers.append([lambda s: "drop chance" in s])
    if not plague_early:
        tiers.append([lambda s: "plague" in s])
    tiers.append([lambda s: "inventory" in s or "max amount" in s])
    tiers.append([lambda s: "attack speed" in s or ("all hero" in s and "armor" in s) or "damage percent" in s])
    tiers.append([lambda s: "stash" in s or "arrange" in s or "offline" in s or "cube" in s])

    ranked = []
    done = {root}
    for preds in tiers:
        tg = pick(preds, done)
        tg.sort(key=lambda nid: cost(nid))
        for nid in tg:
            ranked.append(nid)
            done.add(nid)
    leftovers = sorted((nid for nid in nodes if nid not in done), key=cost)
    ranked += leftovers
    return walk_route(mp, root, ranked)


def esc_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def render_html(build: dict, data: dict, runedata: tuple) -> str:
    matched = [match_section(sec, data) for sec in build["sections"]]
    svg, W = render_build_svg(matched, data)
    rsvg, RW = build_runes_svg(runedata)
    presets = runedata[3] if len(runedata) > 3 else {}
    presets_json = json.dumps(presets)

    rows = []
    hero_blocks = []
    offset = 0
    for sec in matched:
        hero_short = re.sub(r"\s*\(level \d+\)", "", sec["hero"]).strip()
        chip = esc(hero_short[:3].upper())
        for j, st in enumerate(sec["steps"]):
            num = offset + j + 1
            kind = st["kind"]
            icon = {"ativa": "★", "passiva": "◆", "desconhecida": "⚠"}[kind]
            if kind == "desconhecida":
                target = esc(st["name"])
                extra = " — procura manualmente na arvore"
            else:
                r = st["ref"]
                origin = ""
                if kind == "passiva" and sec["matchedCode"] and r["heroDigit"] != sec["matchedCode"] // 100:
                    origin = " (" + data["heroes"].get(r["heroDigit"] * 100, "outro heroi") + ")"
                lvtxt = ""
                if st["lvl"] is not None:
                    lvtxt = f' → sobe até <b>{st["lvl"]}</b>/<b>{r["maxLevel"]}</b>'
                target = f'{esc(st["name"])}{lvtxt}{origin}'
                extra = (" — " + esc(st["note"])) if st["note"] else ""
            rows.append(
                f'<li><span class="badge">{num}</span>'
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

    warn = "" if all(s["kind"] != "desconhecida" for sec in matched for s in sec["steps"]) else \
        '<div class="warn">Algumas skills nao foram encontradas na arvore — ve os passos com ⚠</div>'

    notes_html = ""
    if build["notes"]:
        short = esc(build["notes"][:900]) + ("…" if len(build["notes"]) > 900 else "")
        notes_html = f'<details class="notes"><summary>Notas do autor da build</summary><p>{short.replace(chr(10), "<br>")}</p></details>'

    doc = rf"""<!DOCTYPE html>
<html lang="pt"><head><meta charset="utf-8">
<title>{esc(build["title"])}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:'Segoe UI',system-ui,sans-serif; background:#0e0c0a; color:#e8dcc0; overflow:hidden; }}
  header {{ padding:12px 26px; border-bottom:2px solid #7a6848; background:#1a1712; position:fixed; top:0; left:0; right:360px; z-index:5; }}
  h1 {{ margin:0; font-size:18px; color:#ffd86b; }}
  header .url {{ font-size:12px; color:#a89878; }}
  .treewrap {{ position:fixed; top:74px; left:0; right:360px; bottom:0; overflow:hidden; background:#0e0c0a; cursor:grab; }}
  .treewrap.drag {{ cursor:grabbing; }}
  .zoomer {{ transform-origin:0 0; width:max-content; }}
  svg.tree {{ display:block; }}
  .zonelabel {{ fill:#8a7a5a; font-size:26px; font-weight:800; letter-spacing:4px; }}
  .rowlabel {{ fill:#6b5f4a; font-size:17px; font-weight:800; }}
  .edge {{ stroke:#3f3626; stroke-width:3; }}
  .edgebridge {{ stroke:#57492f; stroke-width:3; stroke-dasharray:10 8; }}
  .routeline {{ fill:none; stroke:#ffd86b; stroke-width:4; opacity:0.95; stroke-linejoin:round; stroke-linecap:round; }}
  .sq {{ fill:#1d1913; stroke:#6b5a38; stroke-width:2; }}
  .sq.used {{ stroke:#ffd86b; stroke-width:3; fill:#2a2314; }}
  .sq.off {{ fill:#131009; stroke:#332b1e; }}
  .glow {{ fill:none; stroke:#ffd86b; stroke-width:2; opacity:0.35; }}
  .ringbadge {{ fill:#ffd86b; stroke:#141210; stroke-width:2; }}
  .under.on {{ fill:#f0e6cc; }}
  .under.off {{ fill:#6b5f4a; }}
  .under.gold {{ fill:#ffd86b; }}
  .q {{ fill:#a89878; font-size:22px; font-weight:800; text-anchor:middle; }}
  .stepnum {{ fill:#141210; font-size:13px; font-weight:800; text-anchor:middle; }}
  .steps {{ position:fixed; top:0; right:0; bottom:0; width:360px; background:#161310; border-left:2px solid #7a6848; padding:16px; overflow:auto; z-index:6; }}
  .steps h3 {{ color:#ffcc4d; margin:0 0 10px; font-size:14px; letter-spacing:2px; }}
  .steps ol {{ list-style:none; margin:0 0 6px; padding:0; display:flex; flex-direction:column; gap:8px; }}
  .steps li {{ display:flex; gap:7px; align-items:flex-start; font-size:13px; line-height:1.45; }}
  .badge {{ flex:0 0 24px; height:24px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; font-weight:800; color:#141210; background:#ffd86b; font-size:12.5px; margin-top:1px; }}
  .hchip {{ flex:0 0 auto; font-size:10px; font-weight:800; color:#0e0c0a; background:#a89878; border-radius:5px; padding:2px 5px; margin-top:3px; letter-spacing:1px; }}
  .kicon {{ flex:0 0 14px; text-align:center; }}
  .gear {{ margin-top:10px; font-size:11.5px; color:#c8b890; line-height:1.5; }}
  .ilink {{ color:#ffd86b; text-decoration:underline; }}
  .ilink:hover {{ color:#ffffff; }}
  .warn {{ background:#3a2020; border:1px solid #7a4040; color:#ffb0b0; padding:8px 12px; border-radius:8px; font-size:13px; margin:10px 16px; }}
  .notes {{ position:fixed; left:16px; bottom:12px; z-index:6; font-size:12px; color:#c8b890; max-width:520px; background:rgba(22,19,16,.92); border:1px solid #3a3226; border-radius:8px; padding:6px 12px; }}
  #zbtns {{ position:fixed; left:16px; bottom:64px; z-index:7; display:flex; gap:6px; }}
  #zbtns button {{ background:#1a1712; color:#ffd86b; border:1px solid #7a6848; border-radius:8px; padding:6px 12px; font-size:15px; cursor:pointer; }}
  #zbtns button:hover {{ background:#2a2317; }}
  .notes p {{ line-height:1.55; }}
  summary {{ cursor:pointer; color:#ffcc4d; }}
  #tabs {{ position:absolute; right:16px; top:12px; display:flex; gap:8px; }}
  #tabs button {{ background:#241f18; color:#ffd86b; border:1px solid #7a6848; border-radius:8px; padding:8px 14px; font-size:13px; font-weight:700; cursor:pointer; letter-spacing:1px; }}
  #tabs button.on {{ background:#ffd86b; color:#141210; }}
  .hidden {{ display:none !important; }}
  #rpanel {{ position:absolute; right:14px; top:14px; width:270px; background:rgba(22,19,16,.95); border:1px solid #7a6848; border-radius:10px; padding:12px; z-index:5; }}
  #rpanel h3 {{ margin:0 0 8px; font-size:13px; color:#ffd86b; letter-spacing:1px; }}
  #plist {{ list-style:none; margin:0 0 8px; padding:0; font-size:12px; display:flex; flex-direction:column; gap:5px; max-height:300px; overflow:auto; }}
  #plist li {{ display:flex; gap:6px; line-height:1.3; }}
  #plist .n {{ color:#ffd86b; font-weight:800; flex:0 0 20px; }}
  #ptotal {{ font-size:15px; font-weight:800; color:#ffd86b; margin:6px 0; }}
  #pclear {{ background:#3a2020; color:#ffb0b0; border:1px solid #7a4040; border-radius:8px; padding:6px 10px; cursor:pointer; font-size:12px; }}
  #phint {{ font-size:11px; color:#a89878; line-height:1.4; margin:8px 0 0; }}
  #idealinfo {{ font-size:11px; color:#9fdc9f; background:#16211a; border:1px solid #2f4a35; border-radius:8px; padding:6px 8px; margin-bottom:8px; line-height:1.4; }}
  #partinfo {{ font-size:12px; font-weight:800; color:#ffd86b; margin:2px 0 6px; }}
  #partbar {{ display:flex; gap:4px; flex-wrap:wrap; margin-bottom:8px; max-height:96px; overflow:auto; }}
  #partbar button {{ background:#241f18; color:#c8b890; border:1px solid #5a4e38; border-radius:6px; padding:4px 7px; font-size:10.5px; font-weight:700; cursor:pointer; }}
  #partbar button.on {{ background:#ffd86b; color:#141210; }}
  #presets {{ display:flex; gap:5px; align-items:center; margin-bottom:8px; font-size:11px; color:#a89878; flex-wrap:wrap; }}
  #presets button {{ background:#241f18; color:#ffd86b; border:1px solid #7a6848; border-radius:6px; padding:4px 8px; font-size:11px; font-weight:700; cursor:pointer; }}
  #presets button.hot {{ background:#ffd86b; color:#141210; }}
  #presets button:hover {{ background:#2a2317; }}
  #presets button.hot:hover {{ background:#ffe28a; }}
</style></head>
<body>
<header>
  <h1>{esc(build["title"])}</h1>
  <div class="url">{esc(build["url"])} — SKILLS: cada linha = um Tier pela ordem do jogo · dourado = comprar · RUNAS: clica no mapa para planeares a tua rota</div>
  <div id="tabs"><button id="tabS" class="on">SKILLS DO HEROI</button><button id="tabR">MAPA DE RUNAS</button></div>
</header>
<div class="treewrap" id="viewSkills"><div class="zoomer" id="skillsZoomer">{svg}</div></div>
<div class="treewrap hidden" id="viewRunes"><div class="zoomer" id="runesZoomer">{rsvg}</div>
    <div id="rpanel">
    <h3>A TUA ROTA DE RUNAS</h3>
    <div id="idealinfo">Rota IDEAL desta build auto-aplicada{(' — ' + esc(build.get("category", ""))) if build.get("category") else ''} · ajusta clicando nas runas</div>
    <div id="presets"><span>Rotas:</span><button data-g="ideal" class="hot">IDEAL DESTA BUILD</button><button data-g="farm">FARM / END GAME</button><button data-g="ouro">OURO</button><button data-g="exp">EXP</button><button data-g="combate">COMBATE</button></div>
    <div id="partinfo"></div>
    <div id="partbar"></div>
    <ol id="plist"></ol>
    <div id="ptotal"></div>
    <button id="pclear">Limpar rota</button>
    <p id="phint">A rota IDEAL equilibra progressao (waves, combate, exp, ouro) consoante as notas da build. Dividida em PARTES de 15 runas. Fica guardada no browser.</p>
  </div>
</div>
<aside class="steps" id="stepsSkills">
  <h3>PASSO A PASSO</h3>
  <ol>{''.join(rows)}</ol>
  {''.join(hero_blocks)}
</aside>
<aside class="steps hidden" id="stepsRunes">
  <h3>MAPA DE RUNAS</h3>
  <ol>
    <li>Este e o mapa completo das 241 runas globais (o mesmo do jogo, partilhado por todos os herois).</li>
    <li>CLICA nas runas pela ordem que queres comprar — o desenho liga-as com a linha dourada numerada.</li>
    <li>Hover mostra nome, max e custo total em ouro; o painel azul claro soma o total.</li>
    <li>Scroll = zoom · arrastar = mover · a rota fica guardada mesmo se fechares.</li>
  </ol>
</aside>
{warn}
{notes_html}
<div id="zbtns"><button id="zin">+</button><button id="zout">−</button><button id="zfit">⤢ ajustar</button></div>
<script>
function makeZoom(wrapId,mvId,MW,start){{
 const wrap=document.getElementById(wrapId),mv=document.getElementById(mvId);
 let scale=start,tx=20,ty=20,drag=null;
 function apply(){{mv.style.transform=`translate(${{tx}}px,${{ty}}px) scale(${{scale}})`;}}
 function zoom(f){{const r=wrap.getBoundingClientRect(),mx=r.width/2,my=r.height/2;tx=mx-(mx-tx)*f;ty=my-(my-ty)*f;scale*=f;apply();}}
 function fit(){{scale=Math.min(1,(wrap.clientWidth-20)/MW);tx=(wrap.clientWidth-MW*scale)/2;ty=14;apply();}}
 wrap.addEventListener('wheel',e=>{{e.preventDefault();const f=e.deltaY<0?1.15:1/1.15;
  const r=wrap.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
  tx=mx-(mx-tx)*f; ty=my-(my-ty)*f; scale*=f; apply();}},{{passive:false}});
 wrap.addEventListener('mousedown',e=>{{drag={{x:e.clientX,y:e.clientY,tx,ty}};wrap.classList.add('drag');}});
 window.addEventListener('mousemove',e=>{{if(!drag)return;tx=drag.tx+e.clientX-drag.x;ty=drag.ty+e.clientY-drag.y;apply();}});
 window.addEventListener('mouseup',()=>{{drag=null;wrap.classList.remove('drag');}});
 return {{apply,zoom,fit}};
}}
const zS=makeZoom('viewSkills','skillsZoomer',{W},0.7);
const zR=makeZoom('viewRunes','runesZoomer',{RW},0.5);
let tab='S';
function setTab(t){{
 tab=t;
 document.getElementById('viewSkills').classList.toggle('hidden',t!=='S');
 document.getElementById('stepsSkills').classList.toggle('hidden',t!=='S');
 document.getElementById('viewRunes').classList.toggle('hidden',t!=='R');
 document.getElementById('stepsRunes').classList.toggle('hidden',t!=='R');
 document.getElementById('tabS').classList.toggle('on',t==='S');
 document.getElementById('tabR').classList.toggle('on',t==='R');
 if(t==='R')zR.fit();
}}
document.getElementById('tabS').addEventListener('click',()=>setTab('S'));
document.getElementById('tabR').addEventListener('click',()=>setTab('R'));
document.getElementById('zin').addEventListener('click',()=>{{(tab==='S'?zS:zR).zoom(1.25)}});
document.getElementById('zout').addEventListener('click',()=>{{(tab==='S'?zS:zR).zoom(1/1.25)}});
document.getElementById('zfit').addEventListener('click',()=>{{(tab==='S'?zS:zR).fit()}});

const routeEl=document.getElementById('runeroute'),fullEl=document.getElementById('runefull'),badgeLayer=document.getElementById('badgeLayer'),plist=document.getElementById('plist'),ptotal=document.getElementById('ptotal');
let picked=[];try{{picked=JSON.parse(localStorage.getItem('tbh_rota')||'[]')}}catch(e){{}}
let part=0;const PER=15;
const centers={{}};
document.querySelectorAll('#viewRunes .node').forEach(g=>{{
 const m=g.getAttribute('transform').match(/translate\(([-\d.]+),([-\d.]+)\)/);
 centers[g.dataset.id]=[parseFloat(m[1])+32,parseFloat(m[2])+32];
 g.addEventListener('click',()=>toggle(g.dataset.id));
}});
function save(){{localStorage.setItem('tbh_rota',JSON.stringify(picked))}}
function toggle(id){{const i=picked.indexOf(id);if(i>=0)picked.splice(i,1);else picked.push(id);renderR();}}
function costOf(id){{
 const tEl=document.querySelector('#viewRunes .node[data-id="'+id+'"] title');
 const t=tEl?tEl.textContent.split('|'):['?','?','?','0'];
 return {{name:t[0].trim(),costTxt:t[3].trim(),num:parseFloat(t[3].replace(/[^\d]/g,''))||0}};
}}
function renderR(){{
 save();
 const n=Math.max(1,Math.ceil(picked.length/PER));
 if(part>=n)part=n-1;
 document.querySelectorAll('#viewRunes .node').forEach(g=>g.classList.toggle('sel',picked.includes(g.dataset.id)));
 const bar=document.getElementById('partbar');bar.innerHTML='';
 for(let i=0;i<n;i++){{
  const b=document.createElement('button');b.textContent='PARTE '+(i+1);
  if(i===part)b.classList.add('on');
  b.addEventListener('click',()=>{{part=i;renderR();}});
  bar.appendChild(b);
 }}
 document.getElementById('partinfo').textContent='Parte '+(part+1)+' de '+n+' — runas '+(picked.length?(part*PER+1)+' a '+Math.min(picked.length,(part+1)*PER):'0');
 const seg=picked.slice(part*PER,(part+1)*PER);
 let d='',dFull='',pTotal=0,tTotal=0;
 plist.innerHTML='';
 picked.forEach((id,i)=>{{
  const p=centers[id];if(!p)return;
  dFull+=(dFull?' L ':'M ')+p[0]+' '+p[1];
  tTotal+=costOf(id).num;
 }});
 seg.forEach((id,i)=>{{
  const p=centers[id];if(!p)return;
  d+=(i?' L ':'M ')+p[0]+' '+p[1];
  const c=costOf(id);
  const li=document.createElement('li');li.innerHTML='<span class="n">'+(i+1)+'</span><span>'+c.name+' — '+c.costTxt+'</span>';plist.appendChild(li);
  pTotal+=c.num;
 }});
 routeEl.setAttribute('d',d);
 fullEl.setAttribute('d',dFull);
 badgeLayer.innerHTML='';
 seg.forEach((id,i)=>{{
  const p=centers[id];if(!p)return;
  const c=document.createElementNS('http://www.w3.org/2000/svg','circle');
  c.setAttribute('cx',p[0]);c.setAttribute('cy',p[1]);c.setAttribute('r',14);c.setAttribute('class','ringbadge');
  const t=document.createElementNS('http://www.w3.org/2000/svg','text');
  t.setAttribute('x',p[0]);t.setAttribute('y',p[1]+5);t.setAttribute('class','stepnum');t.textContent=i+1;
  badgeLayer.appendChild(c);badgeLayer.appendChild(t);
 }});
 ptotal.innerHTML='Parte: <b>'+pTotal.toLocaleString('pt-PT')+'</b> ouro · Rota total: <b>'+tTotal.toLocaleString('pt-PT')+'</b> ouro';
}}
document.getElementById('pclear').addEventListener('click',()=>{{picked=[];part=0;renderR();}});
const PRESETS={presets_json};
document.querySelectorAll('#presets button').forEach(b=>b.addEventListener('click',()=>{{picked=(PRESETS[b.dataset.g]||[]).map(String);part=0;renderR();}}));
picked=(PRESETS.ideal&&PRESETS.ideal.length?PRESETS.ideal:(PRESETS.farm||[])).map(String);
part=0;renderR();
</script>
</body></html>"""
    return doc


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:60] or "build"


def main():
    HERO_ICONS.update(load_hero_icons())
    ensure_data_files()
    data = load_game_data()

    urls = [a if a.startswith("http") else "https://" + a for a in sys.argv[1:]]
    if not urls:
        print("Cola o(s) link(s) da build (Enter vazio para sair):")
        while True:
            u = input("> ").strip()
            if not u:
                break
            if not u.startswith("http"):
                u = "https://" + u
            urls.append(u)

    for url in urls:
        try:
            build = fetch_build(url)
            mp = tm.ensure_map()
            runes = tm.load_runes()
            costs = tm.load_costs()
            presets = compute_route_presets(mp, runes, costs)
            presets["ideal"] = compute_ideal_route(mp, runes, costs, build.get("category", ""), build.get("notes", ""))
            runedata = (mp, runes, costs, presets)
            out = render_html(build, data, runedata)
            fname = "arvore_" + slugify(build["title"]) + ".html"
            with open(os.path.join(ROOT, fname), "w", encoding="utf-8") as f:
                f.write(out)
            print("OK: " + fname)
            try:
                os.startfile(os.path.join(ROOT, fname))
            except Exception:
                pass
        except Exception as e:
            print(f"Erro em {url}: {e}")


if __name__ == "__main__":
    main()
