# TaskBarHero Toolkit — 5 Contas via Sandboxie

> Oficina para quem joga **TaskBarHero** a sério: **5 contas isoladas via Sandboxie**, leitura de saves `.es3`, gestão de **baús** (`baus.json/history/cache`), **builds** (`tbhindex.com`), análise de **pixels** (mss + layered windows) e extractor de sprites.

![Sandboxie](https://img.shields.io/badge/Sandboxie-5_contas-yellow) ![TBH](https://img.shields.io/badge/TaskBarHero-toolkit-blue) ![MSS](https://img.shields.io/badge/mss-pixel--capture-black) ![Python](https://img.shields.io/badge/Python-tooling-green)

## O que faz

- **5 contas** (`geek1781, opiratanumero1, robert33o, RobertoMF998, xrobs`) isoladas em `Sandbox\Robs\*\user\current\AppData\LocalLow\TesseractStudio\TaskbarHero` — cada save `SaveFile_Live.es3` separado.
- **Baús** em `baus.json / baus_history.json / baus_cache.json` com monitor de lock + alerts (**min 0.8 / 1 dia**), import via `baus_para_importar/`.
- **Builds** em `builds.json` (`tbhindex.com/252/324/338` + mixes `214+153`).
- **`analyze_tbh.py`**: `EnumWindows` de `taskbarhero.exe`, `GetWindowRect` + flags `WS_EX_LAYERED / WS_EX_TRANSPARENT` + **mss** screenshot para **% pixels pretos**.
- Extractors `extract_chars / passivos / sprites` + `icons/sprites` por tier + `_farm_preview.html`.

## Como funciona

```
5× Sandboxie (Robs\*) ─► SaveFile_Live.es3 por conta ─┬─► baus.json/history/cache (monitor lock, alert 0.8/1d)
                                                      ├─► builds.json (tbhindex.com)
                                                      ├─► analyze_tbh.py (EnumWindows + WS_EX_LAYERED/TRANSPARENT + mss → % pretos)
                                                      └─► extract_{chars,passivos,sprites}.py → icons/ + _farm_preview.html
```

## Stack

Sandboxie, Python, mss, numpy, win32 (pywin32), Pillow, TaskBarHero (.es3)

## Passo a passo — instalar e usar

```bash
# 1. Clone
git clone https://github.com/robertoMF170/tbh-toolkit-5contas.git
cd tbh-toolkit-5contas

# 2. Sandboxie
# Instala Sandboxie-Plus → cria boxes: geek1781, opiratanumero1, robert33o, RobertoMF998, xrobs
# Instala Steam + TaskBarHero dentro de cada box

# 3. Ambiente (análise)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# Reqs: mss, numpy, pillow, pywin32

# 4. Lançar contas
abrir_conta1.bat   # → geek1781
abrir_conta2.bat   # → opiratanumero1
abrir_conta3.bat   # → robert33o
abrir_conta4.bat   # → RobertoMF998
abrir_conta5.bat   # → xrobs
# ou
python abrir_steam.py --conta 1

# 5. Analisar
python analyze_tbh.py
# → lista janelas taskbarhero.exe + % pixels pretos (via mss)

# 6. Baús e builds
# Edita baus.json (ou importa de baus_para_importar/)
# Edita builds.json (ou usa tbhindex.com → export)
# Abre _farm_preview.html no browser para pré-visualizar
```

## Estrutura

```
baus.json / baus_history.json / baus_cache.json
baus_para_importar/          # imports de baús
builds.json                  # builds (252/324/338 + mixes)
analyze_tbh.py               # EnumWindows + WS_EX_LAYERED/TRANSPARENT + mss
extract_chars.py
extract_passivos.py
extract_sprites.py
abrir_conta1..5.bat
abrir_steam.py
icons*/ sprites*
_farm_preview.html
```

## Avisos SrRobs

- Cada caixa Sandboxie tem o seu `SaveFile_Live.es3` — não mistures saves entre contas.
- `analyze_tbh.py` precisa da janela visível (não minimizada) para o mss capturar correto.

## Autor

Roberto Marques (SrRobs)
