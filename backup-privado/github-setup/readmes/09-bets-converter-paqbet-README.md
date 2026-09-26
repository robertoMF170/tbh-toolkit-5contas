# Bets Converter — Paqbet

> Conversor de **booking codes** entre casas (BetAndYou ↔ 1xbet/22bet/Bet9ja…) via **Paqbet** como ponte. Flask + scraping com **CSRF**, retry com backoff, **cache 10 min** e CORS — UI dark com gold.

![Flask](https://img.shields.io/badge/Flask-black) ![BS4](https://img.shields.io/badge/BS4-scraping-green) ![CORS](https://img.shields.io/badge/CORS-enabled-blue)

## O que faz

- **Flask com CORS aberto**, endpoints `/api/convert` e `/health`.
- Sessão `requests` com **User-Agent Chrome 120** e `Referer: paqbet.com`.
- Fluxo: `GET Paqbet → parse csrf input (csrf_new*) → POST convert/booking_codes → JSON`; **retries** `MAX_ATTEMPTS=3, delay 1s` + **cache TTL 600s** em memória.
- **Alias mapping** (`betandyou→1xbet:xx`) + `PRETTY_NAMES`; view HTML devolvida no JSON.

## Como funciona

```
[ UI dark/gold ] ─► POST /api/convert {code, from, to}
                          │
                          ├─► _results_cache (TTL 600s) — se hit, devolve direto
                          └─► GET https://paqbet.com → parse csrf_new* input (BS4)
                               └─► POST convert/booking_codes (CSRF + map aliases)
                                    └─► retry ×3 (backoff 1s) ─► JSON + view HTML
```

## Stack

Flask, BeautifulSoup4, requests, Flask-CORS, Paqbet API

## Passo a passo — instalar e correr

```bash
# 1. Clone
git clone https://github.com/robertoMF170/bets-converter-paqbet.git
cd bets-converter-paqbet

# 2. Ambiente
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# Reqs: flask, flask-cors, requests, beautifulsoup4

# 3. Correr
python app.py
# ou
python start.py
# Abre http://localhost:5000

# 4. Expor (opcional)
# ngrok http 5000
# e cola o domínio em ngrok_domain.txt se usares túnel fixo
```

## API

```http
POST /api/convert
Content-Type: application/json

{
  "code": "ABC123",
  "from": "betandyou",
  "to": "1xbet"
}
# → { "converted": "XYZ789", "view": "<html>…", "cached": false }

GET /health
# → { "status": "ok" }
```

## Estrutura

```
app.py                # Flask + CORS + /api/convert + /health
index.html            # UI dark ( --bg #0f0f0f, gold #d4af37, red #e50914 )
start.py              # entry alternativo
ngrok_domain.txt      # túnel fixo (opcional)
```

## Avisos SrRobs

- Depende de Paqbet — se mudarem o `csrf_new*` input, o BS4 selector precisa atualizar.
- Cache em memória — reiniciar o Flask limpa o cache.

## Autor

Roberto Marques (SrRobs)
