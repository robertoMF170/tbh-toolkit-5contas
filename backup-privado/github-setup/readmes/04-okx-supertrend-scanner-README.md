# OKX SuperTrend AI Scanner

> Scanner **paper-trading** OKX Europe que porta em Python puro o **LuxAlgo SuperTrend AI** (K-means) + **Fibonacci Golden Wave (0.5–0.618)**. Devolve **entrada/SL/TP1/TP2** prontos a copiar — sem colocar ordens.

![FastAPI](https://img.shields.io/badge/FastAPI-black) ![Python](https://img.shields.io/badge/Python-3.11-blue) ![OKX](https://img.shields.io/badge/OKX-Europe-red) ![Paper](https://img.shields.io/badge/mode-paper--only-green)

## O que faz

- **SuperTrend AI**: ATR + `n` SuperTrends + **K-means de 3 clusters** — port fiel do Pine Script do LuxAlgo.
- **Golden Zone Flux**: `highest/lowest N bars → zona 0.5–0.618`; sinal `LONG/SHORT` com recuo + rejeição nos últimos 5 bars + confirmação de candle.
- **Saída pronta**: entrada = close de confirmação, SL = limite oposto ou SuperTrend + **0.2% buffer**, TP1 **RR 1.5×**, TP2 no micro swing high/low.
- Sem ordens — só sugestões clicáveis com casas decimais por tiers + dashboard responsivo via **Tailscale**.

## Como funciona

```
OKX candles (httpx) ─► indicators/supertrend_ai.py (K-means) ─┐
                      └─ indicators/golden_flux.py (Fib 0.5-0.618)┴─► signal_engine.py (LONG/SHORT + SL/TP)
                                                                   └─ dashboard (FastAPI + Jinja2) :8000
                                                                     └─ Tailscale (privado)
```

## Stack

FastAPI, Uvicorn, httpx, numpy, pandas, Jinja2, Tailscale, OKX API

## Passo a passo — instalar e correr

```bash
# 1. Clone
git clone https://github.com/robertoMF170/okx-supertrend-scanner.git
cd okx-supertrend-scanner

# 2. Ambiente
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Configuração
copy .env.example .env   # ou cp .env.example .env
# Edita .env se precisares (OKX sem key para paper, só candles públicos)

# 4. Correr (Windows)
run.bat
# ou manual
uvicorn app.dashboard:app --host 0.0.0.0 --port 8000 --reload

# 5. Abrir
# http://localhost:8000

# 6. Tailscale (acesso remoto privado)
setup_tailscale.bat
# ou
tailscale serve 8000
```

## Como usar

1. Escolhe par (ex: `BTC-USDT`) e timeframe no dashboard.
2. Lê o sinal: **LONG/SHORT + entrada + SL + TP1 (RR 1.5×) + TP2**.
3. Copia para o broker manualmente — o scanner não envia ordens.

## Estrutura

```
app/
  dashboard.py        # FastAPI + Jinja2
  config.py
  indicators/
    supertrend_ai.py  # K-means 3 clusters
    golden_flux.py    # Fibonacci 0.5-0.618
  okx_client.py       # httpx → OKX candles
  signal_engine.py    # combinação + SL/TP
golden_scalp_hybrid.pine  # referência Pine original
templates/ + static/
run.bat
setup_tailscale.bat
```

## Avisos SrRobs

- **Paper-only** por design — não coloca ordens, só calcula.
- Confirmado em Python puro para não depender de TradingView.

## Autor

Roberto Marques (SrRobs)
