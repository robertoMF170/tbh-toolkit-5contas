# MT2Robs Lite — Energy + Locator (Gameforge, client-side)

> Mod **100% client-side** para o cliente atual da Gameforge: **farm de energias** (auto-buy facas → fragmentos com ritmo humanizado) + **localizador Metins/Bosses** com seta, lista de alvos e “ir até”.

![Metin2](https://img.shields.io/badge/Metin2-Gameforge-red) ![Mix](https://img.shields.io/badge/eXLib.mix-client--side-black) ![Python](https://img.shields.io/badge/Python-inject-blue)

## O que faz

- **Energias**: junto ao **vendedor de armas**, auto-buy de **facas até encher**; anda **TU** até ao **alquimista** e ele troca tudo por **fragmentos** com ritmo humanizado (não instantâneo).
- **Locator**: Metins e Bosses com **seta direcional**, lista de alvos (coord/vivo-morto), botão **“ir até”** autónomo, filtro **nível min/max** e **som opcional**.
- **Mapa Pyungmoo** mapeado (`Vendedor 430,607 → Alquimista 292,812 via 383,640 centro`) + ferramentas `marcar_zonas.py` e `recortemapa.py` (OpenCV) para mapear outras zonas.
- Log em `mt2robs.txt`, hotkeys `+/INSERT` (barra) e `↓` (stealth).

## Como funciona

```
eXLib.mix ─► init.py ─► MT2Robs/
                          ├─► EnergyBot.py (NPC_POSITIONS: Vendedor 430,607 → Alquimista 292,812)
                          │     └─► ritmo humanizado + log mt2robs.txt
                          ├─► Locator.py (varredura de Metins/Bosses)
                          │     ├─► seta direcional + lista coord/vivo-morto
                          │     └─► "ir até" autónomo + filtro nível + som
                          └─► Guide (MT2Guide/MT2Robs-IPC) — canal IPC
```

## Stack

eXLib.mix, Python inject (Gameforge), OpenCV (mapeamento), MT2Guide / MT2Robs-IPC

## Passo a passo — instalar

1. Faz backup do cliente Metin2.
2. Copia `init.py` + pasta `MT2Robs/` para a **raiz do cliente** (ao lado de `eXLib.mix` compatível).
3. Verifica que `eXLib.mix` é da **versão do teu cliente Gameforge** (mix por versão).
4. Abre o cliente → entra em jogo → painel MT2Robs aparece.
5. **Hotkeys**: `+` ou `INSERT` = mostra/esconde barra · `↓` = stealth.

### Usar

- **Energy**: vai até **Pyungmoo, vendedor de armas (430,607)** → ativa Energy Bot → ele compra facas → anda até **alquimista (292,812)** → troca por fragmentos.
- **Locator**: abre lista → vê Metins/Bosses com distância → clica **“ir até”** → segue seta até ao alvo.
- **Outras zonas**: corre `marcar_zonas.py` para marcar NPCs novos → adapta `NPC_POSITIONS` em `EnergyBot.py`.

## Estrutura

```
MT2Robs-Lite/
  init.py                     # entry — carregado por eXLib.mix
  MT2Robs/
    EnergyBot.py              # NPC_POSITIONS + auto-buy + troca
    Locator.py                # varredura + seta + "ir até"
    Guide/                    # MT2Guide
    IPC/                      # MT2Robs-IPC (canal)
  marcar_zonas.py             # mapeia NPCs de outras zonas
  recortemapa.py              # OpenCV — recorte de mapa
  eXLib.mix                   # mix compatível com o cliente
  MT2Robs-IPC/                # IPC externo
  ClientGuide/                # guia cliente
```

## Avisos SrRobs

- **Client-side only** — lê só o que o jogador já vê; sem pacotes para o servidor.
- Atualiza `eXLib.mix` sempre que a Gameforge atualiza o cliente.
- Usa com cabeça — não abusa de timings não-humanos.

## Autor

Roberto Marques (SrRobs) — MT2Robs Lite
