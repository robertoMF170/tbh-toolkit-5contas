# Bug Report: TBH Task Bar Hero — black background around overlay when sandboxed

## Para: sandboxie-plus/Sandboxie (GitHub Issues) — em inglês

**Title:** Layered/transparent overlay window renders with black background in sandbox after game update (Unity game, WS_EX_LAYERED)

**Environment:**
- Sandboxie Plus: SbieSvc/Sandboxie 5.73.2 (latest is 1.18.4 / 5.73.4 — will retest after upgrade)
- Windows 10/11 x64 with 2026-09 updates (KB5124008, KB5124007, KB5126052, KB5054156)
- Game: "TBH: Task Bar Hero" (Steam AppID 3678970), Unity engine, version 1.2.3 (buildid 25299976), auto-updated 2026-09-15 ~13:04
- Sandbox box: "Steam2", standard config, `NoRenameWinClass=UnityWndClass`

**Issue:**
The game draws an always-on overlay over the Windows taskbar using a click-through layered window. After the game updated to v1.2.3, the sandboxed instance shows a solid BLACK background around/behind the game graphics (the previously transparent area). The same game version running OUTSIDE the sandbox renders perfectly — so it only reproduces sandboxed. Before this update the sandboxed game rendered fine.

**Measured evidence (pixel analysis of the sandboxed window):**
- Window class: `UnityWndClass`, title "TaskBarHero"
- Extended styles: `0x80028` = `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW`
- Window/client rect: 1455 x 1338 px borderless overlay covering the taskbar area
- 6px border band around the overlay: **52.87% near-black pixels**, mean RGB (17,16,16)
- Overall overlay area: 17.43% near-black
- Same analysis outside sandbox: normal (transparent, no black)

**Box config:**
```ini
[Steam2]
NoRenameWinClass=UnityWndClass
Enabled=y
ConfigLevel=10
BorderColor=#FF00FF,ttl
Template=LingerPrograms
Template=BlockPorts
Template=qWave
Template=FileCopy
Template=SkipHook
Template=OpenBluetooth
```

**Repro:**
1. Install game via Steam (AppID 3678970), let it update to 1.2.3 (buildid 25299976)
2. Run game inside any sandbox (Start.exe /box:MyBox TaskBarHero.exe)
3. Overlay heroes walk on taskbar but with a black band/background around them
4. Run same exe outside sandbox → renders correctly

**Suspect:** the new Unity build changed how the layered window presents its alpha channel (e.g. UpdateLayeredWindow / DirectComposition change); inside the sandbox the transparency is lost and black is displayed instead.

---

## Para o developer do jogo (Steam / Discord) — resumo

O update de hoje (v1.2.3, buildid 25299976) fez o overlay da taskbar perder a transparência
quando o jogo corre dentro do Sandboxie Plus (janela LAYERED+TRANSPARENT renderiza com fundo
preto). Fora da sandbox funciona bem. Se mudaram a forma de apresentar a janela
(UpdateLayeredWindow, alpha, DirectComposition, etc.), agradecia compatibilidade com
window-managers/sandboxes. Obrigado!

---

## Timeline local (evidência)
- 2026-09-12 23:21 — Sandboxie Plus 5.73.2 (re)instalado
- 2026-09-15 13:04 — Steam atualizou o jogo para 1.2.3 (34.3 MB)
- 2026-09-15 13:17 — primeiras capturas do bug (verif_0.png)
- Análise: analyze_tbh.py / analysis_result.json na pasta do projeto
