r"""INVENTARIO COMPLETO - abre o save local de cada conta e mostra tudo o que
da para vender, com precos do Mercado Steam em tempo real.

  - le o SaveFile_Live.es3 de cada conta (baus.json) sem precisar do jogo
  - precos: api.tbhindex.com/api/items (menor venda, maior compra, mediana, volume)
  - "Cliente paga" = preco atual da listagem mais barata no Mercado
  - "Eu ganho" = o que cai na carteira Steam depois das taxas (5% Steam + 10% do
    jogo, cada uma com minimo de 1 centavo — mesma formula que o site usa)
  - link direto para vender cada item no Mercado Steam
  - ordenador: mais caro -> mais barato, tempo de venda, quantidade, nome
  - PESQUISA EXTENSA: apos atualizacoes muitos itens ficaram nao-negociaveis
    (Common/Uncommon, Deleted, sem oferta). So itens com oferta ATIVA no
    Mercado contam para o TOTAL do bau. Os outros aparecem em secao separada.

Gera inventario.html. CLI:
  python tbh_inventario.py            # tudo + abre a pagina
  python tbh_inventario.py --conta 3  # so uma conta (1..N)
  python tbh_inventario.py --so-html  # regenera a pagina com precos em cache
"""

import gzip
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
def _resolve(*parts):
    p = os.path.join(ROOT, *parts)
    if os.path.exists(p): return p
    for alt in [os.path.join(ROOT, parts[-1]), os.path.join(BASE, *parts)]:
        if os.path.exists(alt): return alt
    return p
OUT_HTML = os.path.join(ROOT, "inventario.html")
PRECO_CACHE = _resolve("data", "tbhdata", "precos_cache.json")
if not os.path.exists(PRECO_CACHE):
    for alt in [os.path.join(ROOT, "tbhdata", "precos_cache.json"), os.path.join(BASE, "tbhdata", "precos_cache.json")]:
        if os.path.exists(alt): PRECO_CACHE = alt; break
API_ITEMS = "https://api.tbhindex.com/api/items"
MARKET_URL = "https://steamcommunity.com/market/listings/3678970/"
PRECO_TTL = 30 * 60  # 30 min

# ------------------------------------------------------- decrypt do save ES3

PW = b"emuMqG3bLYJ938ZDCfieWJ"
GRADE = {"COM": "Common", "UNC": "Uncommon", "RAR": "Rare", "LEG": "Legendary",
         "IMM": "Immortal", "ARC": "Arcana", "BEY": "Beyond", "CEL": "Celestial",
         "DIV": "Divine", "COS": "Cosmic"}

MOEDA_SEM_CENTAVOS = {"JPY"}  # iene nao tem casas decimais


