# Créditos — SrRobs não reinventa a roda

> Estes projetos são **minha versão / wrapper / adaptação** em cima de trabalho de outros. Sem eles, nada disto existia.

## Base / Terceiros

| Projeto SrRobs | Base original | Autor / Repo | O que usei |
|---|---|---|---|
| **Kronos K-Lines** | Kronos — The First K-Line Foundation Model | **NeoQuasar** — https://github.com/NeoQuasar/Kronos — `NeoQuasar/Kronos` no HF — AAAI 2026, arXiv 2508.02739 | Tokenizer hierárquico + Transformer autorregressivo (mini/small). O meu é wrapper: `sr_robs_ia_signal.py`, `crypto_signals.py`, `web_dashboard.py` |
| **MT2Robs Lite** | **eXLib** (loader `.mix`) | Comunidade Metin2 — **eXLib** (autor original do mix) | Loader que permite `init.py` client-side. O MT2Robs Lite é **minha versão**: Energy Bot + Locator em `D:\metin2` |
| **Skin Trader Pro** | CSGO-API | **ByMykel** — https://github.com/ByMykel/CSGO-API | DB de ~2000 skins para seed/import. Resto (collectors, EV, risk) é meu |
| **PokeMMO / outros** | GLM-4.6, Tesseract, CCXT, Flask, discord.js etc | Ver `requirements.txt` / `package.json` de cada repo | Uso como dependência, não como autor |

## Como cito nos READMEs

- Cada README de repo derivado tem secção `## Créditos` + link direto para o repo original.
- Exemplo Kronos: `> Base: NeoQuasar — Kronos — AAAI 2026 — github.com/NeoQuasar/Kronos`
- Exemplo MT2: `> Base: eXLib — loader .mix pela comunidade — MT2Robs Lite é minha versão em cima dele`

> Se faltar algum crédito, abre issue no `srrobs-portfolio` que corrijo.

## O que NÃO subo

Nenhum repo leva:
- `.env` / chaves / `events.db` / `debug.txt` / `shots/` / `baus_cache.json` / `.venv/` / `node_modules/`
- Código com lógica anti-detecção sensível — só documentação, instalação e uso público

Todos os READMEs explicam **como instalar, dependências e como funciona** — sem expor código privado.
