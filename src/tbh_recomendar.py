"""
MOTOR DE RECOMENDACOES em tempo real (por conta, a partir do save local).

Para cada conta responde: "o que upar AGORA?"
  - pontos de habilidade livres por gastar
  - skills/passivas do heroi principal que ainda nao estao no maximo
  - proximas runas do caminho ideal (rota ouro/farm) que ainda nao tens
  - quanto ouro tens vs. quanto custa o proximo upgrade
  - distancia ate ao objetivo endgame (23-20 Plague)

Usado pelo tbh_baus.render_section: cada cartao de conta ganha um chip
notif clickable com o painel de recomendações (HTML/CSS puro, sem JS).
Nao depende da API do site — le os saves diretos, por isso e "tempo real"
a cada ciclo do monitor.
"""
import os
import re
import json

from tbh_inventario import _es3_decrypt, _save_legivel, HERO_NOMES, esc as _esc

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

# ---------------------------------------------------------------- dados do jogo (carregados 1x)

_D = None


def _dados() -> dict:
    """{data: arvore, mp: mapa de runas, runes: nomes, costs: custos, presets: rotas, meta}"""
    global _D
    if _D:
        return _D
    import tbh_arvore as ta
    import tbh_mapa as tm

    data = ta.load_game_data()
    mp = tm.ensure_map()
    runes = tm.load_runes()
    costs = tm.load_costs()
    presets = ta.compute_route_presets(mp, runes, costs)

    # nomes PT (mesmos mapas do site)
    pt_at, pt_st = {}, {}
    try:
        import tbh_site as ts
        pt_at, pt_st = ts.PT_ATIVAS, ts.PT_STATS
    except Exception:
        pass
    for aid, a in data["actives"].items():
        a["pt"] = pt_at.get(aid, a["name"])
    for pid, p in data["passives"].items():
        p["pt"] = pt_st.get(pid, p["label"])

    _D = {"data": data, "mp": mp, "runes": runes, "costs": costs, "presets": presets}
    return _D


def _init():
    return _dados()


# ---------------------------------------------------------------- leitura do save

def ler_save(save_path: str) -> dict:
    """Campos de progressao do save. Nunca lanca."""
    try:
        p = _es3_decrypt(_save_legivel(save_path))
    except Exception:
        return {}
    herois = []
    for h in p.get("heroSaveDatas") or []:
        if not h.get("IsUnLock"):
            continue
        herois.append({
            "key": h.get("heroKey"),
            "lvl": int(h.get("HeroLevel") or 0),
            "pontos": int(h.get("AbilityPoint") or 0),
            "grupos": len(h.get("unlockedAttributeGroupKeys") or []),
        })
    herois.sort(key=lambda x: -x["lvl"])
    attrs = {}
    for a in p.get("attributeSaveDatas") or []:
        try:
            if a.get("Level"):
                attrs[int(a["Key"])] = int(a["Level"])
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
            ouro = int(c.get("Quantity") or 0)
    return {"herois": herois, "attrs": attrs, "runas": runas, "ouro": ouro,
            "stage_key": (p.get("commonSaveData") or {}).get("currentStageKey"),
            "max_key": (p.get("commonSaveData") or {}).get("maxCompletedStage")}


# ---------------------------------------------------------------- goal endgame

def _passos_ate_goal(stage_key) -> int:
    """Passos na cadeia 'next' do mapa ate 23-20 Plague (-1 = nao sei)."""
    d = _dados()
    stages = d.get("_stages")
    if stages is None:
        stages = {}
        try:
            f = os.path.join(ROOT, "data", "tbhdata", "tbhStages.js")
            if not os.path.exists(f):
                for _alt in [os.path.join(ROOT, "tbhdata", "tbhStages.js"), os.path.join(BASE, "tbhdata", "tbhStages.js")]:
                    if os.path.exists(_alt): f = _alt; break
            m = re.search(r"JSON\.parse\(`(\{.*?\})`\)",
                          open(f, encoding="utf-8", errors="replace").read(), re.S)
            for s in json.loads(m.group(1)).get("stages", []):
                stages[int(s["key"])] = s
        except Exception:
            pass
        d["_stages"] = stages
    goal = None
    for s in stages.values():
        if s.get("type") == "PLAGUE" and s.get("act") == 23 and s.get("no") == 20:
            goal = int(s["key"])
            break
    if not goal:
        return -1
    try:
        cur = int(stage_key or 0)
    except Exception:
        return -1
    if not cur or cur not in stages:
        return -1
    n, seen = 0, set()
    while cur and cur != goal and cur not in seen and n < 500:
        seen.add(cur)
        cur = stages.get(cur, {}).get("next")
        cur = int(cur) if cur else 0
        n += 1
    return n if cur == goal else -1


