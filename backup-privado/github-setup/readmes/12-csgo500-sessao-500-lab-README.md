# Laboratório Sessão 500 — CSGO500

> Kit de **disciplina** para CSGO500: **painel com Monte Carlo 10k**, **HUD Tampermonkey (Shadow DOM)**, **Vigia com OpenCV** que lê saldo/multiplicador **sem API** e simuladores Python. O mais testado da casa: **623 testes**.

![Tests](https://img.shields.io/badge/tests-623-green) ![MonteCarlo](https://img.shields.io/badge/Monte_Carlo-10k-blue) ![Tampermonkey](https://img.shields.io/badge/Tampermonkey-Shadow_DOM-yellow) ![OpenCV](https://img.shields.io/badge/OpenCV-vigia-black)

## O que faz

- **`painel-sessao.html`** (offline, 1 ficheiro): P/L, meta, **volume = banca/edge** (ex: `$5 / 1% = $500 ~1667 rondas $0.30`), **guardrails**, coach por rotação (**dice / mines**), **TiltGuard** (a cada 25 rondas, 5 defeats seguidas, win ≥$1).
- **Monte Carlo 10k** simulações **~250ms** no browser + gráfico canvas `E[saldo]=banca−edge×volume`; **export JSON/CSV** + **localStorage** + **mock-casino.html**.
- **`painel-500.user.js`** HUD em **Shadow DOM**: lê saldo/URL, **edge por jogo**, recomendação; **414 testes** (`fuzz 1680 estados`).
- **`vigia-500.py`** com **OpenCV** sem API — lê **saldo/multiplicador/minas/tabuleiro por cor**; **209 testes** de paridade com o JS + simuladores Python para custo real.

## Como funciona

```
[banca + edge] ─► volume (banca/edge) ─► painel-sessao.html (P/L, guardrails, TiltGuard, coach)
                                           ├─► Monte Carlo 10k → canvas E[saldo] + JSON/CSV
                                           ├─► painel-500.user.js (Shadow DOM HUD no CSGO500)
                                           │     └─► teste-hud.js (414 testes, fuzz 1680 estados)
                                           └─► vigia-500.py (OpenCV, sem API)
                                                 ├─► vigia_motor/visao.py (saldo/mult/minas por cor)
                                                 ├─► teste-vigia.py (209 testes, paridade JS)
                                                 └─► simulador_diversao/desafio.py
```

## Stack

HTML + CSS + Canvas + JS, Tampermonkey (Shadow DOM), Python, OpenCV, PyQt6 (vigia GUI opcional), Node test

## Passo a passo — usar

### Painel (sem instalar nada)

1. Abre `painel-sessao.html` com duplo clique (offline, sem servidor).
2. Preenche **Banca**, **Edge %** e **Stake**.
3. Vê **Volume**, **P/L**, **Guardrails** e **TiltGuard**.
4. Clica **Monte Carlo 10k** → gráfico + export.

### HUD no CSGO500 (Tampermonkey)

1. Instala **Tampermonkey** → `Create new script` → cola `painel-500.user.js` → Save.
2. Abre `csgo500.com` → HUD aparece em Shadow DOM.
3. Para testes: `node teste-hud.js` (414 testes).

### Vigia (OpenCV, sem API)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# Reqs: opencv-python, numpy, mss, pillow, pyqt6 (GUI opcional)

python vigia-500.py
python teste-vigia.py          # 209 testes
python simulador_diversao.py
python simulador_desafio.py

# Mock para testar sem CSGO500
# Abre mock-casino.html no browser e aponta o vigia para a janela
```

## Matemática chave

| Conceito | Fórmula |
|---|---|
| Volume | `banca / edge` → ex: `$5 / 0.01 = $500` |
| Rondas | `volume / stake` → `$500 / $0.30 ≈ 1667` |
| E[saldo] | `banca − edge × volume` |
| TiltGuard | a cada **25 rondas**, **5 defeats seguidas**, ou `win ≥ $1` |
| Mines (desafio) | `fid: rotação dice 2.0 / mines 3 2` com `p = C(25−m,k) / C(25,k)` |

## Estrutura

```
painel-sessao.html            # 1 ficheiro offline (volume=banca/edge)
painel-500.user.js            # HUD Shadow DOM
teste-hud.js                  # 414 testes (Node)
vigia-500.py                  # entry vigia
vigia_motor/
  visao.py                    # OpenCV: saldo/mult/minas por cor
teste-vigia.py                # 209 testes (paridade JS)
simulador_desafio.py
simulador_diversao.py
mock-casino.html              # mock para testes
```

## Avisos SrRobs

- **Disciplina > sorte** — o lab mede, não promete. Monte Carlo mostra a distribuição real.
- Vigia lê **por cor/pixels** — se o casino mudar o layout, `visao.py` precisa recalibrar cor/coords.

## Autor

Roberto Marques (SrRobs) — Laboratório Sessão 500
