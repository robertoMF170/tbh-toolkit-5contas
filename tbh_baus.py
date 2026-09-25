r"""MEUS BAUS - valor REAL vendavel (Steam Market) das contas de Task Bar Hero.

Pesquisa extensa (24/09/2026): dos 8.213 itens da API so ~1.060 tem oferta de
venda ATIVA (lowest_sell_order != null). O resto (Common/Uncommon, Deleted,
sem vendedor, nivel >90, nm) nao vale nada para venda imediata e NAO conta
para o TOTAL do bau. Este modulo passa a mostrar SÓ o vendavel - igual ao
inventario.html - usando o save local + API de mercado. Antes contava tudo
e inflava o valor.

Fonte: API publica do tbhindex.com (os mesmos numeros que o site mostra).
  - /api/profile/resolve/<nick-ou-steamid>  -> steam id
  - /api/ranking/live/player/<steam_id>     -> baú, heróis equipados, rank...
  - /api/items                               -> preco vendavel (sell ativo)
  + save local SaveFile_Live.es3 (via tbh_inventario) -> verdade vendavel
Os valores brutos da API estão em USD; converte-se para a moeda configurada
com a mesma fonte de câmbio que o site usa (open.er-api.com).

A conta só aparece na API DEPOIS de importares o save dela em
tbhindex.com ("Inspecionar Seu Baú"). Cada save = 1 conta Steam = 1 perfil.
Mas o valor VENDÁVEL verdadeiro vem do save local (tbh_inventario.py).

Config: baus.json  {"moeda": "EUR", "contas": [{"nome": "...", "id": "...", "save": "..."}]}
CLI:   python tbh_baus.py --add NICK_OU_STEAMID [--nome ROTULO]
       python tbh_baus.py --rm NICK_OU_STEAMID
       python tbh_baus.py --moeda BRL
       python tbh_baus.py --list
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_FILE = os.path.join(BASE, "baus.json")
CACHE_FILE = os.path.join(BASE, "baus_cache.json")

API = "https://api.tbhindex.com/api"
FX_URL = "https://open.er-api.com/v6/latest/USD"
FX_TTL = 6 * 3600  # câmbio em cache 6h
SIMBOLOS = {"EUR": "€", "USD": "$", "BRL": "R$", "GBP": "£", "JPY": "¥"}
HIST_FILE = os.path.join(BASE, "baus_historico.json")
HIST_PONTO_MIN = 5 * 60  # mínimo entre pontos gravados (segundos)
ALERTAS_FILE = os.path.join(BASE, "alertas_dedup.json")
TEMP_DIAS = {0.2: "6h", 1.0: "1 dia", 7.0: "1 semana", 1000000.0: "tudo"}  # janelas do gráfico


def _get_json(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": "tbh-minhas-builds/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ---------------------------------------------------------------- config

def load_cfg() -> dict:
    if os.path.exists(CFG_FILE):
        try:
            return json.load(open(CFG_FILE, encoding="utf-8-sig"))
        except Exception:
            pass
    return {"moeda": "EUR", "contas": []}


def save_cfg(cfg: dict) -> None:
    with open(CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- cache

def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            return json.load(open(CACHE_FILE, encoding="utf-8-sig"))
        except Exception:
            pass
    return {}


def save_cache(c: dict) -> None:
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1, ensure_ascii=False)


# ---------------------------------------------------------------- histórico

def hist_load() -> list:
    """Lista de pontos: {"t": iso, "contas": {chave: valor_moeda_local}, "total": soma}.
    chave = nome da conta em baus.json (caiu a conta e voltou com outro nome,
    o gráfico simplesmente deixa de a desenhar).
    Valor em moeda local (a mesma que aparece nos cartões)."""
    if os.path.exists(HIST_FILE):
        try:
            h = json.load(open(HIST_FILE, encoding="utf-8-sig"))
            if isinstance(h, list):
                return h
        except Exception:
            pass
    return []


def hist_save(h: list) -> None:
    with open(HIST_FILE, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False)


def _alerta_cfg() -> dict:
    """Config dos alertas: "discord" (webhook), "alerta_min" (€), "alerta_dias" (liquidez)."""
    return load_cfg()


def _fmt_euro(v: float) -> str:
    s = "{:,.2f}".format(v)
    if "." in s:
        s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return "€" + s


def discord_enviar(payload: dict) -> tuple:
    """POST para o webhook do Discord (se configurado). -> (ok, msg)."""
    url = (_alerta_cfg().get("discord") or "").strip()
    if not url:
        return False, "sem webhook configurado (python tbh_baus.py --discord URL)"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "tbh-baus/1.0"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return (204 == r.status), "HTTP " + str(r.status)
    except Exception as e:
        return False, str(e)[:120]


def _alertas_dedup() -> dict:
    if os.path.exists(ALERTAS_FILE):
        try:
            d = json.load(open(ALERTAS_FILE, encoding="utf-8-sig"))
            if isinstance(d, dict):
                return d
        except Exception:
            pass
    return {"oportunidades": {}, "valor": {}}


def _alertas_dedup_save(d: dict) -> None:
    try:
        with open(ALERTAS_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass


def _alerta_valor(contas: list, total_local: float, moeda: str) -> None:
    """1 alerta/dia quando o total varia >= 10% vs o ultimo valor conhecido."""
    try:
        dedup = _alertas_dedup()
        last = dedup.get("valor") or {}
        if last and moeda != last.get("moeda"):
            last = {}
        anterior = float(last.get("total") or 0.0)
        if total_local <= 0 or anterior <= 0:
            if total_local > 0:
                dedup["valor"] = {"total": total_local, "moeda": moeda}
                _alertas_dedup_save(dedup)
            return
        pct = (total_local - anterior) / anterior * 100.0
        if abs(pct) < 10.0:
            return
        sobe = pct > 0
        sub = last.get("quando")
        if sub and (datetime.now() - datetime.fromisoformat(sub)).total_seconds() < 20 * 3600:
            # houve alerta ha menos de 20h: so atualizamos a base
            dedup["valor"] = {"total": total_local, "moeda": moeda, "quando": sub}
            _alertas_dedup_save(dedup)
            return
        fields = [{"name": it.get("nome", "?"), "value": _fmt_euro(it.get("valor_local") or 0.0), "inline": True}
                  for it in contas if it.get("valor_local")]
        emb = {"title": ("📈 Subida forte: " if sobe else "📉 Queda forte: ") + _fmt_euro(abs(total_local - anterior)),
               "color": 0x3FB950 if sobe else 0xF85149,
               "description": "Total " + _fmt_euro(anterior) + " → " + _fmt_euro(total_local)
                              + " (" + ("+" if sobe else "−") + "{:.1f}%".format(abs(pct)).replace(".", ",") + ")",
               "fields": fields[:10],
               "footer": {"text": "Monitor TBH · alerta máx 1/dia"},
               "timestamp": datetime.now().isoformat(timespec="seconds")}
        ok, msg = discord_enviar({"embeds": [emb]})
        _log("  discord valor: " + ("enviado (" if ok else "FALHOU (") + msg + ")")
        dedup["valor"] = {"total": total_local, "moeda": moeda,
                          "quando": datetime.now().isoformat(timespec="seconds")}
        _alertas_dedup_save(dedup)
    except Exception as e:
        _log("  alerta valor falhou: " + str(e)[:100])


def _alerta_oportunidades(contas: list, min_cent: int, dias_max: float) -> None:
    """1 alerta/ciclo com os melhores itens: cliente paga >= min_cent, tempo de venda
    <= dias_max, ordenados por ganho rapido. Dedup 24h por item.
    Sem webhook configurado: guarda "pendente" em alertas_dedup.json e envia tudo
    no proximo ciclo depois de configurar."""
    if not contas:
        return
    try:
        dedup = _alertas_dedup()
        opp = dedup.setdefault("oportunidades", {})
        agora = datetime.now()
        cand = []
        for it in contas:
            for o in (it.get("oportunidades") or []):
                if o["paga"] < min_cent:
                    continue
                dias = (o["qtd"] / o["vol"]) if o["vol"] else 9999.0
                if dias > dias_max:
                    continue
                t, tag = opp.get(o["nome"], (None, None))
                if t and tag != "pendente" and (agora - datetime.fromisoformat(t)).total_seconds() < 24 * 3600:
                    continue
                cand.append((it["nome"], o, dias))
        if not cand:
            return
        cand.sort(key=lambda x: -(x[1]["ganho"] * x[1]["qtd"]))
        cand = cand[:10]
        rows = []
        for conta, o, dias in cand:
            dtxt = ("~<1 dia" if dias < 1 else "~" + str(int(dias + 0.5)) + " d") if dias < 9999 else "?"
            rows.append({"name": o["nome"],
                         "value": "**" + _fmt_euro(o["ganho"] / 100.0) + "** por item (×"
                                  + str(o["qtd"]) + ") · " + conta + " · vende em " + dtxt,
                         "inline": False})
        emb = {"title": "⭐ " + str(len(rows)) + " itens que valem a pena vender já",
               "color": 0xFFD86B,
               "description": "cliente paga >= " + _fmt_euro(min_cent / 100.0)
                              + " · vende em <= " + str(int(dias_max)) + " dia(s) · ordenados por ganho rápido",
               "fields": rows,
               "footer": {"text": "Monitor TBH · mesmo item não repete em 24h"},
               "timestamp": agora.isoformat(timespec="seconds")}
        ok, msg = discord_enviar({"embeds": [emb]})
        if not ok and "sem webhook" in msg:
            # grava pendentes: entram no proximo alerta assim que o webhook existir
            for conta, o, dias in cand:
                opp.setdefault(o["nome"], [agora.isoformat(timespec="seconds"), "pendente"])[1] = "pendente"
            _alertas_dedup_save(dedup)
            return
        for conta, o, dias in cand:
            opp[o["nome"]] = [agora.isoformat(timespec="seconds"), conta]
        _alertas_dedup_save(dedup)
        _log("  discord oportunidades: " + ("enviado " + str(len(rows)) + " itens (" if ok else "FALHOU (") + msg + ")")
    except Exception as e:
        _log("  alerta oportunidades falhou: " + str(e)[:100])


def hist_gravar(moeda: str, valores: dict, total: float) -> None:
    """Grava um ponto do histórico (chamado na coletar()). Ignora se o último
    ponto for muito recente (evita gravar 10x iguais quando várias coisas
    regeneram a dashboard no mesmo minuto)."""
    try:
        h = hist_load()
        agora = datetime.now()
        if h:
            try:
                dt = (agora - datetime.fromisoformat(h[-1]["t"])).total_seconds()
                if 0 <= dt < HIST_PONTO_MIN:
                    return
            except Exception:
                pass
        h.append({"t": agora.isoformat(timespec="seconds"),
                  "moeda": moeda,
                  "contas": {k: round(float(v), 2) for k, v in valores.items()},
                  "total": round(float(total), 2)})
        if len(h) > 5000:
            h = h[-5000:]
        hist_save(h)
    except Exception:
        pass


# ---------------------------------------------------------------- câmbio

def get_rate(moeda: str):
    """-> (fator USD->moeda, origem) ou (None, erro). Usa cache 6h."""
    moeda = (moeda or "EUR").upper()
    if moeda == "USD":
        return 1.0, "fixo"
    c = load_cache()
    fx = c.get("fx") or {}
    if fx.get("moeda") == moeda and fx.get("t", 0) + FX_TTL > time.time() and fx.get("rate"):
        return fx["rate"], "cache"
    try:
        d = _get_json(FX_URL)
        rate = (d.get("rates") or {}).get(moeda)
        if not rate:
            return None, "moeda desconhecida: " + moeda
        save_cache({**c, "fx": {"moeda": moeda, "rate": rate, "t": int(time.time())}})
        return rate, "live"
    except Exception as e:
        if fx.get("rate"):
            return fx["rate"], "cache (offline)"
        return None, str(e)


# ---------------------------------------------------------------- api tbhindex

def resolver(idente: str) -> dict:
    """nick ou steam id -> {"steamId":..., "username":...} ou erro."""
    return _get_json(API + "/profile/resolve/" + urllib.parse.quote(idente.strip()))


def buscar_conta(steam_id: str) -> dict:
    """Perfil público da conta (o mesmo que a pagina /profile mostra)."""
    return _get_json(API + "/ranking/live/player/" + urllib.parse.quote(str(steam_id)))


# ---------------------------------------------------------------- coleta

def coletar() -> dict:
    """Busca todas as contas do baus.json + câmbio. Sempre devolve algo
    renderizável (usa cache se a API estiver inacessível).
    Valor vendável verdadeiro vem do save local (tbh_inventario.resumo_vendavel)
    quando houver 'save' em baus.json. Sem save, cai no antigo (API/medicao).
    """
    cfg = load_cfg()
    moeda = (cfg.get("moeda") or "EUR").upper()
    rate, rate_src = get_rate(moeda)
    cache = load_cache().get("payload")

    # cache de precos e dados do jogo para o vendavel local (evita refetch por conta)
    _precos = None
    _dados = None

    def vendavel_local(save_path: str):
        """Tenta calcular vendavel pelo save. Retorna (eur_vendavel, itens_vendaveis, itens_nao, tipos_nao, motivo_erro)"""
        nonlocal _precos, _dados
        if not save_path or not os.path.exists(save_path):
            return None
        try:
            if _dados is None:
                from tbh_inventario import carregar_dados_jogo, precos_frescos, resumo_vendavel, _para_centavos, eu_ganho_cent  # noqa
                _dados = carregar_dados_jogo()
                _precos = precos_frescos()
            from tbh_inventario import resumo_vendavel, _para_centavos, eu_ganho_cent  # type: ignore
            res = resumo_vendavel(save_path, _dados, _precos)
            vend = res["vendaveis"]
            itens_v = sum(vend.values())
            # totais + oportunidades por item (cliente paga / eu ganho / liquidez)
            tot_cent = 0
            ganho_cent = 0
            opps = []
            for nm, qtd in vend.items():
                p = _precos.get(nm)
                if not (p and p.get("sell")):
                    continue
                pc = _para_centavos(float(p["sell"]), rate or 1.0, moeda)
                gc = eu_ganho_cent(pc)
                tot_cent += pc * qtd
                ganho_cent += gc * qtd
                opps.append({"nome": nm, "qtd": qtd, "paga": pc, "ganho": gc,
                             "vol": int(p.get("vol") or 0), "med": float(p.get("med") or 0.0)})
            nao_qtd = sum(q for q, _ in res["nao_vendaveis"].values()) + sum(q for q, _ in res["deleted"].values())
            nao_tipos = len(res["nao_vendaveis"]) + len(res["deleted"])
            return (tot_cent, itens_v, nao_qtd, nao_tipos, len(vend), ganho_cent, opps)
        except Exception as e:
            return (None, 0, 0, 0, 0, 0, [])

    contas, total_usd, ok_any = [], 0.0, False
    erro_geral = None
    for c in cfg.get("contas", []):
        item = {"nome": c.get("nome") or c.get("id", "?"), "id": c.get("id", "")}
        # tenta vendavel local primeiro se tiver save
        loc = vendavel_local(c.get("save", ""))
        usou_local = False
        if loc and loc[0] is not None:
            tot_cent_local, itens_v, nao_qtd, nao_tipos, tipos_v, ganho_cent_local, opps = loc
            # tot_cent_local esta na moeda configurada; para total_usd guardamos aproximado em USD para compat mas render usa tot_eur_local
            # Calcula tot em moeda local: tot_cent_local/100
            tot_local_val = tot_cent_local / 100.0 if moeda not in ("JPY",) else float(tot_cent_local)
            # para total_usd do payload, converte de volta para USD aprox (divide por rate)
            total_usd_add = (tot_local_val / (rate or 1.0)) if moeda != "USD" else tot_local_val
            total_usd += total_usd_add
            ok_any = True
            usou_local = True
            # progresso (estagio/dificuldade/herois) direto do save local
            prog = {}
            try:
                from tbh_inventario import progresso_da_conta
                prog = progresso_da_conta(c.get("save", ""))
            except Exception:
                prog = {}
            # precisamos steam_id / username se possivel para link
            sid_try = str(c.get("id", ""))
            username_try = ""
            try:
                if not sid_try.isdigit():
                    r = resolver(sid_try)
                    sid_try = str(r.get("steamId") or sid_try)
                    username_try = r.get("username") or ""
                else:
                    # tenta buscar username via API mas sem exigir snapshot
                    try:
                        d2 = buscar_conta(sid_try)
                        username_try = (d2.get("player") or {}).get("username") or ""
                        item["rank"] = d2.get("globalRank")
                        item["privado"] = bool(d2.get("isPrivate") or d2.get("inventoryPrivate"))
                    except Exception:
                        pass
            except Exception:
                pass
            item.update({
                "steam_id": sid_try,
                "username": username_try,
                "vend_cent": tot_cent_local,
                "vend_itens": itens_v,
                "vend_tipos": tipos_v,
                "nao_itens": nao_qtd,
                "nao_tipos": nao_tipos,
                "valor_local": tot_local_val,
                "ganho_local": (ganho_cent_local if moeda == "JPY" else ganho_cent_local / 100.0),
                "oportunidades": opps,
                "fonte": "vendavel_local",
                "progresso": prog,
                "sync": datetime.now().isoformat(timespec="seconds"),
            })
            contas.append(item)
            continue
        # fallback: API / medicao antiga
        try:
            sid = str(c.get("id", ""))
            if not sid.isdigit():
                r = resolver(sid)
                sid = str(r.get("steamId") or sid)
                item["username"] = r.get("username") or ""
            d = buscar_conta(sid)
            snap = d.get("snapshot") or {}
            if snap:
                ok_any = True
                item.update({
                        "steam_id": sid,
                        "username": (d.get("player") or {}).get("username") or item.get("username") or "",
                        "bau": snap.get("total_stash_value") or 0.0,
                        "herois": snap.get("total_hero_value") or 0.0,
                        "itens": snap.get("total_items") or 0,
                        "rank": d.get("globalRank"),
                        "privado": bool(d.get("isPrivate") or d.get("inventoryPrivate")),
                        "sync": snap.get("submitted_at") or "",
                        "fonte": "api",
                        "valor_local": ((snap.get("total_stash_value") or 0.0)
                                        + (snap.get("total_hero_value") or 0.0)) * (rate or 1.0),
                    })
                total_usd += item["bau"] + item["herois"]
            else:
                med = (load_cache().get("medicoes") or {}).get(sid)
                if med:
                    ok_any = True
                    item.update({
                        "steam_id": sid,
                        "username": (d.get("player") or {}).get("username") or item.get("username") or "",
                        "med_eur": float(med.get("eur") or 0.0),
                        "itens": med.get("itens") or 0,
                        "sync": med.get("quando") or "",
                        "fonte": "medicao",
                        "valor_local": float(med.get("eur") or 0.0),
                    })
                else:
                    item["erro"] = ("perfil privado" if (d.get("isPrivate") or d.get("inventoryPrivate"))
                                    else "valores ainda a processar no servidor do site — volta a correr python tbh_site.py daqui a pouco")
        except urllib.error.HTTPError as e:
            item["erro"] = ("conta ainda não existe no tbhindex.com — importa o save dela lá"
                            if e.code == 404 else "HTTP " + str(e.code))
        except Exception as e:
            item["erro"] = str(e)[:120]
            erro_geral = str(e)[:120]
        contas.append(item)
    if not cfg.get("contas"):
        return {"moeda": moeda, "simbolo": SIMBOLOS.get(moeda, moeda + " "),
                "rate": rate, "rate_src": rate_src, "contas": [],
                "total_usd": 0.0, "gerado_em": datetime.now().isoformat(timespec="seconds")}

    if erro_geral and not ok_any and cache and cache.get("contas"):
        cache["cache_de"] = cache.get("gerado_em", "")
        cache["offline"] = True
        return cache

    out = {"moeda": moeda, "simbolo": SIMBOLOS.get(moeda, moeda + " "),
           "rate": rate, "rate_src": rate_src,
           "contas": contas, "total_usd": total_usd,
           "gerado_em": datetime.now().isoformat(timespec="seconds")}
    if erro_geral:
        out["aviso"] = "alguma conta falhou: " + erro_geral
    # ponto de histórico (uma entrada por atualização; na prática 1 por ciclo do monitor)
    # + alertas Discord (valor ±10% e oportunidades que valem a pena)
    try:
        _val = {it["nome"]: it["valor_local"] for it in contas if "valor_local" in it}
        if _val:
            hist_gravar(moeda, _val, sum(_val.values()))
            _alerta_valor(contas, sum(_val.values()), moeda)
            _cfg = load_cfg()
        if _cfg.get("discord") and not _cfg.get("sem_alertas"):
            _alerta_valor(contas, sum(_val.values()), moeda)
            _alerta_oportunidades(contas,
                                  int((float(_cfg.get("alerta_min") or 0.8)) * 100),
                                  float(_cfg.get("alerta_dias") or 1.0))
    except Exception:
        pass
    save_cache({**load_cache(), "payload": out})
    return out


# ---------------------------------------------------------------- formato

def fmt(v_usd: float, d: dict) -> str:
    sim = d.get("simbolo", "€")
    rate = d.get("rate") or 1.0
    v = v_usd * rate
    s = "{:,.2f}".format(v)
    if "." in s:  # pt-PT: 1.234,56
        s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return sim + s


def fmt_data(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%d/%m %H:%M")
    except Exception:
        return iso[:16].replace("T", " ")


def fmt_eur(v: float, d: dict) -> str:
    sim = d.get("simbolo", "€")
    s = "{:,.2f}".format(v)
    if "." in s:
        s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return sim + s


# ---------------------------------------------------------------- gráfico do histórico

CORES_HIST = ["#58a6ff", "#3fb950", "#f08833", "#f85149", "#bc8cff",
              "#39d2c0", "#ff7ab6", "#a8e05f", "#e3b341", "#939ca7"]

HIST_CSS = (
    ".bhx-wrap{background:linear-gradient(135deg,#1a160e,#12100a);border:1px solid #57492f;"
    "border-radius:14px;padding:12px 16px 10px;margin-bottom:12px}"
    ".bhx-head{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:6px}"
    ".bhx-head h3{margin:0;font-size:12px;letter-spacing:2px;color:#a89878;font-weight:800}"
    ".bhx-sub{font-size:10.5px;color:#8a7a5a}"
    ".bhx-legend{display:flex;gap:6px;flex-wrap:wrap;margin:2px 0 6px}"
    ".bhx-chip{display:inline-flex;align-items:center;gap:6px;background:#241f18;border:1px solid #5a4e38;"
    "border-radius:999px;padding:3px 10px;font-size:11px;font-weight:700;color:#e8dcc0;cursor:pointer;user-select:none}"
    ".bhx-chip:hover{border-color:#ffd86b}"
    ".bhx-chip.bhx-off{opacity:.35}"
    ".bhx-chip .sw{width:10px;height:10px;border-radius:3px;display:inline-block}"
    ".bhx-chip .lv{color:#a89878;font-weight:600}"
    ".bhx-chip.ttotal{border-color:#8a6a2a}"
    ".bhx-svg{display:block;width:100%;height:auto}"
    ".bhx-svg text{font:10.5px 'Segoe UI',system-ui,sans-serif;fill:#8a7a5a}"
    ".bhx-grid{stroke:#332b1e;stroke-width:1}"
    ".bhx-axis{stroke:#57492f;stroke-width:1}"
    ".bhx-serie{fill:none;stroke-width:2.4;stroke-linejoin:round;stroke-linecap:round}"
    ".bhx-serie.bhx-off,.bhx-total.bhx-off{display:none}"
    ".bhx-total{fill:none;stroke:#ffd86b;stroke-width:3;stroke-dasharray:7 5;"
    "stroke-linejoin:round;stroke-linecap:round;opacity:.92}"
    ".bhx-dot{stroke:#141210;stroke-width:1}"
    ".bhx-trend{font-size:14px;font-weight:700;margin-left:12px}"
    ".bhx-trend.up{color:#7ee787}.bhx-trend.down{color:#ffb0b0}.bhx-trend.flat{color:#8a7a5a}"
    ".bhx-btns{display:flex;gap:5px;margin:2px 0 4px;flex-wrap:wrap}"
    ".bhx-btn{background:#241f18;border:1px solid #5a4e38;border-radius:6px;padding:3px 10px;"
    "font-size:10.5px;font-weight:700;color:#c8b890;cursor:pointer;letter-spacing:1px}"
    ".bhx-btn:hover{border-color:#ffd86b;color:#ffd86b}"
    ".bhx-btn.on{background:#ffd86b;color:#141210;border-color:#ffd86b}"
    ".bhx-max{stroke:#141210;stroke-width:1}"
    ".bhx-xhair{stroke:#8a7a5a;stroke-width:1;stroke-dasharray:3 3;opacity:.7}"
    ".bhx-tip{fill:rgba(20,18,16,.96);stroke:#57492f;stroke-width:1}"
    ".bhx-tiptext{font:11px 'Segoe UI',system-ui,sans-serif;fill:#e8dcc0}"
    ".bspark{display:flex;align-items:center;gap:8px;margin-top:4px}"
    ".bhx-spark{display:block;flex:0 0 auto}"
    ".bttl{font-size:11px;font-weight:700;color:#8a7a5a}"
    ".bttl.bhx-up{color:#7ee787}.bttl.bhx-dn{color:#ffb0b0}"
)

PROG_CSS = (
    ".buser{font-weight:600;color:#a89878;font-size:11px}"
    ".bprog{font-size:11px;color:#c8b890;margin-top:3px}"
    ".bdif{font-weight:700;padding:1px 8px;border-radius:6px;display:inline-block;font-size:11px}"
    ".bdif.dif-normal{background:#2a4a2a;color:#7ee787}"
    ".bdif.dif-nightmare{background:#4a3a2a;color:#e3b341}"
    ".bdif.dif-torment{background:#4a2a2a;color:#ff9d9d}"
    ".bdif.dif-hell{background:#4a1f1f;color:#ff7070}"
    ".bherois{display:flex;gap:5px;flex-wrap:wrap;margin-top:4px}"
    ".hchip{background:#241f18;border:1px solid #5a4e38;border-radius:999px;padding:2px 9px;font-size:10.5px;color:#e8dcc0}"
    ".hchip b{color:#ffd86b}"
    ".baugrid > div{position:relative}"
    ".recbox{display:inline-block;position:absolute;top:8px;right:8px;z-index:40}"
    ".recbox summary{list-style:none;cursor:pointer;user-select:none;font-size:11px;font-weight:800;"
    "color:#ffd86b;background:#241f18;border:1px solid #5a4e38;border-radius:999px;padding:2px 10px}"
    ".recbox summary::-webkit-details-marker{display:none}"
    ".recbox summary:hover{border-color:#ffd86b}"
    ".recbox[open] summary{background:#ffd86b;color:#141210;border-color:#ffd86b}"
    ".recpanel{position:absolute;top:28px;right:0;z-index:60;width:340px;background:#14120e;"
    "border:1px solid #8a6a2a;border-radius:10px;padding:8px 12px 10px;box-shadow:0 8px 30px rgba(0,0,0,.6);text-align:left}"
    ".recpanel h4{margin:7px 0 3px;font-size:10.5px;letter-spacing:1.5px;color:#a89878}"
    ".rec-line{font-size:11.5px;color:#e8dcc0;padding:2px 0;line-height:1.45}"
    ".rec-line.hot{color:#ffd86b}"
    ".rec-line.ok{color:#7ee787}"
    ".rec-line.dim{color:#8a7a5a;font-size:10.5px}"
    ".rec-dim{color:#8a7a5a}"
    ".rec-line.go{cursor:pointer;border-radius:6px;padding:2px 6px;margin:0 -6px}"
    ".rec-line.go:hover{background:#2a2317;outline:1px solid #8a6a2a}"
    ".rec-dica{padding-top:5px;font-size:10px!important}"
)

BHX_JS = r'''(function(){
  var box=document.querySelector('.bhx-wrap');if(!box)return;
  var svg=box.querySelector('.bhx-svg');if(!svg||svg.dataset.bhx)return;svg.dataset.bhx='1';
  var de=document.getElementById('bhx-data');if(!de)return;var D;try{D=JSON.parse(de.textContent)}catch(e){return}
  var G=D.geom||{};var W=G.W||880,H=G.H||220,PL=G.PL||62,PW=G.PW||806,PT=G.PT||14,PH=G.PH||176,ymax=G.ymax||1;
  var n=(D.ts||[]).length;if(n<2)return;
  function xi(i){return PL+PW*(i/(n-1))}
  function yj(v){return PT+PH*(1-Math.min(Math.max(v||0,0),ymax)/ymax)}
  var NS='http://www.w3.org/2000/svg';
  function mk(t,a){var e=document.createElementNS(NS,t);for(var k in a)e.setAttribute(k,a[k]);return e}
  var skeys=Object.keys(D.series||{});
  var cur=null;
  function i0de(h){if(!h)return 0;var tf=new Date(D.ts[n-1]).getTime(),tm=tf-h*3600e3,i0=0;while(i0<n&&new Date(D.ts[i0]).getTime()<tm)i0++;return Math.min(i0,n-2)}
  function dpath(vals,i0){var out='',c=[],i,v;for(i=i0;i<n;i++){v=vals[i];if(v==null){if(c.length){out+=(out?' ':'')+'M '+c.join(' L ');c=[]}continue}c.push(xi(i).toFixed(1)+' '+yj(v).toFixed(1))}if(c.length)out+=(out?' ':'')+'M '+c.join(' L ');return out}
  function fdata(i){var d=new Date(D.ts[i]);return ('0'+d.getDate()).slice(-2)+'/'+('0'+(d.getMonth()+1)).slice(-2)+' '+('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2)}
  function rebuild(){var i0=i0de(cur);
    var pt=document.getElementById('bhx-total');if(pt&&D.total)pt.setAttribute('d',dpath(D.total,i0));
    skeys.forEach(function(k,j){var p=document.getElementById('bhx-serie-'+j);if(p)p.setAttribute('d',dpath(D.series[k],i0))});
    var t0=svg.querySelector('[data-role=t0]'),t1=svg.querySelector('[data-role=t1]');
    if(t0)t0.textContent=fdata(i0);
    if(t1){t1.style.display=(n-i0>=3)?'':'none';t1.textContent=fdata(i0+Math.floor((n-1-i0)/2))}
  }
  var btns=box.querySelectorAll('.bhx-btn');
  Array.prototype.forEach.call(btns,function(b){b.addEventListener('click',function(){
    Array.prototype.forEach.call(btns,function(x){x.classList.remove('on')});b.classList.add('on');
    cur=(b.dataset.h==='all')?null:parseFloat(b.dataset.h);rebuild();
  })});
  var xh=mk('line',{'class':'bhx-xhair',x1:0,y1:PT,x2:0,y2:PT+PH,visibility:'hidden'});
  var tip=mk('g',{visibility:'hidden'});
  tip.appendChild(mk('rect',{'class':'bhx-tip',x:0,y:0,width:210,height:26+(1+skeys.length)*14,rx:6}));
  var lines=[];
  function tl(y,cor,peso){var t=mk('text',{'class':'bhx-tiptext',x:8,y:y});if(cor)t.setAttribute('fill',cor);if(peso)t.setAttribute('font-weight',peso);tip.appendChild(t);lines.push(t);return t}
  tl(15,null,'700');tl(30,'#ffd86b','700');
  skeys.forEach(function(k,j){tl(44+j*14,D.cores[k]||'#e8dcc0')});
  var dots={};
  skeys.forEach(function(k){var c=mk('circle',{'class':'bhx-dot',r:3.5,fill:D.cores[k]||'#fff',visibility:'hidden'});svg.appendChild(c);dots[k]=c});
  svg.appendChild(xh);svg.appendChild(tip);
  svg.addEventListener('mousemove',function(ev){
    var r=svg.getBoundingClientRect();if(!r.width)return;
    var mx=(ev.clientX-r.left)*W/r.width;
    var i=Math.round((mx-PL)/PW*(n-1));i=Math.max(0,Math.min(n-1,i));
    var x=xi(i);
    xh.setAttribute('x1',x);xh.setAttribute('x2',x);xh.setAttribute('visibility','visible');
    lines[0].textContent=fdata(i);
    lines[1].textContent='TOTAL  '+((D.total[i]||0).toFixed(2)).replace('.',',');
    skeys.forEach(function(k,j){var v=D.series[k][i];lines[2+j].textContent=k+'  '+(v==null?'—':v.toFixed(2).replace('.',','));
      var dc=dots[k];if(v==null){dc.setAttribute('visibility','hidden')}else{dc.setAttribute('cx',x);dc.setAttribute('cy',yj(v));dc.setAttribute('visibility','visible')}});
    tip.setAttribute('visibility','visible');
    var tx=(x+14+215>W)?(x-14-215):(x+14);
    tip.setAttribute('transform','translate('+Math.max(2,tx)+','+(PT+2)+')');
  });
  svg.addEventListener('mouseleave',function(){xh.setAttribute('visibility','hidden');tip.setAttribute('visibility','hidden');skeys.forEach(function(k){dots[k].setAttribute('visibility','hidden')})});
})();'''


def _fmt_eixo(v: float) -> str:
    if v >= 1000:
        return "{:,.0f}".format(v).replace(",", ".")
    if v >= 100:
        return "{:.0f}".format(v)
    if v >= 10:
        return "{:.1f}".format(v).replace(".", ",")
    return "{:.2f}".format(v).replace(".", ",")


def _sparkline(vals: list, cor: str, w: int = 88, h: int = 22):
    """Mini-gráfico SVG (últimos N valores) para os cartões de conta."""
    v = [x for x in vals if x is not None]
    if len(v) < 2 or max(v) <= 0:
        return ""
    ymax = max(v) * 1.08 or 1.0
    pts = []
    for i, x in enumerate(v):
        px = round(1 + (w - 2) * i / (len(v) - 1), 1)
        py = round(1 + (h - 2) * (1.0 - min(max(x, 0.0), ymax) / ymax), 1)
        pts.append(str(px) + "," + str(py))
    subiu = v[-1] >= v[0]
    cc = "#7ee787" if subiu else "#ffb0b0"
    return ('<svg class="bhx-spark" width="' + str(w) + '" height="' + str(h) + '" viewBox="0 0 '
            + str(w) + ' ' + str(h) + '"><polyline fill="none" stroke="' + cor
            + '" stroke-width="1.8" points="' + " ".join(pts) + '"/></svg>')


def render_historico_svg(d: dict, max_pontos: int = 500):
    """Gráfico de linha (SVG puro, sem libs) do histórico gravado por coletar().
    Um traço por conta + TOTAL a tracejado dourado. -> (html, info|None)."""
    h = hist_load()[-max_pontos:]
    pts = [p for p in h if isinstance(p, dict) and p.get("t") and isinstance(p.get("contas"), dict)]
    if not pts:
        return "", None
    if len(pts) < 2:
        return ('<div class="bhx-wrap"><style>' + HIST_CSS + '</style>'
                '<div class="bhx-head"><h3>📈 HISTÓRICO DO VALOR VENDÁVEL</h3>'
                '<span class="bhx-sub">a gravar — 1º ponto registado em ' + fmt_data(pts[0]["t"])
                + ' · o gráfico aparece no próximo ciclo do monitor</span></div></div>'), None

    info = {"n": len(pts), "desde": pts[0]["t"],
            "moedas": sorted({str(p.get("moeda") or "?") for p in pts})}
    try:
        t0, t1 = float(pts[-2].get("total") or 0.0), float(pts[-1].get("total") or 0.0)
        info["delta"] = t1 - t0
        info["pct"] = ((t1 - t0) / t0 * 100.0) if t0 > 0 else None
    except Exception:
        info["delta"], info["pct"] = 0.0, None

    # nomes das series (ordem de primeira aparição) ordenados pelo último valor
    nomes = []
    for p in pts:
        for k in p["contas"]:
            if k not in nomes:
                nomes.append(k)
    nomes.sort(key=lambda k: -float(pts[-1]["contas"].get(k) or 0.0))

    W, H, PL, PR, PT, PB = 880, 220, 62, 12, 14, 30
    PW, PH = W - PL - PR, H - PT - PB
    n = len(pts)
    ymax = 0.0
    for p in pts:
        ymax = max(ymax, float(p.get("total") or 0.0), *(float(v or 0.0) for v in p["contas"].values()))
    if ymax <= 0:
        ymax = 1.0
    ymax *= 1.08

    def xi(i: int) -> float:
        return PL + PW * (i / (n - 1)) if n > 1 else PL + PW / 2

    def yj(v) -> float:
        return PT + PH * (1.0 - min(max(float(v or 0.0), 0.0), ymax) / ymax)

    svg = ['<svg class="bhx-svg" viewBox="0 0 ' + str(W) + ' ' + str(H)
           + '" preserveAspectRatio="xMidYMid meet" role="img">']
    # grelha horizontal + labels
    for j in (1, 2, 3):
        v = ymax * j / 4.0
        y = yj(v)
        svg.append('<line class="bhx-grid" x1="' + str(PL) + '" y1="' + str(round(y, 1))
                   + '" x2="' + str(PL + PW) + '" y2="' + str(round(y, 1)) + '"/>')
        svg.append('<text x="' + str(PL - 6) + '" y="' + str(round(y + 3.5, 1))
                   + '" text-anchor="end">' + _fmt_eixo(v) + '</text>')
    svg.append('<text x="' + str(PL - 6) + '" y="' + str(round(yj(0) + 3.5, 1))
               + '" text-anchor="end">0</text>')
    svg.append('<line class="bhx-axis" x1="' + str(PL) + '" y1="' + str(round(yj(0), 1))
               + '" x2="' + str(PL + PW) + '" y2="' + str(round(yj(0), 1)) + '"/>')
    # marca do maximo do TOTAL (referencia: 'nunca foi tão alto')
    try:
        _im = max(range(n), key=lambda i: float(pts[i].get("total") or 0.0))
        if float(pts[_im].get("total") or 0.0) > 0 and _im < n - 1:
            svg.append('<line class="bhx-max" x1="' + str(PL) + '" y1="' + str(round(yj(pts[_im]["total"]), 1))
                       + '" x2="' + str(PL + PW) + '" y2="' + str(round(yj(pts[_im]["total"]), 1))
                       + '"/><text x="' + str(PL + PW) + '" y="' + str(round(yj(pts[_im]["total"]) - 4, 1))
                       + '" text-anchor="end">máx ' + esc(_fmt_eixo(float(pts[_im]["total"])))
                       + ' · ' + esc(fmt_data(pts[_im]["t"])) + '</text>')
    except Exception:
        pass
    # labels de tempo (inicio / meio / fim)
    svg.append('<text data-role="t0" x="' + str(PL) + '" y="' + str(H - 8) + '">' + esc(fmt_data(pts[0]["t"])) + '</text>')
    if n >= 3:
        svg.append('<text data-role="t1" x="' + str(PL + PW / 2) + '" y="' + str(H - 8)
                   + '" text-anchor="middle">' + esc(fmt_data(pts[n // 2]["t"])) + '</text>')
    svg.append('<text data-role="t2" x="' + str(PL + PW) + '" y="' + str(H - 8)
               + '" text-anchor="end">' + esc(fmt_data(pts[-1]["t"])) + '</text>')

    # traço TOTAL (tracejado dourado)
    d_total = " ".join(("M" if i == 0 else "L") + " " + str(round(xi(i), 1)) + " "
                       + str(round(yj(p.get("total")), 1)) for i, p in enumerate(pts))
    svg.append('<path class="bhx-total" id="bhx-total" d="' + d_total + '"><title>TOTAL — '
               + esc(_fmt_eixo(float(pts[-1].get("total") or 0.0))) + ' agora</title></path>')

    # um traço por conta (com buracos se a conta faltar nalgum ponto)
    dots = []
    for idx, nm in enumerate(nomes):
        cor = CORES_HIST[idx % len(CORES_HIST)]
        segs, cur = [], []
        ultimo_i = -1
        for i, p in enumerate(pts):
            v = p["contas"].get(nm)
            if v is None:
                if cur:
                    segs.append(cur)
                    cur = []
                continue
            cur.append(str(round(xi(i), 1)) + " " + str(round(yj(v), 1)))
            ultimo_i = i
        if cur:
            segs.append(cur)
        d_attr = " ".join("M " + " L ".join(seg) for seg in segs)
        if not d_attr:
            continue
        ult_v = float(pts[ultimo_i]["contas"].get(nm) or 0.0) if ultimo_i >= 0 else 0.0
        svg.append('<path class="bhx-serie" id="bhx-serie-' + str(idx) + '" stroke="' + cor
                   + '" d="' + d_attr + '"><title>' + esc(nm) + " — último: "
                   + esc(_fmt_eixo(ult_v)) + '</title></path>')
        if ultimo_i >= 0:
            dots.append('<circle class="bhx-dot" cx="' + str(round(xi(ultimo_i), 1)) + '" cy="'
                        + str(round(yj(pts[ultimo_i]["contas"].get(nm)), 1)) + '" r="3.2" fill="'
                        + cor + '"/>')
    svg.extend(dots)
    svg.append('</svg>')

    # Δ24h por serie (vs ponto ~24h atras)
    def _delta24(series_valores):
        if len(pts) < 2:
            return None
        alvo = (datetime.fromisoformat(pts[-1]["t"]) - timedelta(hours=24)).timestamp()
        ref = None
        for i in range(len(pts) - 1, -1, -1):
            ti = datetime.fromisoformat(pts[i]["t"]).timestamp()
            if ti <= alvo:
                ref = i
                break
        if ref is None:
            return None
        v_ref = series_valores[ref] if isinstance(series_valores, list) else pts[ref].get("total")
        if v_ref is None or v_ref <= 0:
            return None
        return float(pts[-1].get("total") or 0.0) - float(v_ref) if not isinstance(series_valores, list) else float(series_valores[-1]) - float(v_ref)

    total_24 = _delta24(None)
    def _chip_delta_txt(delta):
        if delta is None:
            return ''
        cls = 'bhx-up' if delta > 0.005 else ('bhx-dn' if delta < -0.005 else '')
        sgn = '+' if delta > 0 else '−'
        return ' <span class="bttl ' + cls + '">' + sgn + esc(_fmt_eixo(abs(delta))) + '/24h</span>'

    # legenda clicável (liga/desliga cada traço)
    chips = ['<span class="bhx-chip ttotal" onclick=\'var e=document.getElementById("bhx-total");'
             'e.classList.toggle("bhx-off");this.classList.toggle("bhx-off")\'>'
             '<span class="sw" style="background:#ffd86b"></span>TOTAL <span class="lv">'
             + esc(_fmt_eixo(float(pts[-1].get("total") or 0.0))) + '</span>'
             + _chip_delta_txt(total_24) + '</span>']
    for idx, nm in enumerate(nomes):
        cor = CORES_HIST[idx % len(CORES_HIST)]
        vals_serie = [p["contas"].get(nm) for p in pts]
        chips.append(
            '<span class="bhx-chip" onclick=\'var e=document.getElementById("bhx-serie-'
            + str(idx) + '");if(e){e.classList.toggle("bhx-off");}this.classList.toggle("bhx-off")\'>'
            '<span class="sw" style="background:' + cor + '"></span>' + esc(nm)
            + ' <span class="lv">' + esc(_fmt_eixo(float(pts[-1]["contas"].get(nm) or 0.0))) + '</span>'
            + _chip_delta_txt(_delta24(vals_serie)) + '</span>')

    sub = (str(info["n"]) + " pontos · desde " + fmt_data(info["desde"])
           + " · grava 1 ponto por atualização (mínimo 5 min entre pontos)")
    if len(info["moedas"]) > 1:
        sub += ' · <span style="color:#ffb0b0">⚠ pontos com moedas diferentes (' \
               + esc(", ".join(info["moedas"])) + ') — mudaste a moeda; a escala mistura tudo</span>'

    # linha com cursor + caixa flutuante (JS); dados para o JS
    try:
        jsdata = json.dumps({"ts": [p["t"] for p in pts],
                             "total": [p.get("total") or 0 for p in pts],
                             "series": {nm: [p["contas"].get(nm) for p in pts] for nm in nomes},
                             "cores": {nm: CORES_HIST[i % len(CORES_HIST)] for i, nm in enumerate(nomes)},
                             "geom": {"W": W, "H": H, "PL": PL, "PW": PW, "PT": PT, "PH": PH,
                                      "ymax": round(ymax, 4)}})
    except Exception:
        jsdata = "{}"

    html = ('<div class="bhx-wrap"><style>' + HIST_CSS + '</style>'
            '<div class="bhx-head"><h3>📈 HISTÓRICO DO VALOR VENDÁVEL</h3>'
            '<span class="bhx-sub">' + sub + '</span></div>'
            '<div class="bhx-btns">'
            '<button class="bhx-btn" data-h="0.2" type="button">6H</button>'
            '<button class="bhx-btn" data-h="1" type="button">1D</button>'
            '<button class="bhx-btn" data-h="7" type="button">1S</button>'
            '<button class="bhx-btn on" data-h="all" type="button">TUDO</button>'
            '<span style="flex:1"></span>'
            '<span class="bhx-sub">passa o rato pelo gráfico para ver os valores</span></div>'
            '<div class="bhx-legend">' + "".join(chips) + '</div>'
            + "".join(svg)
            + '<script type="application/json" id="bhx-data">' + jsdata + '</script>'
            + '<script>' + BHX_JS + '</script></div>')
    return html, info


# ---------------------------------------------------------------- render

def _badge_trend(info, sim: str) -> str:
    """Seta de tendência ao lado do VALOR REAL VENDÁVEL (vs penúltimo ponto)."""
    if not info or info.get("pct") is None:
        return ""
    delta, pct = info.get("delta") or 0.0, info.get("pct") or 0.0
    if abs(pct) < 0.01:
        return '<span class="bhx-trend flat">= estável</span>'
    cls = "up" if delta > 0 else "down"
    seta = "▲" if delta > 0 else "▼"
    s = "{:,.2f}".format(abs(delta))
    if "." in s:
        s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    return ('<span class="bhx-trend ' + cls + '">' + seta + " " + sim + s
            + " (" + ("+" if delta > 0 else "−") + "{:.1f}".format(abs(pct)).replace(".", ",") + "%)</span>")


def render_section() -> str:
    """HTML da seção MEUS BAÚS para embutir no minhas_builds.html."""
    cfg = load_cfg()
    if not cfg.get("contas"):
        return (
            '<div class="bauhint">💰 <b>MEUS BAÚS</b> — valor real das contas ainda não ativado. '
            'Importa cada save em <a class="ilink" href="https://tbhindex.com/pt/" target="_blank">'
            'tbhindex.com → Inspecionar Seu Baú</a> e depois corre no terminal: '
            '<span class="cmdtxt">python tbh_baus.py --add O_TEU_NICK</span></div>'
        )
    try:
        d = coletar()
    except Exception as e:
        return ('<div class="bauhint">💰 <b>MEUS BAÚS</b> — falha a atualizar agora ('
                + esc(str(e)[:120]) + '). Valores anteriores em <a class="ilink" '
                'href="inventario.html">inventario.html</a>; tenta <span class="cmdtxt">python tbh_baus.py --abrir</span></div>')
    sim = d.get("simbolo", "€")
    tot_ganho_local = 0.0

    try:
        histo_html, histo_info = render_historico_svg(d)
    except Exception:
        histo_html, histo_info = "", None

    cards, tot_eur = [], 0.0
    n_inv = os.path.join(BASE, "inventario.html")
    tem_inv = os.path.exists(n_inv)
    # série por conta (para sparklines e delta24h)
    try:
        _hist_pts = [p for p in hist_load() if isinstance(p, dict) and p.get("t") and isinstance(p.get("contas"), dict)]
    except Exception:
        _hist_pts = []

    def _serie_conta(nm):
        vals = [p["contas"].get(nm) for p in _hist_pts]
        if not any(v is not None for v in vals):
            return []
        # preenche buracos no início/fim com None (sparkline salta)
        return vals

    def _delta24_h(vals):
        if not vals or len(vals) < 2 or vals[-1] is None:
            return None
        try:
            alvo = (datetime.fromisoformat(_hist_pts[-1]["t"]) - timedelta(hours=24)).timestamp()
        except Exception:
            return None
        ref = None
        for i in range(len(_hist_pts) - 1, -1, -1):
            try:
                if datetime.fromisoformat(_hist_pts[i]["t"]).timestamp() <= alvo:
                    ref = i
                    break
            except Exception:
                continue
        if ref is None or vals[ref] is None or vals[ref] <= 0:
            return None
        return float(vals[-1]) - float(vals[ref])

    nomes_key = []
    for p in _hist_pts:
        for k in p["contas"]:
            if k not in nomes_key:
                nomes_key.append(k)

    # recomendacoes em tempo real (save por conta, do baus.json)
    _saves = {c.get("nome"): c.get("save", "") for c in cfg.get("contas", [])}

    def _user_chip(c):
        u = c.get("username") or ""
        if not u:
            m = re.search(r"\(([^)]+)\)", c.get("nome") or "")
            u = m.group(1) if m else (c.get("steam_id") or c.get("id") or "")
        return (' <span class="buser">\U0001F464 ' + esc(u) + "</span>") if u else ""

    def _badge_dif(txt, dif):
        """'22-2 Hell (onda 7)' + 'Hell' -> '22-2 <badge>Hell</badge> (onda 7)'"""
        if not txt:
            return ""
        if dif and dif in txt:
            head, _, tail = txt.partition(dif)
            cls = "bdif dif-" + dif.lower()
            return esc(head) + '<span class="' + cls + '">' + esc(dif) + "</span>" + esc(tail)
        return esc(txt)

    def _prog_html(c):
        """Linha de progresso (onde esta + recorde) + chips dos herois, a partir do save."""
        prog = c.get("progresso") or {}
        if not prog:
            return ""
        bits = []
        at = _badge_dif(prog.get("atual") or "", prog.get("atual_dif") or "")
        if at:
            bits.append("\U0001F4CD " + at)
        mx = prog.get("max") or ""
        atual_base = (prog.get("atual") or "").split(" (onda")[0]
        if mx and mx != atual_base:
            bits.append("\U0001F3C6 " + _badge_dif(mx, prog.get("max_dif") or ""))
        if prog.get("plague"):
            bits.append('<span class="hchip">\U0001F9A0' + esc(prog["plague"].replace(" · ", " ").strip()) + "</span>")
        if not bits:
            return ""
        hh = ""
        herois = [h for h in (prog.get("herois") or []) if h.get("lvl")]
        if herois:
            hh = '<div class="bherois">' + "".join(
                '<span class="hchip">' + esc(h["nome"]) + " <b>nv " + str(h["lvl"]) + "</b></span>" for h in herois) + "</div>"
        return '<div class="bprog">' + " · ".join(bits) + "</div>" + hh

    for i, c in enumerate(d["contas"], 1):
        inv_click = ""
        if tem_inv:
            # clicar em qualquer lado do cartao abre o inventario desta conta
            inv_click = (' class="baucard link" onclick="location.href=\'inventario.html#conta-'
                         + str(i) + "\'\" title=\"Ver inventário completo desta conta\"")
        if "erro" in c and "bau" not in c and "med_eur" not in c:
            cards.append(
                '<div' + inv_click + '><div class="bnome">' + esc(c["nome"]) + _user_chip(c) + '</div>'
                '<div class="bvalor">—</div><div class="binfo">' + esc(c["erro"]) + "</div></div>")
            continue
        bau, her = c.get("bau", 0.0), c.get("herois", 0.0)
        user = c.get("username") or c.get("steam_id") or c["id"]
        link = ('<a class="ilink" href="https://tbhindex.com/profile/' + esc(user)
                + '" target="_blank">' + esc(c["nome"]) + "</a>")
        rank = (' · rank #' + str(c["rank"])) if c.get("rank") else ""
        priv = ' · 🔒 privado' if c.get("privado") else ""
        # NOVO: vendavel local (save + mercado) tem prioridade - e o valor REAL
        if c.get("fonte") == "vendavel_local":
            # vend_cent esta na moeda local em centavos
            moeda_local = (d.get("moeda") or "EUR")
            sem_cent = moeda_local == "JPY"
            sim_local = d.get("simbolo", "€")
            def _fmt_cent_local(cent):
                if sem_cent:
                    s = str(int(cent))
                else:
                    s = "{:,.2f}".format(cent / 100.0)
                    if "." in s:
                        s = s.replace(",", "§").replace(".", ",").replace("§", ".")
                return sim_local + s
            vend_cent = c.get("vend_cent", 0)
            tot_eur_local = vend_cent / 100.0 if not sem_cent else float(vend_cent)
            tot_eur += tot_eur_local
            ganho_local = c.get("ganho_local") or 0.0
            tot_ganho_local += ganho_local
            nao_txt = ""
            if c.get("nao_itens"):
                nao_txt = ' · <span style="color:#d29922">' + str(c.get("nao_itens", 0)) + ' itens não vendáveis excluídos</span>'
            # sparkline + delta24h desta conta
            cor_ct = CORES_HIST[(i - 1) % len(CORES_HIST)]
            spark = _sparkline(_serie_conta(c["nome"]), cor_ct)
            d24 = _delta24_h(_serie_conta(c["nome"]))
            if d24 is None:
                d24_html = ''
            else:
                cls = 'bhx-up' if d24 > 0.005 else ('bhx-dn' if d24 < -0.005 else '')
                sgn = '+' if d24 > 0 else '−'
                d24_html = ' <span class="bttl ' + cls + '">' + sgn + _fmt_eixo(abs(d24)) + '/24h</span>'
            spark_html = ('<div class="bspark">' + spark
                          + '<span class="binfo">últimas medições</span>' + d24_html + '</div>') if spark else d24_html
            progh = _prog_html(c)
            # chip 🔔 com recomendações (uva do save: pontos livres, skills, runas)
            try:
                import tbh_recomendar as _tr
                rec_chip = _tr.chip_conta(_saves.get(c["nome"], ""), c["nome"])
            except Exception:
                rec_chip = ""
            cards.append(
                '<div' + inv_click + '><div class="bnome">' + link + priv + _user_chip(c) + "</div>"
                + rec_chip
                + '<div class="bvalor">' + _fmt_cent_local(vend_cent) + "</div>"
                '<div class="bsub">vendável · tu recebes <b style="color:#7ee787">' + _fmt_cent_local(int(round(ganho_local * 100.0)))
                + "</b> · " + str(c.get("vend_tipos", 0)) + " tipos · " + str(c.get("vend_itens", 0)) + " itens" + nao_txt + "</div>"
                + progh
                + spark_html
                + '<div class="binfo">valor real no Mercado agora · <a class="ilink" href="inventario.html#conta-' + str(i) + '">ver itens</a> · '
                + fmt_data(c.get("sync", "")) + "</div></div>")
            continue
        if c.get("fonte") == "medicao":
            tot_eur += c.get("med_eur", 0.0)
            velho = ""
            try:
                horas = (datetime.now() - datetime.fromisoformat(c.get("sync", ""))).total_seconds() / 3600
                if horas > 3:
                    velho = (' <span class="bwarn">⚠ medida antiga (' + str(int(horas))
                             + "h) — o monitor está a correr?</span>")
            except Exception:
                pass
            cards.append(
                '<div' + inv_click + '><div class="bnome">' + link + priv + _user_chip(c) + "</div>"
                '<div class="bvalor">' + fmt_eur(c.get("med_eur", 0.0), d) + "</div>"
                '<div class="bsub">medido na página do site (VALOR TOTAL antigo — sem filtro vendável)</div>'
                '<div class="binfo">' + str(c.get("itens", 0)) + " itens · medido em "
                + fmt_data(c.get("sync", "")) + velho + "</div></div>")
            continue
        tot_eur += (bau + her) * (d.get("rate") or 1.0)
        cards.append(
            '<div' + inv_click + '><div class="bnome">' + link + rank + priv + "</div>"
            '<div class="bvalor">' + fmt(bau + her, d) + "</div>"
            '<div class="bsub">baú ' + fmt(bau, d) + " · heróis " + fmt(her, d) + " (API — pode incluir não vendáveis)</div>"
            '<div class="binfo">' + str(c.get("itens", 0)) + " itens · save no site: "
            + fmt_data(c.get("sync", "")) + "</div></div>")

    n_ok = len([c for c in d["contas"] if c.get("fonte")])
    n_todas = len(d["contas"])

    fonte = "câmbio " + ("live" if d.get("rate_src") == "live" else esc(d.get("rate_src", "?")))
    extra = ""
    if d.get("offline"):
        extra = ' <span class="bwarn">(offline — valores de ' + fmt_data(d.get("cache_de", "")) + ")</span>"
    if d.get("aviso"):
        extra += ' <span class="bwarn">(' + esc(d["aviso"]) + ")</span>"
    # --- timestamp fresco + aviso se o farm parou (explica o 02:04 do print) ---
    gerado_iso = d.get("gerado_em") or ""
    gerado_txt = fmt_data(gerado_iso) if gerado_iso else "—"
    delta_txt = ""
    stale_warn = ""
    stale_warn_btotal = ""
    try:
        if gerado_iso:
            delta_min = (datetime.now() - datetime.fromisoformat(gerado_iso)).total_seconds() / 60.0
            if delta_min < 1:
                delta_txt = "há <1 min"
            elif delta_min < 60:
                delta_txt = f"há {int(delta_min)} min"
            else:
                delta_txt = f"há {int(delta_min // 60)}h {int(delta_min % 60):02d}min"
            if delta_min > 18:
                stale_warn = f' <span class="bwarn" style="background:#3a2020;padding:2px 8px;border-radius:6px;border:1px solid #7a4040">⚠ FARM PARADO {delta_txt} — reabre <b>atualizar_baus_agora.bat</b> ou <b>abrir_minhas_builds.bat</b> e deixa a janela aberta</span>'
                stale_warn_btotal = f' <span class="bwarn">⚠ parado {delta_txt}</span>'
            elif delta_min > 9:
                stale_warn_btotal = f' <span style="color:#e3b341">· {delta_txt}</span>'
            else:
                stale_warn_btotal = f' <span style="color:#7ee787">· {delta_txt}</span>'
    except Exception:
        pass
    header_atualizado = (f' · atualizado <b title="{esc(gerado_iso)}">{esc(gerado_txt)}</b> {stale_warn_btotal}'
                         if gerado_iso else "")

    html = (
        '<div class="bausect"><style>' + PROG_CSS + '</style><div class="bhead"><h2>💰 MEUS BAÚS — só vendáveis contam</h2>'
        '<div class="bsub2">' + str(n_ok) + "/" + str(n_todas)
        + " contas · clica num cartão para abrir o inventário dessa conta (só vendáveis no total) · "
        + ("<a class=\"ilink\" href=\"inventario.html\">abrir inventário geral</a> · " if tem_inv else "")
        + "só com oferta ativa no Mercado"
        + header_atualizado
        + stale_warn
        + extra + "</div></div>"
        + histo_html
        +        '<div class="btotal"><div class="blab">VALOR REAL VENDÁVEL (só com oferta agora)'
        + _badge_trend(histo_info, sim) + '</div>'
        '<div class="bnum">' + fmt_eur(tot_eur, d) + "</div>"
        '<div class="bsub"><b style="color:#7ee787">tu recebes ' + fmt_eur(tot_ganho_local, d)
        + "</b> depois das taxas (5% Steam + 10% do jogo) · " + str(n_ok)
        + " contas somadas (Deleted / Common / Uncommon / sem oferta NÃO contam) · " + fonte + " · "
        + esc(gerado_txt) + stale_warn_btotal + "</div></div>"
        '<div class="baugrid">' + "".join(cards) + "</div>"
        '<div class="bnote">Valor = só o que tem <b>oferta de venda ATIVA agora</b> no Mercado Steam (lowest_sell_order). '
        'Itens <b>Deleted</b> (removidos numa atualização), <b>Common/Uncommon</b> e itens sem vendedor valem 0 e não entram no total — '
        'vê o detalhe em <a class="ilink" href="inventario.html">inventario.html</a> na secção “NÃO VENDÁVEIS”. '
        'Para ranking: entra com essa conta Steam em <a class="ilink" href="https://tbhindex.com/pt/" target="_blank">tbhindex.com</a> e clica 🏆 → Atualizar Meu Ranking. '
        'Remedir: <span class="cmdtxt">python tbh_baus.py --medir</span></div></div>'
    )
    return html


# ---------------------------------------------------------------- medir (browser)

AB = "agent-browser"
SESS = "tbh-baus"


def _b64(js: str) -> str:
    import base64
    return base64.b64encode(js.encode("utf-8")).decode("ascii")


def _ab(*args, timeout=180):
    """Chama o agent-browser. Output via ficheiro (nao pipe) para evitar
    deadlock se o CLI/daemon herdar o handle do stdout."""
    import subprocess
    import shutil
    import tempfile
    exe = shutil.which("agent-browser") or "agent-browser"
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8", errors="replace") as out:
            subprocess.run([exe, "--session", SESS] + [str(a) for a in args],
                           stdout=out, stderr=subprocess.STDOUT, timeout=timeout,
                           stdin=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except Exception as e:
        return "(erro: " + str(e)[:80] + ")"
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


MEDIR_EVAL = r"""(()=>{const el=[...document.querySelectorAll('*')].find(e=>e.children.length===0&&/VALOR TOTAL/i.test(e.textContent));
const tabs=[...document.querySelectorAll('button')].filter(b=>/Geral \(/.test(b.innerText)).map(b=>b.innerText.trim());
const ms=[...performance.getEntriesByType('resource').map(e=>e.name).join(' ').matchAll(/player\/(\d{5,})/g)];
return JSON.stringify({total:el?el.parentElement.innerText.replace(/\n/g,'|'):'',tabs,sid:ms.length?ms[ms.length-1][1]:''})})()"""

MARCA_JS = "var i=document.querySelector('input[type=file]'); i?(i.id='saveinput','ok'):'sem input'"


def _marca_input(tentativas: int = 12) -> bool:
    """Espera a homepage ter o input de save e marca-o como #saveinput."""
    for _ in range(tentativas):
        r = _ab("eval", "-b", _b64(MARCA_JS), timeout=60)
        if "ok" in r and "sem input" not in r:
            return True
        _t_sleep(1.5)
    return False


def _t_sleep(s: float) -> None:
    time.sleep(s)


LOG_FILE = os.path.join(BASE, "baus_monitor.log")


def _log(msg: str) -> None:
    line = "[" + datetime.now().strftime("%d/%m %H:%M:%S") + "] " + msg
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def medir_todas() -> None:
    """Re-medir o VALOR TOTAL de cada conta carregando o save no site (sem login)."""
    if not _ciclo_livre(8):
        _log("outra medicao ja esta a correr — salto este ciclo")
        return
    try:
        _medir_todas_interno()
    finally:
        try:
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
        except Exception:
            pass


def _medir_todas_interno() -> None:
    import time as _t
    cfg = load_cfg()
    for c in cfg.get("contas", []):
        s = c.get("save", "")
        if s and not os.path.exists(s):
            _log("  ATENCAO: save da " + (c.get("nome") or "?") + " nao existe: " + s)
            _log("          (a sandbox mudou de nome?) — corrige o caminho no baus.json, senao esta conta fica com valores parados")
    contas = [c for c in cfg.get("contas", []) if c.get("save") and os.path.exists(c["save"])]
    if not contas:
        print("nenhuma conta com 'save' valido no baus.json")
        return
    print(_ab("open", "https://tbhindex.com/pt/") or "site aberto")
    _t.sleep(4)
    cache = load_cache()
    cache.setdefault("medicoes", {})
    for i, c in enumerate(contas, 1):
        if not _marca_input():
            print("  " + c["nome"] + ": input de save nao apareceu — salto")
            _ab("eval", "-b", _b64("location.href='https://tbhindex.com/pt/'"))
            _t_sleep(5)
            continue
        print(_ab("upload", "#saveinput", c["save"]))
        _t.sleep(10)
        raw = _ab("eval", "-b", _b64(MEDIR_EVAL), timeout=90)
        try:
            txt = raw.strip()
            if txt.startswith('"'):
                txt = json.loads(txt)
            m = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        except Exception:
            print("  " + c["nome"] + ": nao consegui ler (resposta: " + raw[:120] + ")")
            continue
        eur = 0.0
        try:
            eur = float(m.get("total", "").replace("VALOR TOTAL|", "")
                        .replace("€", "").replace("R$", "").replace(".", "").replace(",", ".").strip())
        except Exception:
            pass
        if eur <= 0.0:
            # pagina ainda a calcular? espera e le outra vez
            _t.sleep(4)
            raw2 = _ab("eval", "-b", _b64(MEDIR_EVAL), timeout=90)
            try:
                t2 = raw2.strip()
                if t2.startswith('"'):
                    t2 = json.loads(t2)
                m2 = json.loads(t2[t2.index("{"):t2.rindex("}") + 1])
                eur = float(m2.get("total", "").replace("VALOR TOTAL|", "")
                            .replace("€", "").replace("R$", "").replace(".", "").replace(",", ".").strip())
            except Exception:
                pass
        itens = 0
        try:
            itens = int((m.get("tabs") or [""])[0].split("(")[1].split(")")[0])
        except Exception:
            pass
        sid = m.get("sid") or str(c["id"])
        anterior = cache["medicoes"].get(str(sid)) or {}
        if eur <= 0.0 and float(anterior.get("eur") or 0.0) > 0.0:
            _log(f"  {i}/{len(contas)} {c['nome']}: leitura deu 0.00 (pagina nao processou?) — mantenho a medicao "
                 "anterior de {:.2f} EUR ({}) em vez de apagar com zero".format(
                     float(anterior.get("eur") or 0.0), str(anterior.get("quando") or "?")))
        else:
            cache["medicoes"][str(sid)] = {"eur": eur, "itens": itens,
                                           "quando": datetime.now().isoformat(timespec="seconds")}
            save_cache(cache)
            _log(f"  {i}/{len(contas)} {c['nome']}: {eur:.2f} EUR, {itens} itens (sid {sid})")
        _ab("eval", "-b", _b64("location.href='https://tbhindex.com/pt/'"))
        _t.sleep(5)
    save_cache(cache)
    _ab("close")
    print("medicoes gravadas. agora corre: python tbh_site.py")


# ---------------------------------------------------------------- monitor

HTML_OUT = os.path.join(BASE, "minhas_builds.html")


def markers_present() -> bool:
    return os.path.exists(HTML_OUT) and "<!--BAUS-START-->" in open(HTML_OUT, encoding="utf-8").read()


def atualizar_secao() -> bool:
    """Troca só a seção MEUS BAÚS no minhas_builds.html (sem refetch das builds)."""
    if not markers_present():
        return False
    doc = open(HTML_OUT, encoding="utf-8").read()
    novo = "<!--BAUS-START-->" + render_section() + "<!--BAUS-END-->"
    doc = re.sub(r"<!--BAUS-START-->.*?<!--BAUS-END-->", lambda m: novo, doc, flags=re.S)
    # linhas de recomendação clicáveis: injectar data-build (conta -> build)
    try:
        try:
            _urls = json.load(open(os.path.join(BASE, "builds.json"), encoding="utf-8-sig")).get("urls") or []
        except Exception:
            _urls = []
        from tbh_recomendar import ligar_builds
        doc = ligar_builds(doc, _urls)
    except Exception:
        pass
    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    return True


def atualizar_abas_upar() -> None:
    """Refresca o conteúdo das abas ⚡ UPAR JÁ no minhas_builds.html (plano da conta vs alvos da build).
    Os alvos por build vêm de tbhdata/alvos_builds.json (escrito na regeneração completa)."""
    try:
        import tbh_recomendar as tr
    except Exception:
        return
    alvos_c = tr._alvos_cache_load()
    if not alvos_c:
        return
    _saves = {c.get("nome"): c.get("save", "") for c in load_cfg().get("contas", [])}
    try:
        doc = open(HTML_OUT, encoding="utf-8").read()
    except Exception:
        return
    mudou = False
    for idx_s, info in alvos_c.items():
        conta = info.get("conta") or ""
        save = _saves.get(conta, "")
        if not save:
            continue
        try:
            plano = tr.plano_completo(save, info.get("alvos") or {})
            novo = (tr.aba_up_html(plano, conta))
        except Exception:
            continue
        novo = '<div class="uphead">' + esc(conta) + ' · ' + esc(plano.get("resumo", "")) + "</div>" + novo
        pat = re.compile(r'(id="uw' + re.escape(idx_s) + r'">).*?(<!--uw-end-->)', re.S)
        doc, n = pat.subn(lambda m: m.group(1) + novo + m.group(2), doc)
        if n:
            mudou = True
    if mudou:
        try:
            # reinjectar data-build (conta -> build) nas linhas novas
            try:
                _urls = json.load(open(os.path.join(BASE, "builds.json"), encoding="utf-8-sig")).get("urls") or []
            except Exception:
                _urls = []
            from tbh_recomendar import ligar_builds
            doc = ligar_builds(doc, _urls)
            with open(HTML_OUT, "w", encoding="utf-8") as f:
                f.write(doc)
            _log("abas UPAR JÁ atualizadas (" + str(len(alvos_c)) + " builds)")
        except Exception:
            pass


def atualizar_inventario() -> None:
    """Regenera o inventario.html no mesmo processo (sem abrir janela).
    Os preços têm cache de 30 min dentro do tbh_inventario, por isso num ciclo
    de 15 min só refresca a API de preços de 2 em 2 ciclos — poupa rede/CPU."""
    try:
        import tbh_inventario
        tbh_inventario.gerar_html()
        _log("  inventario.html atualizado (da F5 se estiver aberto)")
    except Exception as e:
        _log("  falha ao atualizar o inventario (" + str(e)[:120] + ")")


def _regen_builds() -> bool:
    """Regenera a dashboard completa (tbh_site.py --sem-abrir) com builds sincronizadas.
    Devolve True se correu sem excecao. Usado pelo monitor para manter TUDO novo."""
    try:
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(BASE, "tbh_site.py"), "--sem-abrir"],
                           check=False, timeout=180)
        return r.returncode == 0
    except Exception as e:
        _log("  falha ao regenerar builds (" + str(e)[:120] + ")")
        return False


