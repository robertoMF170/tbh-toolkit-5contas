# SrRobs Skin Trader Pro

> Dashboard Flask local que cruza **Steam + CSFloat + Skinport + DMarket** para calcular o **EV determinístico** de trade-ups. Botão “Comprar” sempre manual — nada automático.

![Stack](https://img.shields.io/badge/Flask-3.x-black) ![Python](https://img.shields.io/badge/Python-3.11-blue) ![SQLite](https://img.shields.io/badge/SQLite-WAL-green) ![Status](https://img.shields.io/badge/status-em_desenvolvimento-red)

## O que faz

- Liga a 4 fontes (Steam priceoverview + pricehistory, CSFloat listings com **float real**, Skinport bulk, DMarket com HMAC assinado) com **rate-limit + backoff exponencial** para 429/5xx.
- Calcula trade-ups **determinísticos**: contratos `10×` da mesma coleção e mixes `k×A + (10−k)×B`, com float ratio normalizado e distribuição de output por wear.
- Avalia **EV líquido** já com fees (Steam 15% / terceiros 5%) e mede **robustez por volatilidade σ 30/60/90d** — robusto só se `EV ≥ 2×σ` ponderada e histórico suficiente (≥3 pontos, ≥50% cobertura). Sem dados, nunca assume robustez.
- Rastreia **trade lock de 7 dias** e sugere `vender / tradear / segurar` após o lock. Notifica via **Telegram (Roco)** oportunidades robustas e fim de lock.
- Acesso remoto só via **Tailscale serve** (nunca funnel). IA local opcional via **LM Studio**.

## Como funciona

```
collectors/steam.py ─┐
collectors/csfloat.py ─┼─► engine/tradeup.py (contratos + EV) ─► engine/risk.py (σ, robustez) ─► engine/opportunities.py
collectors/skinport.py┤         ▲                                                      │
collectors/dmarket.py ─┘         └─ data/importer.py (ByMykel/CSGO-API ~2000 skins) ◄─┘
                                 scheduler.py (APScheduler) ─► db.py (SQLite WAL) ─► portfolio.py + notifier.py (Telegram)
```

## Stack

Flask 3, APScheduler, SQLite (WAL), requests, python-dotenv, brotli, ByMykel/CSGO-API, Tailscale, Telegram, LM Studio (opcional)

## Passo a passo — instalar e correr

```bash
# 1. Clone
git clone https://github.com/robertoMF170/srrobs-skin-trader-pro.git
cd srrobs-skin-trader-pro

# 2. Ambiente
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 3. Dependências
pip install -r requirements.txt

# 4. Configuração (cria .env na raiz)
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/Mac
# Edita .env: STEAM_API_KEY, CSFLOAT_KEY, SKINPORT_KEY, DMARKET_KEYS, TELEGRAM_BOT_TOKEN, ROCO_CHAT_ID

# 5. Seed de skins (opcional, primeira vez)
python data/importer.py

# 6. Correr
python app.py            # ou: flask run --port 5000
# Abre http://localhost:5000

# 7. Tailscale (acesso remoto privado)
tailscale serve 5000
# ou: tailscale funnel 5000  (evita — serve é o correto)
```

## Como usar

1. Dashboard lista oportunidades com **EV, σ e badge Robustez**.
2. Filtra por coleção / mix / fee.
3. Clica **Comprar** — abre a fonte certa (Steam/CSFloat...) para comprares manualmente.
4. Registra a compra para rastrear o lock de 7 dias.
5. Recebe alerta Telegram quando ficar robusto ou quando o lock acabar.

## Estrutura

```
app.py
scheduler.py          # APScheduler — polling de preços
db.py                 # SQLite WAL + helpers
collectors/
  steam.py            # priceoverview + pricehistory
  csfloat.py          # listings + float
  skinport.py         # bulk
  dmarket.py          # HMAC assinado + backoff
engine/
  tradeup.py          # contratos + distribuição wear
  risk.py             # σ 30/60/90 + robustez
  opportunities.py    # ranking por EV
data/importer.py      # ByMykel/CSGO-API
portfolio.py          # posições + locks
notifier.py           # Telegram (Roco)
insights.py
seed.py
```

## Avisos SrRobs

- Nunca clica em “Comprar” por ti — **cálculo ≠ ordem**. fees e lock são reais.
- Sem histórico suficiente, a flag robusto não aparece — é por design.
- Mantém `requirements.txt` com `flask 3, apscheduler, requests, python-dotenv, brotli, pytest` como em `D:\cs2snipre`.

## Autor

Roberto Marques (SrRobs) — Operação Mainframe / Control-M · Python & Web nos tempos livres.
