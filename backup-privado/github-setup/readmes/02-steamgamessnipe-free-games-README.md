# SrRobs Free Games — Steamgamessnipe

> Bot Discord (Node 20) que vigia a loja Steam a cada **30 min** e anuncia jogos que **estavam pagos e ficaram a -100%** (licença permanente). Também faz arbitragem de **trading cards**.

![Node](https://img.shields.io/badge/Node-20-green) ![discord.js](https://img.shields.io/badge/discord.js-14-blue) ![SQLite](https://img.shields.io/badge/better--sqlite3-black) ![Docker](https://img.shields.io/badge/Docker-ready-blue)

## O que faz

- **Freebies reais**: `specials=1` sorted `Price_ASC` → confirma via `appdetails` que o preço original era `> 0` (F2P de origem fora).
- **Modo cards**: até **3€**, calcula `drops × preço médio ÷ 1.15` e só anuncia se recuperar custo + margem; mostra set completo e previsão conservadora.
- **Sem spam**: dedupe por `appid`, **apaga** a mensagem quando a promo acaba (após 2 ciclos sem ver), histórico arquivado 30 dias.
- **Zero ASF / zero conta Steam**: só lê a store pública.

## Como funciona

```
Steam specials=1 Price_ASC ─► appdetails (confirma preço original) ─┬─► freebies (-100% com preço original >0)
                                                                    └─► cards (≤3€, retorno > custo + margem)
                                                                      ─► better-sqlite3 (dedupe + historico)
                                                                      ─► discord.js (embed + auto-delete)
                                                                      ◄─ cron 30min + winston logs
```

## Stack

Node 20, discord.js 14, better-sqlite3, winston, Docker, Steam Store API

## Passo a passo — instalar e correr

```bash
# 1. Clone
git clone https://github.com/robertoMF170/steamgamessnipe-free-games.git
cd steamgamessnipe-free-games

# 2. Dependências
npm install

# 3. Configuração
cp .env.example .env
# Edita .env: DISCORD_TOKEN, CLIENT_ID, GUILD_ID, CHANNEL_ID

# 4. Wizard (interativo)
npm run setup        # cria .env passo a passo
npm run invite       # gera link de convite com permissões certas
npm run deploy-commands  # registra /ofertas /status /verificar /help

# 5. Correr
npm start            # ou: npm run dev (watch)
npm run smoke-test   # teste rápido sem Discord (mock)

# 6. Docker
docker compose up -d --build
docker logs -f steamgamessnipe

# 7. Oracle Free (opcional)
# O deploy/install.sh já está preparado para VPS Oracle
```

## Comandos Discord

| Comando | O que faz |
|---|---|
| `/ofertas` | Lista freebies e arbitragens ativas |
| `/status` | Estado do bot, último ciclo, erros |
| `/verificar` | Força um ciclo agora |
| `/help` | Ajuda |

## Estrutura

```
src/index.js
src/discord/deploy-commands.js
src/steam/
  search.js          # specials + sort
  appdetails.js      # confirmação de preço
  market.js          # preço médio de cards
src/db/              # better-sqlite3
Dockerfile + docker-compose.yml
deploy/install.sh    # Oracle
```

## Avisos SrRobs

- Só anuncia **pagos→grátis**, não F2P de origem — checagem dupla via appdetails.
- ~100 MB RAM — cabe no free tier.
- Não faz farm, não usa ASF.

## Autor

Roberto Marques (SrRobs) — https://github.com/robertoMF170