# ---------------------------------------------------------------- recomendações

def _fmt_ouro(v: int) -> str:
    if v >= 1_000_000:
        s = "{:,.1f}".format(v / 1_000_000).replace(",", "§").replace(".", ",").replace("§", ".")
        return s + "M"
    if v >= 1_000:
        return "{:,}".format(v // 1000).replace(",", ".") + "k"
    return str(v)


def recomendar(save_path: str, nome_conta: str = "", alvos_build: dict = None) -> dict:
    """Devolve {alertas, chip, resumo} ou {} se nao conseguir ler.
    alvos_build: {'skills': {id: nivel_alvo}} da build perfeita da conta — se vier, o UPAR JÁ mostra só o que falta dessa build.
    As linhas de skill/runa levam data-attrs para a dashboard torná-las clicáveis
    (abre a build da conta e faz zoom no item)."""
    d = _dados()
    sv = ler_save(save_path)
    if not sv or not sv["herois"]:
        return {}
    main = sv["herois"][0]
    hcode = main["key"]
    hnome = HERO_NOMES.get(hcode, "Herói " + str(hcode))
    dca = ' data-conta="' + _esc(nome_conta) + '"' if nome_conta else ""

    alertas = 0
    linhas_up = []
    # 1) pontos livres
    pts_livres = sum(h.get("pontos", 0) for h in sv["herois"])
    if pts_livres > 0:
        alertas += 1
        linhas_up.append('<div class="rec-line hot">⚠ <b>' + str(pts_livres)
                         + (' pontos' if pts_livres != 1 else ' ponto')
                         + ' de habilidade livres</b> — gastá-los é sempre o primeiro passo</div>')
    # 2) skills/passivas: se houver alvos da build perfeita, mostrar só o que falta dessa build; senão genérico
    alvos_sk = (alvos_build or {}).get("skills") or {}
    # normaliza chaves para int
    try:
        alvos_sk = {int(k): int(v) for k, v in alvos_sk.items()}
    except Exception:
        alvos_sk = {}
    minhas = []
    if alvos_sk:
        for k, alvo in alvos_sk.items():
            lv = sv["attrs"].get(k, 0)
            if lv >= alvo:
                continue
            info = None
            if k >= 100000:
                info = d["data"]["passives"].get(k)
            else:
                info = d["data"]["actives"].get(k)
            if not info:
                continue
            minhas.append((k, lv, info, alvo))
        # ordena por progresso relativo ao ALVO da build
        minhas.sort(key=lambda x: -(x[1] / max(1, x[3])))
        prontas = len(minhas)
        for k, lv, info, alvo in minhas[:5]:
            alertas += 1
            nome = info.get("pt") or info.get("name") or info.get("label") or str(k)
            falta = alvo - lv
            linhas_up.append('<div class="rec-line go"' + dca + ' data-skill="' + str(k) + '" onclick="window.recGo&&recGo(this)">→ <b>' + str(nome) + "</b> "
                             + str(lv) + "→" + str(alvo)
                             + ("/" + str(info.get("maxLevel", alvo)) if info.get("maxLevel", alvo) != alvo else "")
                             + ' <span class="rec-dim">(falta ' + str(falta) + ")</span></div>")
    else:
        digit = hcode // 100
        minhas2 = []
        for k, lv in sv["attrs"].items():
            info = None
            if k >= 100000 and k // 100000 == digit:
                info = d["data"]["passives"].get(k)
            elif 10000 <= k < 100000 and k // 10000 == digit:
                info = d["data"]["actives"].get(k)
            if info and lv < info.get("maxLevel", 1):
                minhas2.append((k, lv, info))
        minhas2.sort(key=lambda x: -(x[1] / max(1, x[2].get("maxLevel", 1))))
        prontas = len(minhas2)
        minhas = [(k, lv, info, info.get("maxLevel", 1)) for k, lv, info in minhas2]
        for k, lv, info in minhas2[:3]:
            alertas += 1
            nome = info.get("pt") or info.get("name") or info.get("label") or str(k)
            falta = info["maxLevel"] - lv
            linhas_up.append('<div class="rec-line go"' + dca + ' data-skill="' + str(k) + '" onclick="window.recGo&&recGo(this)">→ <b>' + str(nome) + "</b> "
                             + str(lv) + "→" + str(info["maxLevel"])
                             + ' <span class="rec-dim">(falta ' + str(falta) + ")</span></div>")
    # 2b) proximo desbloqueio da arvore (grupos desbloqueados = tiers abertos)
    tree = d["data"]["trees"].get(hcode) or {}
    tiers = tree.get("tiers") or []
    if 0 < main.get("grupos", 0) < len(tiers):
        t = tiers[main["grupos"]]
        nomes = []
        for aid in (t.get("actives") or []):
            info = d["data"]["actives"].get(aid)
            if info:
                nomes.append(str(info.get("pt") or info.get("name") or aid))
        for pid in (t.get("passives") or []):
            info = d["data"]["passives"].get(pid)
            if info:
                nomes.append(str(info.get("pt") or info.get("label") or pid))
        if nomes and main.get("lvl", 0) < 70:
            alertas += 1
            primeiro_id = (t.get("actives") or t.get("passives") or [None])[0]
            ds = (' data-skill="' + str(primeiro_id) + '"' + dca + ' onclick="window.recGo&&recGo(this)"') if primeiro_id else ""
            linhas_up.append('<div class="rec-line go"' + ds + '>→ a seguir na árvore: <b>'
                             + _esc(" + ".join(nomes[:3])) + "</b> (sobe de nível para desbloquear)</div>")
    if not linhas_up:
        linhas_up.append('<div class="rec-line ok">✓ tudo no máximo neste herói — a focar runas!</div>')

    # 3) próximas runas: se houver rota da BUILD perfeita usa essa; senão late-genérica
    rota = ((alvos_build or {}).get("runas") or [])
    if rota:
        # rota da build já é a ideal dessa build — mantém ordem, filtra só o que já compraste
        pass
    else:
        rota = _rota_late(d)
    owned = sv["runas"]
    nos_mapa = {int(k) for k in d["mp"]["nodes"]}
    compraveis = [n for n in rota if int(n) in owned and owned[int(n)] == 0]
    futuras = [n for n in rota if int(n) not in owned]
    n_runa = len([k for k, v in owned.items() if v > 0 and int(k) in nos_mapa])
    tot_mapa = len(nos_mapa)
    linhas_r = []
    custo_prox = 0
    vistos = []  # [label, n, primeiro_nid_do_grupo, lock]
    for nid in compraveis[:5]:
        info = d["runes"].get(int(nid), {})
        custo_prox += d["costs"].get(int(nid), {}).get("total", 0)
        lab = str(info.get("label", "?"))
        if vistos and vistos[-1][0] == lab and not vistos[-1][3]:
            vistos[-1][1] += 1
        else:
            vistos.append([lab, 1, nid, False])
    for nid in futuras[:2]:
        info = d["runes"].get(int(nid), {})
        vistos.append([str(info.get("label", "?")), 1, nid, True])
    for lab, n, nid_grupo, lock in vistos:
        nm = ("🔒 " if lock else "") + lab + (" ×" + str(n) if n > 1 else "")
        dr = ' data-runa="' + str(nid_grupo) + '"' + dca
        if lock:
            linhas_r.append('<div class="rec-line dim"' + dr + '>→ 🔒 <b>' + str(nm)
                            + "</b> <span class=\"rec-dim\">(ainda não alcançada)</span></div>")
        else:
            linhas_r.append('<div class="rec-line go"' + dr + ' onclick="window.recGo&&recGo(this)">→ <b>' + str(nm) + "</b></div>")
    if compraveis or futuras:
        linhas_r.append('<div class="rec-line dim">' + str(len(compraveis)) + " compráveis agora (já alcançadas) · "
                        + str(len(futuras)) + " ainda por alcançar · as próximas custam ≈<b>"
                        + _fmt_ouro(custo_prox) + "</b> ouro</div>")
    else:
        linhas_r.append('<div class="rec-line ok">✓ rota completa — lenda!</div>')

    # 4) ouro e meta
    ouro = sv["ouro"]
    meta = ""
    passos = _passos_ate_goal(sv.get("stage_key"))
    if passos >= 0:
        meta = 'faltam <b>~' + str(passos) + '</b> estágios até <b>23-20 Plague</b> (a build 23-20)'

    sec_up = '<h4>⚡ UPAR JÁ — ' + str(hnome) + ' nv ' + str(main["lvl"]) + "</h4>" + "".join(linhas_up)
    sec_r = '<h4>🔷 PRÓXIMAS RUNAS <span class="rec-dim">(' + str(n_runa) + "/" + str(tot_mapa) + ' no mapa)</span></h4>' + "".join(linhas_r)
    sec_m = '<h4>🎯 AGORA</h4><div class="rec-line">ouro: <b>' + _fmt_ouro(ouro) + "</b>" + (" · " + meta if meta else "") + "</div>" \
        + '<div class="rec-dim rec-dica">💡 clica nas linhas para ver no mapa de runas / árvore de skills da build da conta</div>'
    if prontas:
        resumo = str(prontas) + " skills prontas · " + str(len(compraveis) + len(futuras)) + " runas em fila"
    else:
        resumo = str(len(compraveis) + len(futuras)) + " runas em fila"

    chip = '<details class="recbox" onclick="event.stopPropagation()"><summary class="recchip">🔔 ' \
           + (str(alertas) if alertas else "✓") + "</summary>" \
           + '<div class="recpanel">' + sec_up + sec_r + sec_m + "</div></details>"
    return {"alertas": alertas, "chip": chip, "resumo": resumo,
            "pontos": pts_livres, "skills": prontas, "runas_faltam": len(compraveis) + len(futuras)}


def _rota_late(d: dict) -> list:
    """Rota de runas focada em CHEGAR AO LATE-GAME o mais rapido possivel:
    waves (matar mais rapido) -> exp (subir de nivel desbloqueia a arvore)
    -> skill slots -> move speed -> dano (bosses) -> ouro -> QoL -> resto."""
    if d.get("_late"):
        return d["_late"]
    import tbh_arvore as ta
    mp, runes, costs = d["mp"], d["runes"], d["costs"]
    nodes = {int(k) for k in mp["nodes"]}
    root = 1 if 1 in nodes else min(nodes)

    def stat(nid):
        return runes.get(nid, {}).get("stat", "").lower()

    def custo(nid):
        return costs.get(nid, {}).get("total", 10 ** 9)

    def ordered(preds):
        out, done = [], {root}
        for pred in preds:
            tg = [n for n in nodes if n not in done and pred(stat(n))]
            tg.sort(key=custo)
            for n in tg:
                out.append(n)
                done.add(n)
        return out

    rota = ta.walk_route(mp, root, ordered([
        lambda s: "wave" in s,
        lambda s: "exp" in s,
        lambda s: "skill slot" in s,
        lambda s: "move speed" in s,
        lambda s: "attack" in s or "damage" in s or "crit" in s,
        lambda s: "gold" in s,
        lambda s: "drop chance" in s or "auto" in s or "stash" in s or "inventory" in s,
        lambda s: True,
    ]))
    d["_late"] = rota
    return rota


def plano_completo(save_path: str, alvos_build: dict = None) -> dict:
    """Plano completo de upgrades para a aba 'UPAR JÁ' da build da conta.
    alvos_build: {'skills': {id: nivel_alvo}, 'runas': [nids em ordem]} (da build atribuída).
    Devolve {'skills': [...], 'runas': [...], 'resumo': str} ou {}.
    Skills: {id, nome, atual, alvo, max, tier, fila, row_y, col_x}
    Runas:  {id, nome, prof, col, row_y, col_x, custo, owned}
    Posições calculadas pela mesma matemática do render da árvore/mapa:
      skills: y=130+ti*128+64 (centro do nó), x=90+k*78+64 (k=índice no tier)
      runas:  y = maxy - node_y, x = node_x - minx (mesma conversão do build_runes_svg)
    """
    d = _dados()
    sv = ler_save(save_path)
    if not sv or not sv["herois"]:
        return {}
    main = sv["herois"][0]
    hcode = main["key"]
    digit = hcode // 100
    alvos = (alvos_build or {}).get("skills") or {}

    # TODOS os herois desbloqueados (a build e a conta tem equipa, nao um heroi so)
    # alvos da build separados por heroi (passivas 6-digit, ativas 5-digit)
    def _alvos_do_heroi(h):
        dig = h // 100
        out = {}
        for k, v in alvos.items():
            try:
                kid = int(k)
            except Exception:
                continue
            hero = kid // 100000 if kid >= 100000 else kid // 10000
            if hero == dig:
                out[kid] = int(v)
        return out

    ordem_map = (alvos_build or {}).get("ordem") or {}
    skills = []
    feitos = []

    def _regista(hnome_h, ti, k, pid, info, atual, alvo):
        item = {
            "id": pid, "nome": str(info.get("pt") or info.get("name") or info.get("label") or pid),
            "heroi": hnome_h,
            "atual": atual, "alvo": alvo, "max": info.get("maxLevel", 1),
            "tier": ti, "fila": k + 1,
            "row_y": 130 + ti * 128 + 64, "col_x": 90 + k * 78 + 64,
            "ordem": ordem_map.get(str(pid), 10 ** 6),
        }
        if atual >= alvo:
            feitos.append(item)  # ja atingido — nunca aparece como "por fazer"
        else:
            skills.append(item)

    for hero in sv["herois"]:
        h = hero["key"]
        hnome_h = HERO_NOMES.get(h, "Herói " + str(h))
        alvos_h = _alvos_do_heroi(h)
        tree = d["data"]["trees"].get(h) or {}
        grupos = hero.get("grupos", 0)
        for ti, tier in enumerate(tree.get("tiers") or []):
            slots = []
            if tier.get("passives"):
                slots.extend(tier["passives"][:2])
            slots.extend(tier.get("actives") or [])
            for k, pid in enumerate(slots):
                info = (d["data"]["passives"].get(pid) if pid >= 100000 else d["data"]["actives"].get(pid))
                if not info:
                    continue
                atual = sv["attrs"].get(pid, 0)
                if alvos_h:
                    # a build define o que interessa: so skills DA BUILD, com o alvo DELA
                    if pid not in alvos_h:
                        continue
                    alvo = alvos_h[pid]
                    if alvo <= 0:
                        continue
                else:
                    # sem alvos desta build: so o que ja esta desbloqueado, ate ao max
                    if ti > grupos:
                        continue
                    alvo = info.get("maxLevel", 1)
                _regista(hnome_h, ti, k, pid, info, atual, alvo)

    # herois da build que a conta ainda NAO tem (builds que trocam de heroi/especializacao):
    # entram no plano como "por fazer" — nao ficam esquecidos
    if alvos:
        _save_keys = {hero["key"] for hero in sv["herois"]}
        for h, tree in (d["data"]["trees"] or {}).items():
            if h in _save_keys:
                continue
            alvos_h = _alvos_do_heroi(h)
            if not alvos_h:
                continue
            hnome_h = HERO_NOMES.get(h, "Herói " + str(h)) + " (por desbloquear)"
            for ti, tier in enumerate(tree.get("tiers") or []):
                slots = []
                if tier.get("passives"):
                    slots.extend(tier["passives"][:2])
                slots.extend(tier.get("actives") or [])
                for k, pid in enumerate(slots):
                    if pid not in alvos_h:
                        continue
                    alvo = alvos_h[pid]
                    if alvo <= 0:
                        continue
                    info = (d["data"]["passives"].get(pid) if pid >= 100000 else d["data"]["actives"].get(pid))
                    if not info:
                        continue
                    _regista(hnome_h, ti, k, pid, info, sv["attrs"].get(pid, 0), alvo)

    # ORDEM DA BUILD (a ordem do guia manda) — desempate por tier/fila
    skills.sort(key=lambda s: (s.get("ordem", 10 ** 6), s["tier"], s["fila"]))
    feitos.sort(key=lambda s: (s.get("ordem", 10 ** 6), s["tier"], s["fila"]))

    runas = []
    runas_feitas = 0
    rota = (alvos_build or {}).get("runas") or _rota_late(d)
    # rota COMPLETA desta build, pela ordem certa — sem saltar nenhuma runa nem passos
    nodes = d["mp"]["nodes"]
    xs = [v[0] for v in nodes.values()]
    ys = [v[1] for v in nodes.values()]
    pad = 90
    minx, maxy = min(xs) - pad, max(ys) + pad
    for ordem, nid in enumerate(rota, 1):
        nid = int(nid)
        info = d["runes"].get(nid, {})
        nx, ny = nodes.get(str(nid), (0, 0))
        estado = ("feito" if sv["runas"].get(nid, 0) > 0 else ("comprar" if nid in sv["runas"] else "lock"))
        if estado == "feito":
            runas_feitas += 1
        runas.append({
            "id": nid, "nome": str(info.get("label", "?")),
            "ordem": ordem, "total": len(rota),
            "custo": d["costs"].get(nid, {}).get("total", 0),
            "estado": estado, "owned": 1 if estado == "feito" else 0,
            "lock": estado == "lock",
            "row_y": maxy - ny, "col_x": nx - minx,
        })
    resumo = (str(len(skills)) + " skills por fazer · " + str(len(feitos)) + " feitas · "
              + str(len(rota) - runas_feitas) + " runas pela frente")
    return {"skills": skills, "feitos": feitos, "runas": runas, "resumo": resumo}


def aba_up_html(plano: dict, nome_conta: str = "") -> str:
    """Conteudo da aba 'UPAR JÁ': ✓ JÁ FEITO vs ⚡ POR FAZER, pela ORDEM DA BUILD.
    As linhas sao clicáveis e saltam para a posição na árvore/mapa."""
    dca = ' data-conta="' + _esc(nome_conta) + '"' if nome_conta else ""
    if not plano:
        return '<p class="rec-dim">Sem plano (save não encontrado ou tudo feito).</p>'
    hint = (
        '<div class="upHint"><b>COMO USAR ESTE PLANO (passo a passo)</b><br>'
        '1️⃣ <b>✓ JÁ FEITO</b> — já está feito, podes ignorar (não percas tempo).<br>'
        '2️⃣ <b>⚡ POR FAZER</b> — faz <u>por ordem de cima para baixo</u>: 1., depois 2., depois 3… '
        'sobe a skill ao nível indicado e só depois passa à seguinte.<br>'
        '3️⃣ <b>🔷 RUNAS</b> — compra sempre a próxima da lista (#1, #2, #3…) — <u>nunca saltes passos</u>. '
        '🔒 = ainda não consegues comprar (mais à frente).<br>'
        '4️⃣ Clica em qualquer linha para saltar logo para a skill / runa no mapa.<br>'
        '⚠️ Siga <b>esta</b> build — cada página de build tem o SEU plano (não mistures com outras builds).</div>'
    )
    linhas = []
    ft = plano.get("feitos") or []
    sk = plano.get("skills") or []
    if ft:
        linhas.append('<details class="updet"><summary class="upsec upsec-feito">✓ JÁ FEITO (' + str(len(ft)) + ')</summary>')
        for s in ft:
            pos = "T" + str(s["tier"] + 1) + " · fila " + str(s["fila"])
            extra = ' <span class="rec-dim">(tens ' + str(s["atual"]) + ')</span>' if s["atual"] > s["alvo"] else ""
            linhas.append(
                '<div class="upline done"><span>✓ <b>' + _esc(s["heroi"]) + "</b> · " + _esc(s["nome"])
                + " — feito (alvo " + str(s["alvo"]) + ")" + extra + "</span>"
                '<span class="uppos">árvore: ' + pos + "</span></div>")
        linhas.append("</details>")
    if sk:
        linhas.append('<div class="upsec">⚡ POR FAZER — PELA ORDEM DA BUILD</div>')
        for i, s in enumerate(sk, 1):
            pos = "T" + str(s["tier"] + 1) + " · fila " + str(s["fila"])
            if s["alvo"] < s["max"]:
                alvo = "até <b>" + str(s["alvo"]) + "</b>/" + str(s["max"])
            else:
                alvo = "até <b>" + str(s["max"]) + "</b> (max)"
            linhas.append(
                '<div class="upline go"' + dca + ' data-skill="' + str(s["id"]) + '" onclick="window.recGo&&recGo(this)">'
                "<span>" + str(i) + ". → <b>" + _esc(s["heroi"]) + "</b> · " + _esc(s["nome"]) + " " + str(s["atual"]) + "→ " + alvo + "</span>"
                '<span class="uppos">árvore: ' + pos + "</span></div>")
    else:
        linhas.append('<p class="updone">✓ Skills todas no alvo desta build!</p>')
    rn = plano.get("runas") or []
    rn_feitas = [r for r in rn if r.get("estado") == "feito"]
    rn_pend = [r for r in rn if r.get("estado") != "feito"]
    if rn:
        linhas.append('<div class="upsec">🔷 RUNAS — ROTA DESTA BUILD (sem saltar passos)</div>')
        if rn_feitas:
            linhas.append('<details class="updet"><summary class="upsec upsec-feito">✓ ' + str(len(rn_feitas)) + ' runas já feitas</summary>')
            for r in rn_feitas:
                pos = "col " + str(int(r["col_x"] // 72 + 1)) + " · linha " + str(int(r["row_y"] // 72 + 1))
                linhas.append(
                    '<div class="upline done"><span>✓ <b>' + _esc(r["nome"]) + "</b> #" + str(r["ordem"]) + "/" + str(r.get("total", "?")) + "</span>"
                    '<span class="uppos">mapa: ' + pos + "</span></div>")
            linhas.append("</details>")
        for r in rn_pend:
            pos = "col " + str(int(r["col_x"] // 72 + 1)) + " · linha " + str(int(r["row_y"] // 72 + 1))
            if r.get("lock"):
                linhas.append(
                    '<div class="upline dim"' + dca + ' data-runa="' + str(r["id"]) + '">'
                    '<span>🔒 <b>' + _esc(r["nome"]) + "</b> #" + str(r["ordem"]) + "/" + str(r.get("total", "?")) + "</span>"
                    '<span class="uppos">ainda não alcançada · mapa: ' + pos + "</span></div>")
            else:
                linhas.append(
                    '<div class="upline go"' + dca + ' data-runa="' + str(r["id"]) + '" onclick="window.recGo&&recGo(this)">'
                    '<span>→ <b>' + _esc(r["nome"]) + "</b> #" + str(r["ordem"]) + "/" + str(r.get("total", "?")) + ' <span class="rec-dim">(≈' + _fmt_ouro(r["custo"]) + " ouro)</span></span>"
                    '<span class="uppos">mapa: ' + pos + "</span></div>")
    if not linhas:
        return '<p class="updone">✓ Tudo no máximo — esta conta já atingiu o plano desta build!</p>'
    linhas.insert(0, hint)
    return "".join(linhas)


ALVOS_CACHE = os.path.join(ROOT, "data", "tbhdata", "alvos_builds.json")
if not os.path.exists(ALVOS_CACHE):
    for _alt in [os.path.join(ROOT, "tbhdata", "alvos_builds.json"), os.path.join(BASE, "tbhdata", "alvos_builds.json")]:
        if os.path.exists(_alt): ALVOS_CACHE = _alt; break


def _alvos_cache_load() -> dict:
    try:
        return json.load(open(ALVOS_CACHE, encoding="utf-8-sig"))
    except Exception:
        return {}


def _alvos_cache_save(d: dict) -> None:
    try:
        with open(ALVOS_CACHE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def chip_conta(save_path: str, nome_conta: str = "") -> str:
    """Chip-clickable para meter no cartao da conta ('' se nada a mostrar)."""
    try:
        alvos = None
        try:
            cache = _alvos_cache_load()
            for v in cache.values():
                if (v.get("conta") or "") == nome_conta and v.get("alvos"):
                    alvos = v.get("alvos")
                    break
        except Exception:
            pass
        return recomendar(save_path, nome_conta, alvos).get("chip", "")
    except Exception:
        return ""


def ligar_builds(doc: str, urls: list) -> str:
    """Injecta data-build="<indice>" nas linhas .rec-line.go/upline.go com data-conta,
    mapeando a conta -> build (sufixo |user=Nome da Conta no builds.json).
    Usado pelo tbh_site.py (geracao completa) e tbh_baus.atualizar_secao."""
    try:
        mapa = {}
        for j, u in enumerate(urls):
            partes = str(u).split("|user=")
            if len(partes) == 2:
                chave = partes[1].split("|")[0].strip()
                if chave:
                    mapa.setdefault(chave, j)
        n = [0]

        def _marca(mo):
            n[0] += 1
            acc = mo.group(0)
            conta = (mo.group(1) or "").strip()
            bidx = mapa.get(conta)
            if bidx is None:
                return acc
            return acc[:-1] + ' data-build="' + str(bidx) + '">'

        return re.sub(r'class="(?:rec-line|upline) go"[^>]*data-conta="([^"]*)"[^>]*>', _marca, doc)
    except Exception:
        return doc
