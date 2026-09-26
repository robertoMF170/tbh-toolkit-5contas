# Robs Farmer — CS2

> App desktop para CS2 com **CustomTkinter** (900×650 dark), **Arduino Leonardo** opcional ou **vgamepad** virtual, **hotkey F8** global e ritmo humanizado.

![Python](https://img.shields.io/badge/Python-3.11-blue) ![CustomTkinter](https://img.shields.io/badge/CustomTkinter-dark-black) ![Arduino](https://img.shields.io/badge/Arduino-Leonardo-teal) ![CS2](https://img.shields.io/badge/CS2-input--sim-red)

## O que faz

- Janela **900×650** em `CustomTkinter` dark (`#16161b`), deteta CS2 via `psutil`, **hotkey F8** (WM_HOTKEY) para ciclo rápido ligado/desligado.
- `input_sim.py` com **SCAN codes** + `arduino_link.py` (Leonardo) ou **vgamepad** como fallback — movimento e pausas com timing humanizado (não robótico).
- Modo remoto via **socket** (`farmer_config.json`: destino Local/Remoto, host, token), vídeo opcional e gestão multi-processo.
- Build para `.exe` via `build_exe.bat` / `.spec`.

## Como funciona

```
[CustomTkinter App 900×650] ─► psutil (CS2 detect) ─► input_sim.py (SCAN + timing)
        │   ▲ F8 (WM_HOTKEY)                               ├─► arduino_link.py ─► Leonardo (.ino)
        │   │                                              └─► vgamepad (fallback virtual)
        └──► agent.py (socket) ◄─► farmer_config.json (Local/Remoto, host, token)
```

## Stack

Python 3.11, CustomTkinter, psutil, pillow, ctypes/win32, Arduino Leonardo, vgamepad, PyInstaller

## Passo a passo — instalar e correr

```bash
# 1. Clone
git clone https://github.com/robertoMF170/robos-farmer-cs2.git
cd robos-farmer-cs2

# 2. Ambiente
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# Reqs: customtkinter, psutil, pillow, vgamepad (opcional), pyserial

# 3. Configuração
# Edita farmer_config.json:
# {
#   "destino": "Local",   // ou "Remoto"
#   "host": "127.0.0.1",
#   "port": 8765,
#   "token": "muda-isto",
#   "arduino_port": "COM3"   // ou null para vgamepad
# }

# 4. Arduino (opcional)
# Abre Arduino IDE → robs_farmer.ino → Upload para Leonardo

# 5. Correr
python main.py          # abre a janela
# ou
iniciar.bat             # arranque rápido (Windows)

# 6. Atalho global
# F8 = liga/desliga ciclo

# 7. Build .exe
build_exe.bat
# ou
pyinstaller "CS2 Robs Farmer.spec"
# → dist/CS2 Robs Farmer.exe
```

## Estrutura

```
main.py                # App ctk.CTk (janela principal)
agent.py               # Daemon remoto (socket)
input_sim.py           # SCAN codes + ritmo humanizado
arduino_link.py        # Serial para Leonardo
vgamepad/              # Driver virtual fallback
farmer_config.json     # Destino/host/token/porta
robs_farmer.ino        # Sketch do Leonardo
CS2 Robs Farmer.spec   # PyInstaller
Robs Farmer Agent.spec
build_exe.bat
iniciar.bat
```

## Avisos SrRobs

- Requer CS2 focado — não injeta no jogo, só simula input do SO.
- Arduino é o modo mais “humano”; vgamepad é fallback.
- Mantém `farmer_config.json` fora do git (está no `.gitignore`).

## Autor

Roberto Marques (SrRobs)
