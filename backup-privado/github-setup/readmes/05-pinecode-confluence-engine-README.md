# Confluence Engine — RebelsFunding

> Motor de confluência **4 pernas + HTF** para contas de prop firm. **Trend 30% + Momentum 25% + Volume 15% + Structure 30%**, 12 presets HTF, lote por risco, 3 TPs, BE e trailing — dashboard arrastável via **Tampermonkey**.

![Pine](https://img.shields.io/badge/Pine-v5-blue) ![MQL5](https://img.shields.io/badge/MQL5-MT5-orange) ![Tampermonkey](https://img.shields.io/badge/Tampermonkey-user.js-yellow) ![TradingView](https://img.shields.io/badge/TradingView-override-black)

## O que faz

- **Scoring de confluência**: cada perna pontua bull/bear (EMA/RSI/MACD/ATR/Pivot/Volume). Só dispara se gap mínimo + volatilidade OK + barras de gap cumpridas.
- **Presets por timeframe**: 1m até 1d + duais `15m+4H, 30m+4H, 1H+4H, 5m+1H, 3m+30m, 1m+15m` — cada um com parâmetros dedicados (EMA/MACD/ATR/pivot/gap/TP).
- **Risk embutido**: saldo + `% risco` → lote auto, `SL = max(ATR TF × mult, ATR HTF ×0.6)`, 3 TPs com RR configurável, **BE após TP1 + trailing**.
- **Sem API TradingView**: o `user.js` intercepta `fetch/XHR` para roubar OHLC direto do gráfico + dashboard flutuante arrastável.

## Como funciona

```
TradingView OHLC (fetch/XHR intercept)
  ├─► SrRobs_Confluence_Engine.pine  ─┬─► Trend (EMA) + Momentum (RSI/MACD) + Volume + Structure (Pivot)
  ├─► SrRobs_Confluence_Engine.mq5    ├─► HTF filter (5ª perna) ─► gap/VOL check ─► LONG/SHORT
  └─► SrRobs_Confluence_Engine.user.js┴─► Risk: lote por saldo → SL (ATR) → TP1/TP2/TP3 → BE+trailing → Dashboard
```

## Stack

Pine Script v5, MQL5, Tampermonkey (user.js), EMA/RSI/MACD/ATR/Pivot/Volume, TradingView

## Passo a passo — instalar

### TradingView (Pine)

1. TradingView → Pine Editor → `Create new indicator` → cola `SrRobs_Confluence_Engine.pine`.
2. `Add to chart` → escolhe `Preset` no input (ex: `15m+4H RebelsFunding`).
3. Ajusta `Risco %` e `Saldo` nos inputs se quiseres cálculo de lote visível.

### MetaTrader 5 (MQL5)

1. Copia `SrRobs_Confluence_Engine.mq5` para `MQL5/Experts/`.
2. Compila (F7) e arrasta para o gráfico.

### Tampermonkey (Dashboard)

1. Instala extensão **Tampermonkey** no browser.
2. `Create new script` → cola `SrRobs_Confluence_Engine.user.js` → Save (Ctrl+S).
3. Abre TradingView com o Confluence no gráfico → dashboard aparece flutuante (arrastável).
4. `F12` → filtra `[SrRobs CE]` nos logs para debug OHLC.

## Presets HTF disponíveis

`1m, 3m, 5m, 15m, 30m, 1H, 4H, 1D, 15m+4H, 30m+4H, 1H+4H, 5m+1H, 3m+30m, 1m+15m` — cada preset tem tuplos próprios de EMA/MACD/ATR/pivot/gap/TP (ver tabela no código).

## Estrutura

```
SrRobs_Confluence_Engine.pine   # master strategy/indicator
SrRobs_Confluence_Engine.mq5    # port MT5
SrRobs_Confluence_Engine.user.js# intercept + dashboard flutuante
SrRobs_Dashboard.pine           # dashboard auxiliar Pine
```

## Avisos SrRobs

- Pensado para **RebelsFunding** e prop firms — respeita o edge/TTF do desafio.
- O user.js não usa API pública — lê o que o gráfico já tem em memória.

## Autor

Roberto Marques (SrRobs)
