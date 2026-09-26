# Taskbar Hero Toolkit

Ferramenta completa para o jogo **Taskbar Hero**: gera uma dashboard local com **builds** (skills + mapa de runas), **farm OP** do dia, **mapa de drops estilo jogo**, recomendações **UPAR JÁ**, **inventário** vendável e gestão de **baús**.

Tudo corre localmente em Python — sem contas, sem chaves e sem dados pessoais.

## Uso rápido (único arranque)

```bat
run.bat              :: confirma saves vs Steam Cloud, gera o site e abre o dashboard
run.bat --forcar     :: (só com módulos locais) força arranque de todas as sandboxes
```

O `run.bat` é o **único** arranque — os atalhos legados em `scripts/` apenas chamam este. Sem os módulos locais opcionais, o run gera apenas o site e abre o dashboard (a versão pública funciona assim).

Também podes correr diretamente:

```bat
python src\tbh_site.py        :: gera minhas_builds.html e inventario.html
```

## Instalação

1. **Python 3.10+** em Windows (testado em 3.14).
2. Copia `config/builds.example.json` para `config/builds.json` e ajusta as tuas builds (URLs do `tbhindex.com`).
3. Corre `python src\tbh_site.py` (ou `run.bat`).
4. Abre `minhas_builds.html` no browser.

## Proteção de saves (anti-perda de dados)

Antes de arrancar qualquer conta, o `run.bat` corre `src/tbh_sync.py --pre`, que:

- **faz sempre backup** do save local para `var/saves_backup/<conta>/` (guarda os 20 mais recentes);
- compara o save local (`SaveFile_Live.es3`) com a **cache da Steam Cloud** (`Steam\userdata\<id>\3678970\ac\...`);
- se o save local faltar, estiver vazio ou corrompido, **restaura da cloud** (ou do backup mais novo);
- se a **cloud estiver mais nova** que o local, avisa e pergunta antes de arrancar — assim um save velho nunca sobrescreve a cloud e perdes progresso.

Também corre sozinho: `python src\tbh_sync.py --pre` (ou `--auto` para não perguntar).

## O que a dashboard dá

- **SKILLS DO HEROI** — árvore de skills de cada build com a ordem de up.
- **MAPA DE RUNAS** — rota ideal pela árvore global de 241 runas.
- **FARM OP** (em baixo, horizontal) — filtros *Equilíbrio / Mais caros / Mais fácil vender / Mais fácil drop* e coluna *Dropa em* (zona + dificuldade).
- **Ver no mapa** — mapa estilo jogo, "para burros": em cima o **modo** e o **lugar do item**, passo a passo (Portal → modo → ato → andar) e a **bola pintada de verde** exatamente onde farmar; nas **Terras da Peste** mostra o **nível** e o **andar** (1–20).
- **UPAR JÁ** — recomendações de progressão ligadas às builds.
- **Inventário / baús** — ativos quando os módulos locais opcionais existem.

## Estrutura

```
run.bat                → único arranque (usa SEMPRE este)
minhas_builds.html     → dashboard gerado (builds + farm + mapa)
inventario.html        → inventário vendável (gerado)

src/                   → código Python
  tbh_site.py          → gerador da dashboard (ver mapa, farm em baixo, filtros)
  tbh_arvore.py        → árvore de skills
  tbh_mapa.py          → mapa de runas e assets/maps/
  tbh_farm.py          → farm OP (top híbrido/baleias/líquidos + Dropa em)
  tbh_recomendar.py    → motor UPAR JÁ
  tbh_inventario.py    → inventário a partir do save .es3
  tbh_sync.py          → confirma saves vs Steam Cloud antes do login (anti-perda)
  tbh_sieve.py         → scraping opcional (usesieve.com)
  tbh_protocol.py      → protocolo tbh://

assets/                → icons, icons_chars, icons_hero, icons_passivos, maps/
config/                → builds.example.json (copia para builds.json), .env.example
data/tbhdata/          → dados do jogo (stages, runas, skills, preços)
var/                   → caches e logs gerados
scripts/               → atalhos sieve_* (os restantes .bat são locais, opcionais)
tests/                 → test_tbh_sieve.py
```

O código procura primeiro na estrutura nova (`config/`, `data/tbhdata/`, `assets/`, `var/`) com **fallback** para a raiz, por isso nada quebra ao migrar.

## Módulos opcionais (versão local)

`src/abrir_steam.py` e `src/tbh_baus.py` não fazem parte da versão pública (automação de sandboxes e leitura de saves). O `run.bat` e os `scripts/` detetam a ausência e saltam essas secções automaticamente — o site continua a ser gerado na mesma.

Os teus dados (contas, saves `.es3`, `config/builds.json`, caches) ficam locais e estão no `.gitignore`.

## SIEVE (opcional)

Integração com `scrape.usesieve.com` em `src/tbh_sieve.py`. Sem chave não faz nada.

```bat
scripts\sieve_login.bat          :: ou: python src\tbh_sieve.py --login
python src\tbh_sieve.py --iniciar "Extrai ..." --url https://quotes.toscrape.com
scripts\sieve_seguir.bat         :: ou: python src\tbh_sieve.py --seguir
```

Coloca a chave em `config/.env` (ver `config/.env.example`).

## Testes

```bat
python -m unittest tests.test_tbh_sieve -v
:: ou tudo:
python -m unittest discover -s tests
```