def monitor(minutos: float = 15) -> None:
    """FARM ESTAVEL 15 MIN — como o antigo, mas com TUDO novo.
    - A cada ~2 min (rapido): saves locais -> baus vendaveis + progresso + UPAR JA + inventario (barato, sem rede).
    - A cada `minutos` (padrao 15): dashboard completa de builds (tbh_site) + medicao baus no browser.
    Nunca sai sozinho: qualquer excecao e logada e o ciclo recomeça em 30s.
    Ctrl+C ou fechar a janela para parar."""
    rapido = 2.0  # minutos entre leituras leves de save
    intervalo_builds = float(minutos)  # regenerar builds a cada 15 min tambem
    _log("MONITOR LIGADO — ciclo leve a cada " + str(int(rapido))
         + " min (saves locais) · ciclo completo (builds+baus) a cada " + str(int(minutos)) + " min")
    _log("  5 contas em baus.json · log em baus_monitor.log · deixa esta janela ABERTA")
    if not markers_present():
        _log("a gerar a dashboard uma vez para criar os marcadores...")
        _regen_builds()
    ciclo = 0
    ultima_medicao = datetime.min
    ultima_build = datetime.min
    while True:
        ciclo += 1
        try:
            # ---- ciclo rapido: estado local em tempo (quase) real — barato
            _log("ciclo " + str(ciclo) + ": a ler os saves (progresso + recomendacoes)...")
            try:
                # regenera builds de tempos a tempos (pesado, mas garante skills/runas sempre certas)
                if (datetime.now() - ultima_build).total_seconds() >= intervalo_builds * 60:
                    _log("  a regenerar builds sincronizadas (a cada " + str(int(intervalo_builds)) + " min)...")
                    if _regen_builds():
                        ultima_build = datetime.now()
                        _log("  builds regeneradas")
                    else:
                        _log("  builds falharam — tento outra vez no proximo ciclo")
                if not atualizar_secao():
                    _log("  marcadores em falta — a regenerar dashboard completa...")
                    if _regen_builds():
                        ultima_build = datetime.now()
                    else:
                        import subprocess
                        subprocess.run([sys.executable, os.path.join(BASE, "tbh_site.py")], check=False)
                else:
                    _log("  minhas_builds.html atualizado (da F5 se estiver aberto)")
                atualizar_abas_upar()
                atualizar_inventario()
            except Exception as e:
                _log("  falha ao atualizar o HTML (" + str(e)[:140] + ")")
            # ---- ciclo lento: medir os baús no browser (opcional, se tiver saves)
            if ciclo == 1 or (datetime.now() - ultima_medicao).total_seconds() >= minutos * 60:
                _log("  a medir os baús no site (a cada " + str(int(minutos)) + " min)...")
                try:
                    medir_todas()
                    ultima_medicao = datetime.now()
                    if atualizar_secao():
                        atualizar_abas_upar()
                        atualizar_inventario()
                except Exception as e:
                    _log("  medicao falhou (" + str(e)[:140] + ") — tento outra vez no proximo ciclo")
            nxt = datetime.now() + timedelta(minutes=rapido)
            _log("  proximo ciclo as " + nxt.strftime("%H:%M"))
            time.sleep(rapido * 60)
        except KeyboardInterrupt:
            _log("monitor parado (Ctrl+C).")
            return
        except Exception as e:
            _log("ERRO no ciclo " + str(ciclo) + ": " + str(e)[:200] + " — recomeço em 30s")
            try:
                time.sleep(30)
            except KeyboardInterrupt:
                _log("monitor parado.")
                return


