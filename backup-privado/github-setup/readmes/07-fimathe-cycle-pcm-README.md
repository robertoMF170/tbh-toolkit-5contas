# Fimathe Cycle + PCM — Pine v6 Strategy

> Proxy **objetivo e não-repintável** do método discricionário **Fimathe (Teoria dos Ciclos)**: canal `highest/lowest`, **Zona Neutra %**, arming por toque no extremo e disparo ao **recross** — com overlay **PCM** (SL por ATR, TP no bound oposto).

![Pine](https://img.shields.io/badge/Pine-v6-blue) ![Strategy](https://img.shields.io/badge/Strategy-non--repaint-green) ![PCM](https://img.shields.io/badge/PCM-ATR-red)

## O que faz

- **Canal rolling** `highest/lowest` (inclui barra atual), **Zona Neutra 35–65%** centrada na midline, tolerância de toque **8–20%** conforme TF.
- **Ciclo armado** no toque do extremo → **disparo no recross da fronteira near** da ZN — uma vez por ciclo, sem repintar.
- **PCM congelado no sinal**: `SL = além do extremo + ATR(14)×mult (1.0–3.0×)`, `TP = bound oposto`; níveis estáticos após o disparo (sem trailing).
- `strategy()` com `calc_on_every_tick=false`, `process_orders_on_close=true` (fill no **close do sinal** → alinhado com `{{close}}` dos alerts), `pyramiding 0`, 10% equity.

## Como funciona

```
highest/lowest rolling ─► Canal ─► Zona Neutra (35-65% da altura) ─┬─► Toque no extremo (tol 8-20%)
 (barra atual incl.)      │  midline                                │    └─► Arming (ciclo armado)
                          └─► ATR(14) ─► PCM (SL = extremo+ATR×mult)└─► Recross da fronteira near ─► Sinal
                                                                                 └─► TP = bound oposto (estático)
```

## Stack

Pine Script v6, TradingView strategy, ATR(14), Non-repaint

## Passo a passo — instalar

1. TradingView → `Pine Editor` → `Open` → cola `fimathe-pcm-strategy.pine`.
2. `Add to chart` → abre `Settings` → escolhe `Preset` e vê os inputs:
   - `1m`: canal **40 bars / 8% tol / 1.0× ATR**
   - `3m / 5m / 15m / 30m`: valores dedicados (ver tabela nos inputs)
3. Cria **Alert** → `Condition: Fimathe Cycle + PCM` → `Once Per Bar Close` → mensagem com `{{close}}` se quiseres.

### Inputs chave

| Preset | Canal (bars) | Tol toque | ATR mult |
|---|---|---|---|
| 1m | 40 | 8% | 1.0× |
| 3m | 60 | 10% | 1.5× |
| 5m | 80 | 12% | 2.0× |
| 15m | 100 | 15% | 2.5× |
| 30m | 120 | 20% | 3.0× |

> `max_lines=500, max_labels=500, max_bars_back=500`

## Estrutura

```
fimathe-pcm-strategy.pine   # strategy() Pine v6 — tudo num ficheiro
# (presets por input, sem includes)
```

## Avisos SrRobs

- Proxy objetivo, não o método discricionário completo — serve para testar e alertar sem subjetividade.
- `calc_on_every_tick=false` garante que não repinta dentro da barra.

## Autor

Roberto Marques (SrRobs)
