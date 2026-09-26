# Kronos — K-Lines Foundation Model (wrapper SrRobs)

> Wrapper SrRobs sobre o **Kronos (NeoQuasar)** — primeiro **foundation model para candlesticks** (45 exchanges). Tokenizer hierárquico + Transformer autorregressivo → sinais **COMPRA / VENDA / NEUTRO** + dashboard **Flask/Plotly**.

![Kronos](https://img.shields.io/badge/Kronos-HF-yellow) ![Transformer](https://img.shields.io/badge/Transformer-autoregressive-blue) ![CCXT](https://img.shields.io/badge/CCXT-Binance-orange) ![Paper](https://img.shields.io/badge/AAAI-2026-green)

> Base: NeoQuasar — *Kronos: The First K-line Foundation Model* — AAAI 2026, arXiv 2508.02739

## O que faz

- **Tokenização hierárquica** de OHLCV + **Transformer autorregressivo**; modelos **mini (4.1M, ctx 2048)** e **small (24.7M, ctx 512)** no HuggingFace.
- **SrRobs IA**: `sr_robs_ia_signal.py + crypto_signals.py` — fetch via **CCXT Binance**, `load_kronos` + `run_kronos_prediction` → sinais com confiança.
- **Dashboard** `web_dashboard.py` (Flask + Plotly interativo) em `:5050` — alterna **Confluence Engine ↔ Kronos IA** — via **Tailscale**.
- `signal_watcher.py` vigia sinais fora do dashboard; finetune com **Qlib** + exemplos + webui inclusos.

## Como funciona

```
Binance OHLCV (CCXT) ─► load_kronos (HF mini/small) ─► run_kronos_prediction (Transformer + hierarchical tokenizer)
                              │
                              ├─► sr_robs_ia_signal.py ─► COMPRA/VENDA/NEUTRO
                              ├─► crypto_signals.py / crypto_scanner.py / forex_scanner.py
                              └─► web_dashboard.py (Flask + Plotly :5050) ◄─► signal_watcher.py
                                                                    └─► Tailscale
```

## Stack

Kronos (HF), PyTorch, CCXT, Binance, Flask, Plotly, Qlib, Python

## Passo a passo — instalar e correr

```bash
# 1. Clone
git clone https://github.com/robertoMF170/kronos-klines-ai.git
cd kronos-klines-ai

# 2. Clone do Kronos base (se ainda não tens)
git clone https://github.com/NeoQuasar/Kronos.git
# ou usa o subdir já em D:\kronos\Kronos

# 3. Ambiente
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# Reqs: torch, transformers, ccxt, flask, plotly, pandas, numpy, qlib (finetune opcional)

# 4. HF login (se precisares de modelo gated)
huggingface-cli login

# 5. Sinais (CLI)
python sr_robs_ia_signal.py --symbol BTCUSDT --interval 1h
python crypto_signals.py --scan

# 6. Dashboard
python web_dashboard.py
# Abre http://localhost:5050
tailscale serve 5050

# 7. Watcher (opcional)
python signal_watcher.py
```

## Estrutura

```
Kronos/                   # base NeoQuasar (model/ + examples/)
sr_robs_ia_signal.py      # entry SrRobs (load_kronos → prediction)
crypto_signals.py
crypto_scanner.py
forex_scanner.py
web_dashboard.py          # Flask + Plotly :5050
signal_watcher.py
finetune/ + qlib
examples/ + webui/
```

## Avisos SrRobs

- **Research lane** — lab, não é estratégia final. Usa em **paper** primeiro.
- Modelos são pesados — `mini` para testes rápidos, `small` para sinais mais estáveis.
- Citação: se usares Kronos, cita `NeoQuasar, AAAI 2026`.

## Autor

Wrapper SrRobs — Base NeoQuasar / HuggingFace `NeoQuasar/Kronos`.
Roberto Marques (SrRobs)