# ---------------------------------------------------------------- cli

LOCK_FILE = os.path.join(BASE, "baus_monitor.lock")


def _ciclo_livre(idade_max_min: float = 8) -> bool:
    """Devolve True se puder comecar um ciclo agora (e cria o lock)."""
    if os.path.exists(LOCK_FILE) and time.time() - os.path.getmtime(LOCK_FILE) < idade_max_min * 60:
        return False
    try:
        open(LOCK_FILE, "w").write(str(time.time()))
    except Exception:
        pass
    return True


def ciclo_agora(abrir: bool = True) -> None:
    """Mede tudo, atualiza secao da dashboard + abas UPAR JÁ + inventario e (opcional) abre."""
    medir_todas()
    if atualizar_secao():
        print("minhas_builds.html atualizado", flush=True)
    else:
        print("marcadores em falta — corre python tbh_site.py", flush=True)
    atualizar_abas_upar()
    atualizar_inventario()
    if abrir:
        try:
            os.startfile(HTML_OUT)
        except Exception:
            pass


def cli() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = sys.argv[1:]
    cfg = load_cfg()
    if not a or a[0] == "--list":
        print("moeda: " + cfg.get("moeda", "EUR"))
        for i, c in enumerate(cfg.get("contas", []), 1):
            print(f"  {i}. {c.get('nome','?')}  (id: {c.get('id','?')})")
        if not cfg.get("contas"):
            print("  (nenhuma conta) — adiciona com: python tbh_baus.py --add NICK_OU_STEAMID")
        return
    if a[0] == "--add" and len(a) > 1:
        idente = a[1].strip()
        try:
            r = resolver(idente)
            sid, user = str(r.get("steamId") or idente), r.get("username") or idente
        except Exception as e:
            print("ERRO: nao encontrei essa conta no tbhindex.com (" + str(e)[:100] + ")")
            print("       importa primeiro o save dela no site (Inspecionar Seu Baú)")
            return
        nome = None
        if "--nome" in a and a.index("--nome") + 1 < len(a):
            nome = a[a.index("--nome") + 1]
        cfg.setdefault("contas", []).append({"nome": nome or user, "id": user})
        save_cfg(cfg)
        print("conta adicionada: " + (nome or user) + " (steam_id " + sid + ")")
        print("agora corre: python tbh_site.py")
    elif a[0] == "--rm" and len(a) > 1:
        t = a[1].strip().lower()
        antes = len(cfg.get("contas", []))
        cfg["contas"] = [c for c in cfg.get("contas", [])
                         if str(c.get("id", "")).lower() != t and str(c.get("nome", "")).lower() != t]
        if len(cfg["contas"]) == antes:
            print("nao encontrei: " + t)
        else:
            save_cfg(cfg)
            print("removida: " + t)
    elif a[0] == "--moeda" and len(a) > 1:
        cfg["moeda"] = a[1].upper()
        save_cfg(cfg)
        print("moeda: " + cfg["moeda"])
    elif a[0] == "--discord" and len(a) > 1:
        u = a[1].strip()
        if not u.startswith(("http://", "https://")):
            print("ERRO: esse URL nao parece um webhook (tem de comecar por http(s)://)")
            return
        cfg["discord"] = u
        save_cfg(cfg)
        print("webhook do Discord guardado. Testa com: python tbh_baus.py --teste-discord")
    elif a[0] == "--sem-discord":
        cfg.pop("discord", None)
        save_cfg(cfg)
        print("webhook do Discord removido")
    elif a[0] == "--teste-discord":
        emb = {"title": "✅ Monitor TBH ligado a este canal",
               "color": 0x3FB950,
               "description": "Vou avisar aqui: 📈/📉 variações fortes do total dos baús "
                              "e ⭐ itens que valem a pena vender já (>= "
                              + _fmt_euro(float(cfg.get("alerta_min") or 0.8))
                              + " e que vendem em <= " + str(int(float(cfg.get("alerta_dias") or 1.0)))
                              + " dia(s)). Mesmo item não repete em 24h.",
               "footer": {"text": "Monitor TBH · " + datetime.now().strftime("%d/%m %H:%M")}}
        ok, msg = discord_enviar({"embeds": [emb]})
        print("Discord: " + ("ENVIADO ✔" if ok else "FALHOU — " + msg))
    elif a[0] == "--alerta-min" and len(a) > 1:
        try:
            cfg["alerta_min"] = max(0.01, float(a[1].replace(",", ".")))
            save_cfg(cfg)
            print("alerta_min: " + _fmt_euro(cfg["alerta_min"]))
        except ValueError:
            print("ERRO: valor invalido (ex.: 0.80)")
    elif a[0] == "--alerta-dias" and len(a) > 1:
        try:
            cfg["alerta_dias"] = max(0.2, float(a[1].replace(",", ".")))
            save_cfg(cfg)
            print("alerta_dias: " + str(cfg["alerta_dias"]))
        except ValueError:
            print("ERRO: valor invalido (ex.: 1)")
    elif a[0] == "--sem-alertas":
        cfg["sem_alertas"] = True
        save_cfg(cfg)
        print("alertas desligados (usa --moeda/--discord normalmente; para voltar: apaga 'sem_alertas' do baus.json)")
    elif a[0] == "--medir":
        medir_todas()
    elif a[0] == "--agora":
        ciclo_agora(abrir=("--silencioso" not in a and "--sem-abrir" not in a))
    elif a[0] == "--abrir":
        # rapido: valores vendaveis vem dos saves locais + cache de precos (sem browser)
        silencioso = "--silencioso" in a or "--sem-abrir" in a
        if atualizar_secao():
            print("minhas_builds.html atualizado", flush=True)
        else:
            print("marcadores em falta — a regenerar dashboard completa (tbh_site.py)...", flush=True)
            import subprocess
            args2 = [sys.executable, os.path.join(BASE, "tbh_site.py")]
            if silencioso:
                args2.append("--sem-abrir")
            subprocess.run(args2, check=False)
            return  # tbh_site.py ja abre a pagina (ou nao, se silencioso)
        try:
            atualizar_abas_upar()
        except Exception:
            pass
        atualizar_inventario()
        if not silencioso:
            try:
                os.startfile(HTML_OUT)
            except Exception:
                pass
    elif a[0] == "--atualizar":
        # usado pelo farm em ciclo: atualiza baús/UPAR JÁ/inventário SEM abrir browser e SEM medir via site
        if atualizar_secao():
            print("minhas_builds.html atualizado", flush=True)
        else:
            print("marcadores em falta — a regenerar dashboard completa (tbh_site.py --sem-abrir)...", flush=True)
            import subprocess
            subprocess.run([sys.executable, os.path.join(BASE, "tbh_site.py"), "--sem-abrir"], check=False)
            # depois de regenerar já está atualizado, só falta inventário
        try:
            atualizar_abas_upar()
        except Exception:
            pass
        atualizar_inventario()
    elif a[0] == "--monitor":
        m = 15.0
        if len(a) > 1:
            try:
                m = max(5.0, float(a[1]))
            except ValueError:
                pass
        try:
            monitor(m)
        except KeyboardInterrupt:
            print("monitor parado.")
    else:
        print(__doc__)


if __name__ == "__main__":
    cli()