def _es3_decrypt(path: str) -> dict:
    """Desencripta um save .es3 (Easy Save 3) -> dicionario do PlayerSaveData."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    raw = open(path, "rb").read()
    salt = raw[:16]
    key = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=salt,
                     iterations=100).derive(PW)
    dec = Cipher(algorithms.AES(key), modes.CBC(salt)).decryptor()
    out = dec.update(raw[16:]) + dec.finalize()
    if out[:2] == b"\x1f\x8b":
        out = gzip.decompress(out)
    txt = out.decode("utf-8", "replace").split("\x00")[0]
    d, _ = json.JSONDecoder().raw_decode(txt)
    return json.loads(d["PlayerSaveData"]["value"])


# ------------------------------------------------------- dados do jogo

def _json_de_js(conteudo: str, comeca_com: str) -> dict:
    i = conteudo.find(comeca_com)
    if i < 0:
        return {}
    ini = conteudo.rfind("JSON.parse(`", 0, i) + len("JSON.parse(`")
    fim = conteudo.find("`)", ini)
    return json.loads(conteudo[ini:fim])


def carregar_dados_jogo() -> dict:
    """Nomes e grades dos itens a partir dos dados do site (pasta tbhdata)."""
    nomes, gear = {}, {}
    f = _resolve("data", "tbhdata", "tbhNames-Di6BnslN.js")
    if not os.path.exists(f):
        for alt in [os.path.join(ROOT, "tbhdata", "tbhNames-Di6BnslN.js"), os.path.join(BASE, "tbhdata", "tbhNames-Di6BnslN.js")]:
            if os.path.exists(alt): f = alt; break
    _f_tmp = f
    if os.path.exists(f):
        m = re.search(r"JSON\.parse\(`(\{.*?\})`\)",
                      open(f, encoding="utf-8", errors="replace").read(), re.S)
        if m:
            nomes = json.loads(m.group(1))
    f = _resolve("data", "tbhdata", "game-data-qWh3M14n.js")
    if not os.path.exists(f):
        for alt in [os.path.join(ROOT, "tbhdata", "game-data-qWh3M14n.js"), os.path.join(BASE, "tbhdata", "game-data-qWh3M14n.js")]:
            if os.path.exists(alt): f = alt; break
    if os.path.exists(f):
        gear = _json_de_js(open(f, encoding="utf-8", errors="replace").read(),
                           '"503051":{"g"')
    if not nomes or not gear:
        raise SystemExit("falta tbhdata/tbhNames-Di6BnslN.js ou game-data-qWh3M14n.js")
    return {"nomes": nomes, "gear": gear}


def nome_de_mercado(itemkey: int, dados: dict, nomes_mercado=None):
    """ItemKey -> nome no Mercado Steam (ou None se desconhecido/deleted).
    nomes_mercado = conjunto de nomes com preço conhecido; serve para detetar
    materiais (que se vendem pelo nome simples, sem grade nem variante A/B)."""
    k = str(itemkey)
    info = dados["gear"].get(k)
    base = dados["nomes"].get(k)
    if not info or not base:
        return None
    g = GRADE.get(info.get("g"), info.get("g"))
    var = "A" if k[-1] in "13579" else "B"
    completo = base + " (" + g + ") " + var
    if info.get("tp") == "MATERIAL":
        return base
    if nomes_mercado is not None and completo not in nomes_mercado and base in nomes_mercado:
        return base  # material sem flag MATERIAL (ingots, gemas, soulstones...)
    return completo


# ------------------------------------------------------- precos

def precos_frescos() -> dict:
    """{nome: {sell, buy, med, vol}} com cache de 30 min (precos em USD)."""
    if os.path.exists(PRECO_CACHE):
        try:
            c = json.load(open(PRECO_CACHE, encoding="utf-8"))
            if c.get("t", 0) + PRECO_TTL > datetime.now().timestamp():
                return c["itens"]
        except Exception:
            pass
    req = urllib.request.Request(API_ITEMS, headers={"User-Agent": "Mozilla/5.0"})
    items = json.loads(urllib.request.urlopen(req, timeout=30).read().decode()).get("items", [])
    out = {}
    for i in items:
        n = i.get("market_hash_name")
        if not n:
            continue
        out[n] = {
            "sell": i.get("lowest_sell_order"),
            "buy": i.get("highest_buy_order"),
            # median_price vem na moeda interna do site (x~5.59); x0.179 -> USD
            "med": (float(i["median_price"]) * 0.179) if i.get("median_price") else None,
            "vol": int(str(i.get("volume") or "0").replace(",", "") or 0),
            "hist": int(str(i.get("historical_volume") or "0").replace(",", "") or 0),
        }
    try:
        json.dump({"t": datetime.now().timestamp(), "itens": out},
                  open(PRECO_CACHE, "w", encoding="utf-8"))
    except Exception:
        pass
    return out


def _eh_vendavel(nome: str, precos: dict) -> bool:
    """Vendavel = tem oferta ATIVA agora no Mercado (lowest_sell_order != None)."""
    p = precos.get(nome)
    return bool(p and p.get("sell") not in (None, 0, 0.0, ""))


def _motivo_nao_vendavel(itemkey: int, nome, dados: dict, precos: dict) -> str:
    """Explica porque um item nao conta para o valor do bau."""
    # Deleted / ItemKey desconhecido apos update
    if nome is None:
        # tenta dar informacao extra sobre o ItemKey
        k = str(itemkey)
        info = dados["gear"].get(k)
        base = dados["nomes"].get(k)
        if not info and not base:
            return "Item removido (Deleted) — ItemKey " + k + " não existe nos dados atuais do jogo"
        if not base:
            return "Item removido (Deleted) — sem nome nos dados atuais"
        if not info:
            return "Item removido (Deleted) — sem grade/tipo nos dados atuais"
        return "Deleted — dados incompletos"
    k = str(itemkey)
    info = dados["gear"].get(k) or {}
    g = info.get("g")
    # Common / Uncommon gear nunca foi negociável
    if info.get("tp") != "MATERIAL" and g in ("COM", "UNC"):
        grade_pt = GRADE.get(g, g)
        return grade_pt + " — nunca foi negociável no Steam (Common/Uncommon não lista)"
    if info.get("nm"):
        return "Marcado como não-negociável (nm) nos dados do jogo"
    if info.get("l") is not None and info.get("l") > 90:
        return "Nível " + str(info.get("l")) + " — acima do limite de mercado (>90)"
    # fallthrough: checar mercado
    if nome not in precos:
        return "Sem página no Mercado (nunca listado / removido)"
    p = precos.get(nome)
    if not p:
        return "Sem dados de mercado"
    if not p.get("sell"):
        if p.get("hist"):
            return "Sem oferta ativa agora — ninguém a vender (já vendeu antes)"
        if p.get("med"):
            return "Sem oferta ativa — sem vendedor atual"
        return "Sem oferta ativa no Mercado"
    return "Não vendável"


# ------------------------------------------------------- taxas steam (cliente paga -> eu ganho)

def _para_centavos(v_usd: float, rate: float, moeda: str) -> int:
    """USD -> unidade menor da moeda local (centavos; iene = unidade inteira)."""
    if moeda in MOEDA_SEM_CENTAVOS:
        return max(1, round(v_usd * rate))
    return max(1, round(v_usd * rate * 100))


def eu_ganho_cent(paga_cent: int) -> int:
    """O que fica na carteira Steam quando o cliente paga `paga_cent`.
    Algoritmo exato do site (mesmo do Mercado Steam): procura o valor que o
    vendedor recebe tal que valor + taxas = preco do cliente, com
    taxa Steam 5% e taxa do jogo 10%, cada uma com minimo de 1 centavo
    e arredondada para baixo."""
    if paga_cent <= 0:
        return 0

    def taxas(n: int) -> int:
        steam = int(max(n * 0.05, 1))
        jogo = int(max(n * 0.10, 1))
        return steam + jogo

    n = int(paga_cent / 1.15)
    subiu = False
    passos = 0
    while n + taxas(n) != paga_cent and passos < 10:
        if n + taxas(n) > paga_cent:
            if subiu:
                # nao ha valor exato: o vendedor fica com n-1 e a diferenca conta como taxa
                return n - 1
            n -= 1
        else:
            subiu = True
            n += 1
        passos += 1
    return n


# ------------------------------------------------------- coleta por conta

def _save_legivel(save_path: str) -> str:
    """Devolve o caminho do save MAIS RECENTE que se consiga desencriptar.
    Enquanto o jogo esta aberto, o SaveFile_Live.es3 pode estar a meio de uma
    gravacao (ou ser mais velho que o ultimo backup) — testamos o principal e
    os .bak por ordem de mtime e devolvemos o primeiro que abre."""
    pasta = os.path.dirname(save_path)
    cand = []
    if os.path.exists(save_path):
        cand.append(save_path)
    try:
        baks = [os.path.join(pasta, f) for f in os.listdir(pasta)
                if f.startswith("SaveFile_Live") and f.endswith(".bak")]
        baks.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        cand.extend(baks)
    except Exception:
        pass
    for p in cand:
        try:
            _es3_decrypt(p)
            return p
        except Exception:
            continue
    return save_path


def itens_da_conta(save_path: str, dados: dict, nomes_mercado=None) -> dict:
    """Le o save e devolve {nome: qtd} dos itens vendaveis (bau + mochila).
    Compativel: só os conhecidos (deleted são ignorados)."""
    cont, _del, _mot = itens_da_conta_detalhado(save_path, dados, nomes_mercado)
    return dict(cont)


def _itens_do_save_data(p: dict, dados: dict, nomes_mercado=None):
    por_uid = {i.get("UniqueId"): i for i in p.get("itemSaveDatas", [])}
    equipados = set()
    for h in p.get("heroSaveDatas", []):
        for uid in (h.get("equippedItemIds") or []):
            if uid:
                equipados.add(uid)
    cont = Counter()
    del_cont = Counter()
    for zona in ("stashSaveDatas", "inventorySaveDatas"):
        for slot in p.get(zona, []):
            uid = slot.get("ItemUniqueId")
            if not uid or uid in equipados:
                continue
            it = por_uid.get(uid)
            if not it:
                continue
            ik = it.get("ItemKey")
            nm = nome_de_mercado(ik, dados, nomes_mercado)
            if nm:
                cont[nm] += 1
            else:
                # Deleted / ItemKey obsoleto apos update
                del_cont[str(ik)] += 1
    return cont, del_cont


def itens_da_conta_detalhado(save_path: str, dados: dict, nomes_mercado=None):
    """Le o save e devolve quantidades conhecidas e ItemKeys Deleted/desconhecidos."""
    p = _es3_decrypt(_save_legivel(save_path))
    return _itens_do_save_data(p, dados, nomes_mercado)


def itens_da_conta_com_zona(save_path: str, dados: dict, nomes_mercado=None):
    """Lê itens e zona do mesmo save para a vigia não o desencriptar novamente."""
    p = _es3_decrypt(_save_legivel(save_path))
    itens, deleted = _itens_do_save_data(p, dados, nomes_mercado)
    return itens, deleted, _zona_do_save_data(p)


def resumo_vendavel(save_path: str, dados: dict, precos: dict):
    """Calcula resumo vendável para o bau: so o que tem venda ativa conta.
    Retorna dict com totais e contagens.
    """
    nomes_mercado = set(precos)
    cont, del_cont = itens_da_conta_detalhado(save_path, dados, nomes_mercado)
    # precisamos também do ItemKey por nome para motivo; reconstruimos mapa nome->exemplo ItemKey
    # Para simplificar, pegamos qualquer ItemKey que gere aquele nome
    nome_para_key = {}
    # varre save de novo para mapear (custo aceitavel; saves são pequenos)
    try:
        p = _es3_decrypt(_save_legivel(save_path))
        por_uid = {i.get("UniqueId"): i for i in p.get("itemSaveDatas", [])}
        equipados = set()
        for h in p.get("heroSaveDatas", []):
            for uid in (h.get("equippedItemIds") or []):
                if uid:
                    equipados.add(uid)
        for zona in ("stashSaveDatas", "inventorySaveDatas"):
            for slot in p.get(zona, []):
                uid = slot.get("ItemUniqueId")
                if not uid or uid in equipados:
                    continue
                it = por_uid.get(uid)
                if not it:
                    continue
                ik = it.get("ItemKey")
                nm = nome_de_mercado(ik, dados, nomes_mercado)
                if nm and nm not in nome_para_key:
                    nome_para_key[nm] = ik
    except Exception:
        pass

    vend = {}
    nao = {}
    for nm, qtd in cont.items():
        if _eh_vendavel(nm, precos):
            vend[nm] = qtd
        else:
            ik = nome_para_key.get(nm, 0)
            nao[nm] = (qtd, _motivo_nao_vendavel(ik, nm, dados, precos))

    # deleted são todos nao vendaveis
    motivos_del = {}
    for ik_str, qtd in del_cont.items():
        try:
            ik = int(ik_str)
        except Exception:
            ik = ik_str
        motivos_del["Deleted ItemKey " + str(ik_str)] = (qtd, _motivo_nao_vendavel(ik, None, dados, precos))

    return {
        "vendaveis": vend,
        "nao_vendaveis": nao,
        "deleted": motivos_del,
        "cont_total": cont,
        "del_cont": del_cont,
    }


# ------------------------------------------------------- oportunidades
OPP_MIN_CENT = 80  # cliente paga pelo menos isto (0,80 EUR na moeda configurada)
OPP_DIAS_MAX = 1.0  # e vende-se em no maximo ~1 dia (qtd/volume)


def _eh_oportunidade(paga_c: int, dias: float) -> bool:
    """Raro e liquido: paga >= OPP_MIN_CENT e vende-se em <= OPP_DIAS_MAX dias."""
    return paga_c >= OPP_MIN_CENT and dias <= OPP_DIAS_MAX


def _painel_oportunidades(todas: list, sim: str, sem_cent: bool) -> str:
    """Painel global com os melhores itens de todas as contas.
    todas = [(idx_conta, nome, qtd, paga_c, ganho_c, dias)].
    Com itens ao limiar: "VALE A PENA VENDER JÁ". Sem nenhum: mostra os melhores
    que vendem rapido (para nao ficar um painel vazio sem utilidade)."""
    if not todas:
        return ""
    estritas = [t for t in todas if _eh_oportunidade(t[3], t[5])]
    if estritas:
        itens = sorted(estritas, key=lambda t: -(t[4] * t[2]))[:12]
        titulo = ('⭐ VALE A PENA VENDER JÁ — raros com comprador à espera (ganho >= '
                  + fmt_cent(OPP_MIN_CENT, sim, sem_cent) + " e vende em <= 1 dia)")
    else:
        itens = sorted((t for t in todas if t[5] <= OPP_DIAS_MAX),
                       key=lambda t: -(t[4] * t[2]))[:6]
        if not itens:
            return ""
        titulo = ('⭐ Nenhum item >= ' + fmt_cent(OPP_MIN_CENT, sim, sem_cent)
                  + " agora — os melhores que vendem rápido (o Discord avisa quando aparecer um)")
    linhas = []
    for idx, nm, qtd, paga_c, ganho_c, dias in itens:
        dtxt = "~<1 dia" if dias < 1 else "~" + str(int(dias + 0.5)) + " dias"
        link = MARKET_URL + urllib.parse.quote(nm)
        est = "⭐ " if _eh_oportunidade(paga_c, dias) else "· "
        linhas.append(
            '<div class="opp-item">' + est + '<a href="' + link + '" target="_blank">' + esc(nm)
            + "</a> ×" + str(qtd) + " → <b>" + fmt_cent(ganho_c * qtd, sim, sem_cent)
            + '</b> <span class="oppsub">(\u2039' + fmt_cent(ganho_c, sim, sem_cent).replace(sim, sim + " ", 1).strip()
            + "/item · vende em " + dtxt + ' · </span><a href="#conta-' + str(idx) + '" class="opplink">conta '
            + str(idx) + "</a><span class=\"oppsub\">)</span></div>")
    return (
        '<div class="opp-card"><div class="opp-head">' + titulo + "</div>"
        + "".join(linhas)
        + '<div class="oppsub" style="margin-top:6px">Mesmo item não repete no Discord em 24h · '
          'configura o webhook com <b>python tbh_baus.py --discord URL</b></div></div>')


# ------------------------------------------------------- formato

def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _fmt_num(v: float) -> str:
    s = "{:,.2f}".format(v)
    if "." in s:  # pt-PT: 1.234,56
        s = s.replace(",", "\xa7").replace(".", ",").replace("\xa7", ".")
    return s


def fmt_cent(cent: int, sim: str, sem_cent: bool = False) -> str:
    v = cent if sem_cent else cent / 100.0
    return sim + _fmt_num(v)


def fmt_data(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%d/%m %H:%M")
    except Exception:
        return str(iso)[:16].replace("T", " ")


# ------------------------------------------------------- html

CSS = """
:root{--bg:#0d1117;--card:#161b22;--borda:#30363d;--txt:#e6edf3;--sub:#8b949e;
--verde:#3fb950;--azul:#58a6ff;--amarelo:#d29922;--verm:#f85149;--laranja:#f08833}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.45 'Segoe UI',system-ui,sans-serif;padding:24px}
h1{font-size:22px;margin:0 0 4px}
sub2{color:var(--sub);font-size:12.5px;display:block;margin-bottom:18px}
.barra{display:flex;gap:10px;align-items:center;margin:14px 0 20px;flex-wrap:wrap}
#filtro{background:var(--card);border:1px solid var(--borda);color:var(--txt);
border-radius:8px;padding:9px 12px;font-size:14px;width:300px;outline:none}
#filtro:focus{border-color:var(--azul)}
#ordenar{background:var(--card);border:1px solid var(--borda);color:var(--txt);
border-radius:8px;padding:9px 10px;font-size:13.5px;outline:none}
#limpar{background:var(--card);border:1px solid var(--borda);color:var(--sub);
border-radius:8px;padding:9px 12px;font-size:13px;cursor:pointer;outline:none}
#limpar:hover{color:var(--txt);border-color:var(--azul)}
.conta{background:var(--card);border:1px solid var(--borda);border-radius:12px;margin-bottom:18px;overflow:hidden}
.conta.foco{outline:2px solid var(--azul);box-shadow:0 0 18px #58a6ff33}
.ch{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;cursor:pointer;user-select:none;gap:10px;flex-wrap:wrap}
.ch:hover{background:#1c2330}
.cnome{font-weight:600;font-size:15px}
.ctotal{font-size:17px;font-weight:700;color:var(--verde);white-space:nowrap}
.crecebes{font-size:13px;color:var(--sub);white-space:nowrap}
.crecebes b{color:var(--verde)}
.cinfo{color:var(--sub);font-size:12px;white-space:nowrap}
.cinfo b{color:var(--txt)}
.badge{display:inline-block;font-size:11px;font-weight:700;padding:2px 7px;border-radius:999px;border:1px solid var(--borda);margin-left:6px}
.badge.ok{color:var(--verde);border-color:#238636;background:#0f2412}
.badge.warn{color:var(--amarelo);border-color:#8a6a0a;background:#2a2200}
.badge.neutro{color:var(--sub);border-color:var(--borda);background:#1a1f28}
.corpo{padding:0 10px 10px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{color:var(--sub);text-align:right;font-weight:600;padding:7px 10px;border-bottom:1px solid var(--borda);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
td{padding:6px 10px;border-bottom:1px solid #21262d;text-align:right;white-space:nowrap}
tr:hover td{background:#1c2330}
td.item a{color:var(--azul);text-decoration:none}
td.item a:hover{text-decoration:underline}
td.ganho{color:var(--verde);font-weight:600}
.vender{color:var(--verde);text-decoration:none;font-weight:600;font-size:12.5px;border:1px solid #238636;
border-radius:6px;padding:3px 9px;display:inline-block}
.vender:hover{background:#238636;color:#fff}
.med{color:var(--amarelo)}
.sem{color:var(--sub)}
.dias{color:var(--sub)}
.dias.lento{color:var(--verm)}
.total td{font-weight:700;color:var(--verde);border-top:2px solid var(--borda)}
.total .crec{color:var(--azul)}
.warn{background:#3d2e00;border:1px solid var(--amarelo);color:#e3b341;border-radius:10px;padding:10px 14px;margin-bottom:14px;font-size:13px}
.ok{color:var(--verde)}
.nao{margin:10px 0 6px;border:1px dashed #3a3f47;border-radius:10px;overflow:hidden;background:#10141c}
.nao summary{padding:10px 14px;cursor:pointer;user-select:none;color:var(--amarelo);font-weight:600;list-style:none}
.nao summary::-webkit-details-marker{display:none}
.nao summary:hover{background:#1a2330}
.nao table{font-size:12.5px}
.nao td{color:var(--sub)}
.nao td.item{color:var(--txt)}
.nao .motivo{color:var(--laranja);font-size:11.5px;white-space:normal;max-width:360px;text-align:left}
.opp-card{background:#14210f;border:1px solid #2f7a2f;border-radius:12px;padding:12px 16px;margin-bottom:16px}
.opp-head{color:#7ee787;font-weight:800;font-size:14px;margin-bottom:8px;letter-spacing:.5px}
.opp-item{font-size:13.5px;padding:4px 0;border-bottom:1px dashed #1f3a1f;line-height:1.5}
.opp-item:last-of-type{border-bottom:none}
.opp-item a{color:#7ee787;text-decoration:none}
.opp-item a:hover{text-decoration:underline}
.oppsub{color:var(--sub);font-size:11.5px}
.opplink{color:var(--azul);text-decoration:none;font-size:11.5px}
.opplink:hover{text-decoration:underline}
footer{color:var(--sub);font-size:12px;margin-top:8px;line-height:1.6}
a.ilink{color:var(--azul);text-decoration:none}
a.ilink:hover{text-decoration:underline}
"""

JS = r"""
// ---------- filtro ----------
const f=document.getElementById('filtro');
let filtroAtual='';
f.addEventListener('input',()=>{
  filtroAtual=f.value.trim().toLowerCase();
  aplicarFiltro();
});
function aplicarFiltro(){
  // esconder linhas individuais; as total/continuam sempre visiveis
  document.querySelectorAll('table tbody tr').forEach(tr=>{
    if(tr.classList.contains('total'))return;
    if(!filtroAtual){tr.style.display='';return;}
    tr.style.display=tr.textContent.toLowerCase().includes(filtroAtual)?'':'none';
  });
  // cabeçalhos por conta (badges) ficam sempre; contas só somem se NADA corresponder
  document.querySelectorAll('.conta').forEach(c=>{
    const vis=[...c.querySelectorAll('tr[data-filtravel="1"]')].some(tr=>tr.style.display!=='none');
    c.style.display=vis?'':'none';
  });
}

// ---------- ordenacao (só vendáveis) ----------
const CHAVES={
  valor:{k:tr=>-Number(tr.dataset.val||0)},
  ganho:{k:tr=>-Number(tr.dataset.ganho||0)},
  tempo:{k:tr=>Number(tr.dataset.dias||9999)},
  qtd:{k:tr=>-Number(tr.dataset.qtd||0)},
  nome:{k:tr=>(tr.dataset.nome||'').toLowerCase()}
};
function ordenar(){
  const modo=CHAVES[document.getElementById('ordenar').value]||CHAVES.valor;
  document.querySelectorAll('table.vend tbody').forEach(tb=>{
    const total=tb.querySelector('tr.total');
    const rows=[...tb.querySelectorAll('tr[data-filtravel="1"]')];
    rows.sort((a,b)=>{
      const ka=modo.k(a),kb=modo.k(b);
      const r=(typeof ka==='string')?ka.localeCompare(kb,'pt'):(ka-kb);
      return r!==0?r:String(a.dataset.nome).localeCompare(String(b.dataset.nome),'pt');
    });
    rows.forEach(tr=>tb.insertBefore(tr,total));
  });
}
document.getElementById('ordenar').addEventListener('change',ordenar);
ordenar();

// abre so a conta pedida no link (ex.: inventario.html#conta-2) e faz scroll ate ela
function focarConta(){
  const m=location.hash.match(/conta-(\d+)/);
  document.querySelectorAll('.conta').forEach(c=>{
    c.open = m ? (c.id==='conta-'+m[1]) : true;
    c.classList.remove('foco');
  });
  if(m){
    const el=document.getElementById('conta-'+m[1]);
    if(el){ el.classList.add('foco'); el.scrollIntoView({behavior:'smooth',block:'start'}); }
  }
}
window.addEventListener('hashchange',focarConta);
focarConta();
document.getElementById('limpar').addEventListener('click',()=>{f.value='';filtroAtual='';aplicarFiltro();f.focus();});
"""


def gerar_html(somente_cache: bool = False, so_conta: int = 0) -> str:
    # tbh_baus e opcional (modulo privado): sem ele, EUR a 1:1 e sem contas
    try:
        from tbh_baus import load_cfg, get_rate
        cfg = load_cfg()
    except Exception:
        cfg = {}
        get_rate = None
    moeda = (cfg.get("moeda") or "EUR").upper()
    if get_rate is not None:
        try:
            rate, rate_src = get_rate(moeda)
        except Exception:
            rate, rate_src = 1.0, "offline"
    else:
        rate, rate_src = 1.0, "offline"
    sim = {"EUR": "€", "USD": "$", "BRL": "R$", "GBP": "£", "JPY": "¥"}.get(moeda, moeda + " ")
    sem_cent = moeda in MOEDA_SEM_CENTAVOS
    dados = carregar_dados_jogo()
    precos = precos_frescos()
    nomes_mercado = set(precos)

    todas = list(enumerate(cfg.get("contas", []), 1))
    if so_conta:
        todas = [(i, c) for i, c in todas if i == so_conta]

    blocos, avisos = [], []
    opp_todas = []  # (idx_conta, nome, qtd, paga_c, ganho_c, dias)
    tot_paga_geral = tot_ganho_geral = 0
    tot_itens_vend = tot_tipos_vend = 0
    tot_itens_nao = tot_tipos_nao = 0
    # para diagnostico
    pesquisa_info = None

    for idx, c in todas:
        nome = esc(c.get("nome") or c.get("id", "?"))
        save = c.get("save", "")
        save_real = _save_legivel(save) if save else ""
        if not save_real or not os.path.exists(save_real):
            avisos.append("📦 <b>" + nome + "</b>: save não encontrado em <code>"
                          + esc(save or "(sem caminho)") + "</code> — corrige o caminho no baus.json")
            continue
        try:
            res = resumo_vendavel(save_real, dados, precos)
        except Exception as e:
            avisos.append("📦 <b>" + nome + "</b>: não consegui ler o save (" + esc(str(e)[:140]) + ")")
            continue

        vend = res["vendaveis"]  # {nome: qtd} so com venda ativa
        nao = res["nao_vendaveis"]  # {nome: (qtd, motivo)}
        deleted = res["deleted"]  # {label: (qtd, motivo)}
        cont_total = res["cont_total"]
        del_cont = res["del_cont"]

        # totais vendáveis
        linhas_v = []
        tot_paga = tot_ganho = 0
        for nm, qtd in sorted(vend.items(), key=lambda kv: -(precos.get(kv[0], {}).get("sell") or 0)):
            p = precos.get(nm)
            link = MARKET_URL + urllib.parse.quote(nm)
            paga_c = _para_centavos(p["sell"], rate, moeda)
            ganho_c = eu_ganho_cent(paga_c)
            tot_paga += paga_c * qtd
            tot_ganho += ganho_c * qtd
            val_dias = qtd / p["vol"] if p.get("vol") else (9999 if p.get("hist") else 9998)
            col_paga = fmt_cent(paga_c, sim, sem_cent)
            col_ganho = fmt_cent(ganho_c, sim, sem_cent)
            col_med = fmt_cent(_para_centavos(p["med"], rate, moeda), sim, sem_cent) if p.get("med") else '<span class="sem">—</span>'
            col_med = '<span class="med">' + col_med + "</span>" if p.get("med") else col_med
            vol = p.get("vol") if p else None
            if p and p.get("vol"):
                dnum = qtd / p["vol"]
                dtxt = "~" + ("<1" if dnum < 1 else str(int(dnum + 0.5))) + " dia" + ("s" if int(dnum + 0.5) != 1 else "")
                col_dias = '<span class="dias lento">' + dtxt + "</span>" if dnum > 7 else '<span class="dias">' + dtxt + "</span>"
            elif p and p.get("hist"):
                col_dias = '<span class="dias lento">mercado lento</span>'
            else:
                col_dias = '<span class="sem">sem dados</span>'
            estrela = '⭐ ' if _eh_oportunidade(paga_c, val_dias) else ''
            for _rep in range(qtd):
                opp_todas.append((idx, nm, 1, paga_c, ganho_c, val_dias))
            linhas_v.append(
                '<tr data-filtravel="1" data-val="' + str(paga_c * qtd) + '" data-ganho="' + str(ganho_c * qtd)
                + '" data-dias="' + ("%.2f" % val_dias) + '" data-qtd="' + str(qtd)
                + '" data-nome="' + esc(nm) + '">'
                + '<td class="item"><a href="' + link + '" target="_blank">' + estrela + esc(nm) + "</a></td><td>" + str(qtd)
                + "</td><td>" + col_paga + "</td><td class=\"ganho\">" + col_ganho + "</td><td>" + col_med
                + "</td><td>" + (str(vol) if vol else '<span class="sem">—</span>')
                + "</td><td>" + col_dias + '</td><td><a class="vender" href="' + link
                + '" target="_blank">Vender</a></td></tr>')

        tot_paga_geral += tot_paga
        tot_ganho_geral += tot_ganho
        tot_itens_vend += sum(vend.values())
        tot_tipos_vend += len(vend)
        tot_itens_nao += sum(q for q, _ in nao.values()) + sum(q for q, _ in deleted.values())
        tot_tipos_nao += len(nao) + len(deleted)

        # linhas não vendáveis
        linhas_n = []
        # junta nao + deleted para lista única ordenada por qtd desc
        todos_nao = []
        for nm, (qtd, motivo) in sorted(nao.items(), key=lambda kv: -kv[1][0]):
            p = precos.get(nm)
            todos_nao.append((nm, qtd, motivo, p))
        for label, (qtd, motivo) in sorted(deleted.items(), key=lambda kv: -kv[1][0]):
            todos_nao.append((label, qtd, motivo, None))
        # ordena todos por qtd desc
        todos_nao.sort(key=lambda x: -x[1])
        for nm, qtd, motivo, p in todos_nao:
            # tenta link se for nome real
            is_deleted_label = nm.startswith("Deleted ItemKey")
            if is_deleted_label:
                link_td = '<td class="item">' + esc(nm) + '</td>'
                col_paga = col_ganho = '<span class="sem">—</span>'
                col_med = col_vol = col_dias = '<span class="sem">—</span>'
                vender_td = '<span class="sem">—</span>'
            else:
                link = MARKET_URL + urllib.parse.quote(nm)
                p2 = p
                if p2 and p2.get("sell"):
                    # não deveria acontecer (seria vendável), mas trata
                    col_paga = fmt_cent(_para_centavos(p2["sell"], rate, moeda), sim, sem_cent)
                    col_ganho = fmt_cent(eu_ganho_cent(_para_centavos(p2["sell"], rate, moeda)), sim, sem_cent)
                else:
                    col_paga = col_ganho = '<span class="sem">—</span>'
                col_med = (fmt_cent(_para_centavos(p2["med"], rate, moeda), sim, sem_cent) if p2 and p2.get("med") else '<span class="sem">—</span>')
                if p2 and p2.get("med"):
                    col_med = '<span class="med">' + col_med + '</span>'
                col_vol = str(p2.get("vol")) if p2 and p2.get("vol") else '<span class="sem">—</span>'
                col_dias = '<span class="sem">sem oferta</span>'
                link_td = '<td class="item"><a href="' + link + '" target="_blank">' + esc(nm) + '</a></td>'
                vender_td = '<span class="sem">sem venda</span>'
                if p2 and p2.get("sell"):
                    vender_td = '<a class="vender" href="' + link + '" target="_blank">Vender</a>'
            linhas_n.append(
                '<tr data-filtravel="1" data-nome="' + esc(nm) + '">'
                + link_td + '<td>' + str(qtd) + '</td>'
                + '<td>' + col_paga + '</td><td class="ganho">' + col_ganho + '</td><td>' + col_med + '</td>'
                + '<td>' + col_vol + '</td><td class="motivo">' + esc(motivo) + '</td><td>' + vender_td + '</td></tr>')

        qtd_tipos_total = len(cont_total) + len(del_cont)
        qtd_itens_total = sum(cont_total.values()) + sum(del_cont.values())
        qtd_v_tipos = len(vend)
        qtd_v_itens = sum(vend.values())
        qtd_n_tipos = len(nao) + len(deleted)
        qtd_n_itens = sum(q for q, _ in nao.values()) + sum(q for q, _ in deleted.values())

        # badges no header
        badge_v = '<span class="badge ok">' + str(qtd_v_itens) + ' vendáveis</span>' if qtd_v_itens else '<span class="badge neutro">nada vendável</span>'
        badge_n = ('<span class="badge warn">' + str(qtd_n_itens) + ' não vendáveis · não contam</span>' if qtd_n_itens else '')

        extra = ""
        if qtd_n_itens:
            extra = ' · <span class="sem">' + str(qtd_n_itens) + ' itens sem venda (' + str(qtd_n_tipos) + ' tipos) não contam</span>'

        tabela_v = (
            '<table class="vend"><thead><tr><th>Item — só vendáveis (com oferta agora)</th><th>Qtd</th>'
            + '<th>Cliente paga</th><th>Eu ganho 💰</th><th>Mediana</th>'
            + '<th>Volume</th><th>Tempo p/ vender</th><th></th></tr></thead><tbody>'
            + ("".join(linhas_v) if linhas_v else '<tr><td colspan="8" style="text-align:center;color:var(--sub);padding:14px">Nenhum item com venda ativa neste bau. Vê os não vendáveis abaixo — são itens que já não listam ou são Common/Uncommon.</td></tr>')
            + '<tr class="total" data-filtravel="0"><td>TOTAL VENDÁVEL</td><td>' + str(qtd_v_itens) + '</td><td>'
            + fmt_cent(tot_paga, sim, sem_cent)
            + '</td><td class="crec">' + fmt_cent(tot_ganho, sim, sem_cent)
            + '</td><td></td><td></td><td></td><td></td></tr>'
            + '</tbody></table>')

        tabela_n = ""
        if linhas_n:
            tabela_n = (
                '<details class="nao"><summary>🚫 ' + str(qtd_n_tipos) + ' tipos · ' + str(qtd_n_itens) + ' itens NÃO VENDÁVEIS — não contam no total (clica para ver) <span style="color:var(--sub);font-weight:400">· inclui Deleted, Common/Uncommon e sem oferta</span></summary>'
                + '<table><thead><tr><th>Item</th><th>Qtd</th><th>Cliente paga</th><th>Eu ganho</th><th>Mediana</th><th>Vol.</th><th>Motivo</th><th></th></tr></thead><tbody>'
                + "".join(linhas_n) + '</tbody></table></details>')

        blocos.append(
            '<details class="conta" id="conta-' + str(idx) + '" open><summary class="ch">'
            '<span class="cnome">📦 ' + nome + ' ' + badge_v + ' ' + badge_n + '</span>'
            '<span style="text-align:right"><span class="ctotal">' + fmt_cent(tot_paga, sim, sem_cent)
            + '</span> <span class="crecebes">→ tu recebes <b>' + fmt_cent(tot_ganho, sim, sem_cent)
            + '</b></span> <span class="cinfo">· ' + str(qtd_v_tipos) + ' tipos vendáveis · '
            + str(qtd_v_itens) + ' itens vendáveis <span style="opacity:.6">| total no save: ' + str(qtd_tipos_total) + ' tipos · '
            + str(qtd_itens_total) + ' itens</span>' + extra + '</span></span></summary>'
            + '<div class="corpo">' + tabela_v + tabela_n + '</div></details>')

    fav = "câmbio " + ("live" if rate_src == "live" else str(rate_src)) if rate else ""
    avisos_html = "".join('<div class="warn">' + a + "</div>" for a in avisos)
    painel_opp = _painel_oportunidades(opp_todas, sim, sem_cent)
    nota_pesquisa = (
        '<div class="warn" style="background:#102010;border-color:#238636;color:#7ee787">'
        '🔍 <b>Pesquisa extensa aplicada:</b> o TOTAL do baú conta <b>SÓ itens com oferta de venda ATIVA agora</b> no Mercado Steam '
        '(<code>lowest_sell_order != null</code> na API). Itens <b>Deleted</b> (ItemKey removido após atualização), '
        'grades <b>Common/Uncommon</b> (nunca negociáveis), nível &gt;90, <code>nm</code> e itens <b>sem oferta</b> '
        '(ninguém a vender) aparecem abaixo em <b>“NÃO VENDÁVEIS”</b> e <b>não entram no valor</b>. '
        'Dos 8.213 itens listados na API só ~1.060 têm venda ativa — o resto tem valor 0 para venda imediata. '
        'Filtra por nome ou usa o link do cartão em <b>minhas_builds.html</b> para abrir direto a conta.'
        '</div>')

    html = ("<!doctype html><html lang=\"pt\"><head><meta charset=\"utf-8\">"
            "<title>Inventário — Task Bar Hero</title><style>" + CSS + "</style></head><body>"
            "<h1>📦 INVENTÁRIO COMPLETO — só o que dá para vender conta</h1>"
            "<sub2>Itens do baú + mochila lidos do save · preços ao minuto do "
            '<a class="ilink" href="https://tbhindex.com/pt/market" target="_blank">Mercado Steam (appid 3678970)</a> · '
            + fav + " · gerado em " + fmt_data(datetime.now().isoformat(timespec="seconds"))
            + " (preços em cache 30 min — reabre com <b>python tbh_inventario.py</b> para refrescar)</sub2>"
            + avisos_html
            + painel_opp
            + nota_pesquisa
            + '<div class="barra"><input id="filtro" placeholder="🔍 filtrar (ex.: helmet, immortal, soulstone)…"> <button id="limpar" type="button" title="limpar o filtro">✕ limpar</button>'
            '<select id="ordenar" title="ordenar">'
            '<option value="valor">💰 Mais caro → mais barato (vendáveis)</option>'
            '<option value="ganho">💰 O que eu ganho (mais primeiro)</option>'
            '<option value="tempo">⏱ Vende mais rápido primeiro</option>'
            '<option value="qtd">📦 Maior quantidade primeiro</option>'
            '<option value="nome">🔤 Nome (A→Z)</option>'
            "</select>"
            '<span class="cinfo">Soma vendável de tudo: cliente paga <b class="ok">'
            + fmt_cent(tot_paga_geral, sim, sem_cent) + "</b> · tu recebes <b>"
            + fmt_cent(tot_ganho_geral, sim, sem_cent) + "</b> · "
            + str(tot_tipos_vend) + " tipos · " + str(tot_itens_vend) + " itens vendáveis"
            + (' · <span style="color:var(--amarelo)">' + str(tot_itens_nao) + ' itens não vendáveis excluídos</span>' if tot_itens_nao else "") + "</span></div>"
            + "".join(blocos)
            + "<footer><b>Cliente paga</b> = preço da listagem mais barata AGORA no Mercado. "
            "<b>Eu ganho 💰</b> = o que cai na TUA carteira Steam depois das taxas: 5% Steam + 10% do jogo "
            "(mínimo 1 centavo cada — mesma conta que o tbhindex usa). "
            "“Mediana” = preço médio das últimas vendas. “Volume” = unidades negociadas no período recente. "
            "“Tempo p/ vender” = qtd ÷ volume. Só itens com <b>venda ativa</b> entram no TOTAL — "
            "itens <b>Deleted / Common / Uncommon / sem oferta</b> estão na secção “NÃO VENDÁVEIS” e valem 0 para venda imediata. "
            "Itens equipados nos heróis não aparecem.</footer>"
            "<script>" + JS + "</script></body></html>")
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    return OUT_HTML


# ------------------------------------------------------- cli

# ------------------------------------------------------- progresso (estagio/dificuldade/herois)

HERO_NOMES = {101: "Knight", 201: "Ranger", 301: "Sorcerer", 401: "Priest", 501: "Hunter", 601: "Slayer"}


_STAGE_INFO_CACHE = None
_STAGE_INFO_LOADED = False


def _carregar_stages() -> dict:
    """Mapa stageKey -> info (tbhdata/tbhStages.js descarregado do tbhindex.com)."""
    global _STAGE_INFO_CACHE, _STAGE_INFO_LOADED
    if _STAGE_INFO_LOADED:
        return _STAGE_INFO_CACHE or {}

    f = _resolve("data", "tbhdata", "tbhStages.js")
    if not os.path.exists(f):
        for alt in [os.path.join(ROOT, "tbhdata", "tbhStages.js"), os.path.join(BASE, "tbhdata", "tbhStages.js")]:
            if os.path.exists(alt): f = alt; break
    if not os.path.exists(f):
        _STAGE_INFO_LOADED = True
        return {}
    try:
        m = re.search(r"JSON\.parse\(`(\{.*?\})`\)",
                      open(f, encoding="utf-8", errors="replace").read(), re.S)
        if not m:
            return {}
        d = json.loads(m.group(1))
        _STAGE_INFO_CACHE = {s["key"]: s for s in d.get("stages", [])}
        _STAGE_INFO_LOADED = True
        return _STAGE_INFO_CACHE
    except Exception:
        return {}


_DIF_LABEL = {"NORMAL": "Normal", "NIGHTMARE": "Nightmare", "TORMENT": "Torment", "HELL": "Hell"}


def _stage_txt(key, stages: dict, wave=None) -> str:
    """stageKey (+onda opcional) -> zona legível; chaves plague usam A-PP após o ato 21."""
    try:
        k = int(key or 0)
    except Exception:
        return ""
    if k <= 0:
        return ""
    s = stages.get(k) or stages.get(str(k))
    if s:
        txt = str(s.get("act", "?")) + "-" + str(s.get("no", "?"))
        dif = _DIF_LABEL.get(s.get("diff"), s.get("diff", ""))
        return txt + " " + dif if dif else txt
    # chaves de Plague codificam o ato no milhar e o andar nas duas últimas casas.
    if 20000 <= k < 30000:
        act = (k // 1000) % 100
        pp = k % 100
        return str(act) + "-" + str(pp) + " Plague"
    return ""


def _zona_do_save_data(p: dict) -> dict:
    common = p.get("commonSaveData") or {}
    try:
        key = int(common.get("currentStageKey") or 0)
    except (TypeError, ValueError):
        return {}
    if key <= 0:
        return {}

    stages = _carregar_stages()
    stage = stages.get(key) or stages.get(str(key))
    wave = common.get("currentStageWave")
    result = {"key": key, "wave": wave, "label": _stage_txt(key, stages)}
    if isinstance(stage, dict):
        try:
            act = int(stage.get("act"))
            no = int(stage.get("no"))
        except (TypeError, ValueError):
            return result
        diff = str(stage.get("diff") or "").upper()
    elif 20000 <= key < 30000:
        act = (key // 1000) % 100
        no = key % 100
        diff = "PLAGUE"
    else:
        return result
    diff_index = {"NORMAL": 0, "NIGHTMARE": 1, "HELL": 2, "TORMENT": 3}.get(diff)
    result.update({
        "act": act,
        "no": no,
        "diff": diff,
        "diff_index": diff_index,
        "plague": act >= 21 or diff == "PLAGUE",
    })
    return result


def zona_atual_da_conta(save_path: str) -> dict:
    """Lê a zona atual do save; devolve campos estruturados ou {} se indisponível."""
    try:
        return _zona_do_save_data(_es3_decrypt(_save_legivel(save_path)))
    except Exception:
        return {}


def _stage_dif(key, stages: dict) -> str:
    try:
        k = int(key or 0)
    except Exception:
        return ""
    s = stages.get(k) or stages.get(str(k))
    if s:
        return _DIF_LABEL.get(s.get("diff"), s.get("diff", "")) or ""
    if 20000 <= k < 30000:
        return "Plague"
    return ""


def progresso_da_conta(save_path: str) -> dict:
    """Le o save e devolve o progresso da conta:
    atual (estagio em que esta), max (mais avançado limpo) e herois [{nome, lvl}].
    Nunca lança — devolve {} se não conseguir ler."""
    try:
        p = _es3_decrypt(_save_legivel(save_path))
    except Exception:
        return {}
    c = p.get("commonSaveData") or {}
    stages = _carregar_stages()
    atual_key = c.get("currentStageKey")
    wave = c.get("currentStageWave")
    max_key = c.get("maxCompletedStage")
    # intensidade plague atual: [act_idx, intensidade, ?, ?]
    plague_int = ""
    try:
        lp = c.get("lastPlayedPlagueIntensity")
        if isinstance(lp, (list, tuple)) and len(lp) >= 2 and lp[1]:
            plague_int = " · plague " + str(lp[1])
    except Exception:
        pass
    herois = []
    for h in p.get("heroSaveDatas") or []:
        if not h.get("IsUnLock"):
            continue
        hk = h.get("heroKey")
        try:
            lvl = int(h.get("HeroLevel") or 0)
        except Exception:
            lvl = 0
        herois.append({"nome": HERO_NOMES.get(hk, "Heroi " + str(hk)), "lvl": lvl})
    herois.sort(key=lambda x: -x["lvl"])
    return {
        "atual": _stage_txt(atual_key, stages) + (" (onda " + str(wave) + ")" if wave and _stage_txt(atual_key, stages) else ""),
        "atual_dif": _stage_dif(atual_key, stages),
        "max": _stage_txt(max_key, stages),
        "max_dif": _stage_dif(max_key, stages),
        "plague": plague_int,
        "herois": herois,
    }


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = sys.argv[1:]
    so_conta = 0
    if "--conta" in a and a.index("--conta") + 1 < len(a):
        so_conta = int(a[a.index("--conta") + 1])
    caminho = gerar_html(somente_cache="--so-html" in a, so_conta=so_conta)
    print("inventario.html gerado: " + caminho)
    if "--so-html" not in a and "--silencioso" not in a:
        try:
            os.startfile(caminho)
        except Exception:
            pass


if __name__ == "__main__":
    main()
