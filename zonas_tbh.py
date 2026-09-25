"""
zonas_tbh v11 — ZONAS 675x160 EM PILHA ALINHADA (manual, sem automatismos).

- Cada zona tem TAMANHO FIXO: 675 x 160.
- FAIXAS ENCOSTADAS A DIREITA: as janelas ficam sempre com o lado direito
  colado ao ecra (nada sai pela direita); a zona so' manda na ALTURA.
- "+ Zona": cria a zona ja' no lugar dela da PILHA (zona 1 em cima,
  zona 2 logo abaixo, ...). Arrastar muda a altura da faixa.
- MIRA: botao por zona — mira segue o rato, clicas na JANELA do jogo,
  e ela fica nessa zona. A janela NAO e' redimensionada: fica com o
  tamanho ORIGINAL, o canto superior esquerdo na coordenada da zona
  (a faixa 675x160 e' a parte visivel de cada conta na pilha).
- "Cascata": alinha TODAS as zonas/janelas na pilha (1 em cima, ...).
- "Repor todas": cada janela na coordenada da zona dela.
- TROCA DE ECRA (fisico <-> virtual): as zonas adaptam-se sozinhas ao
  novo ecra (alturas em proporcao, faixas sempre encostadas a direita).
- Nada se move sozinho. Zonas e pids em zonas.json. Logs em zonas.log.
"""
import os
import sys
import time
import json
import ctypes
import traceback

EXE_ALVO = "taskbarhero.exe"
CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zonas.json")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zonas.log")
MARGEM = 4
ZONA_L = 675           # largura fixa de cada zona
ZONA_A = 160           # altura fixa de cada zona
GAP_ZONA = 8           # espaco vertical entre zonas da pilha
MUTEX = "zonas_tbh_v11_unico"
VK_LBUTTON = 0x01
VK_ESCAPE = 0x1B
GA_ROOT = 2
WS_EX_LAYERED = 0x80000
WS_EX_TRANSPARENT = 0x20
GWL_EXSTYLE = -20
COR_FUNDO = "#14110e"
COR_PAINEL = "#1e1a17"
COR_TEXTO = "#e8dcc0"
COR_OURO = "#ffd86b"

try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

import tkinter as tk
from tkinter import ttk

import win32gui
import win32api
import win32con
import win32process as wp

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class PONTO(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


user32.WindowFromPoint.argtypes = [PONTO]
user32.WindowFromPoint.restype = ctypes.c_void_p
user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
user32.GetAncestor.restype = ctypes.c_void_p


def tecla_async(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def eco(msg):
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 400000:
            os.remove(LOG)
        stamp = time.strftime("%H:%M:%S") + "." + str(int((time.time() % 1) * 1000)).rjust(3, "0")
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(stamp + " " + msg + "\n")
    except Exception:
        pass


_wmi_svc = None
_exes = {}


def _wmi():
    global _wmi_svc
    if _wmi_svc is None:
        import win32com.client
        _wmi_svc = win32com.client.GetObject(
            "winmgmts:{impersonationLevel=impersonate}!\\\\.\\root\\cimv2")
    return _wmi_svc


def matar_copias_antigas():
    eu = os.getpid()
    try:
        for p in _wmi().ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process "
                                  "WHERE Name='python.exe' OR Name='pythonw.exe'"):
            cl = str(p.CommandLine or "").lower()
            if "zonas_tbh.py" in cl and "python" in cl and int(p.ProcessId) != eu:
                try:
                    p.Terminate()
                    eco(f"[mutex] copia antiga pid {p.ProcessId} terminada")
                except Exception:
                    pass
    except Exception as e:
        eco(f"[mutex] varredura: {e}")


def unica_instancia():
    kernel32.CreateMutexW(None, False, MUTEX)
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def exe_of(pid):
    agora = time.time()
    c = _exes.get(pid)
    if c and agora - c[1] < 10.0:
        return c[0]
    h = None
    nome = ""
    try:
        h = win32api.OpenProcess(0x1000, False, pid)
        if h:
            buf = ctypes.create_unicode_buffer(2048)
            tam = ctypes.c_ulong(2048)
            if kernel32.QueryFullProcessImageNameW(int(h), 0, buf, ctypes.byref(tam)):
                nome = os.path.basename(buf.value).lower()
    except Exception:
        pass
    finally:
        if h:
            win32api.CloseHandle(h)
    _exes[pid] = (nome, agora)
    return nome


def pid_de(hwnd):
    try:
        return wp.GetWindowThreadProcessId(hwnd)[1]
    except Exception:
        return 0


def janelas_do_jogo(exe):
    achadas = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            _, pid = wp.GetWindowThreadProcessId(hwnd)
        except Exception:
            return
        if pid and exe_of(pid) == exe:
            achadas.append(hwnd)

    win32gui.EnumWindows(cb, None)
    return sorted(achadas)


def janela_do_pid(pid):
    """A janela principal visivel de um pid (de preferencia do jogo)."""
    if not pid:
        return None
    for h in janelas_do_jogo(EXE_ALVO):
        if pid_de(h) == pid:
            return h
    melhor = None

    def cb(hwnd, _):
        nonlocal melhor
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            if wp.GetWindowThreadProcessId(hwnd)[1] == pid:
                if user32.GetAncestor(hwnd, 2) == hwnd:  # GA_ROOT
                    if melhor is None or win32gui.GetWindowText(melhor) == "":
                        melhor = hwnd
        except Exception:
            pass

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    return melhor


def monitores():
    lista = []
    for m in win32api.EnumDisplayMonitors():
        info = win32api.GetMonitorInfo(m[0])
        lista.append((m[0], info["Monitor"], info["Work"]))
    return lista


def posicionar_janela(hwnd, z, work):
    """FAIXA ENCOSTADA A DIREITA: a janela cola o lado direito ao ecra
    (nada sai pela direita); a zona so' manda na ALTURA da faixa.
    O tamanho da janela NAO mexe."""
    try:
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        w, h = r - l, b - t
    except Exception:
        return False
    if w <= 0 or h <= 0:
        return False
    wl, wt, wr, wb = work
    wh = max(1, wb - wt)
    nl = wr - MARGEM - w                     # sempre encostada a direita
    nt = wt + int(z["fy"] * wh)
    nt = max(wt, min(nt, wb - MARGEM - ZONA_A))  # a faixa fica toda no ecra
    try:
        win32gui.MoveWindow(hwnd, nl, nt, w, h, True)
        return True
    except Exception:
        return False


def x_faixa(work, z=None):
    """Canto ESQUERDO da faixa: janela encostada a direita pelo proprio
    tamanho (usa a largura da janela da zona, ou 1455 por defeito)."""
    w = 1455
    if z and z.get("pid"):
        h = janela_do_pid(z["pid"])
        if h:
            try:
                r = win32gui.GetWindowRect(h)
                if r[2] - r[0] > 100:
                    w = r[2] - r[0]
            except Exception:
                pass
    return work[2] - MARGEM - w


def tamanho_zona_px(work):
    """Tamanho fixo das zonas: 675x160 (limitado ao ecra)."""
    wl, wt, wr, wb = work
    return min(ZONA_L, max(1, wr - wl - 2 * MARGEM)), min(ZONA_A, max(1, wb - wt - 2 * MARGEM))


def pos_zona_pilha(i, work):
    """Lugar da zona i na PILHA: faixa encostada a direita, zona 1 em cima."""
    wl, wt, wr, wb = work
    w, h = tamanho_zona_px(work)
    x = x_faixa(work)
    y = wt + MARGEM + i * (h + GAP_ZONA)
    y = min(y, wb - MARGEM - h)
    return x, y


def carregar():
    zonas = []
    if os.path.exists(CFG):
        try:
            dados = json.load(open(CFG, encoding="utf-8"))
            if isinstance(dados, dict) and isinstance(dados.get("zonas"), list):
                for z in dados["zonas"]:
                    if isinstance(z, dict) and "fx" in z and "fy" in z:
                        zonas.append({"pid": int(z.get("pid") or 0),
                                      "fx": float(z["fx"]), "fy": float(z["fy"])})
        except Exception:
            pass
    return zonas


def guardar(zonas):
    try:
        json.dump({"zonas": zonas}, open(CFG, "w", encoding="utf-8"), indent=1)
    except Exception:
        pass


class Painel:
    def __init__(self):
        self.zonas = carregar()
        self.editando = False
        self.arrasto = None  # ("mover", i, dx, dy)
        self.itens = {}      # i -> (rect_id, texto_id, pega_id)
        self.pick = None     # indice da zona em modo MIRA
        self.pick_lb = False
        self.work0 = (0, 0, 0, 0)
        self.sig_mon = None  # assinatura dos monitores (deteta troca de ecra)
        self.mover = False   # modo ARRASTAR
        self.mover_h = None
        self.mover_off = (0, 0)
        self.mover_lb = False

        self.root = tk.Tk()
        self.root.title("Zonas TBH")
        self.root.configure(bg=COR_PAINEL)
        self.root.geometry("700x560")
        self.root.minsize(680, 420)

        # ---- overlay dos retangulos dourados ----
        self.ov = tk.Toplevel(self.root)
        self.ov.overrideredirect(True)
        self.ov.attributes("-topmost", True)
        self.ov.attributes("-transparentcolor", "#010101")
        self.canvas = tk.Canvas(self.ov, bg="#010101", highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True)
        self.ov.withdraw()
        self.ov_hwnd = None
        try:
            self.root.update_idletasks()
            hwnd = self.ov.winfo_id()
            while True:
                pai = user32.GetParent(hwnd)
                if not pai:
                    break
                hwnd = pai
            self.ov_hwnd = hwnd
            est = win32api.GetWindowLong(hwnd, GWL_EXSTYLE)
            win32api.SetWindowLong(hwnd, GWL_EXSTYLE, est | WS_EX_LAYERED)
        except Exception as e:
            eco(f"[erro] overlay init: {e}")

        # ---- UI do painel ----
        topo = tk.Frame(self.root, bg=COR_PAINEL)
        topo.pack(fill="x", padx=8, pady=(8, 4))
        self.bt_add = self._botao(topo, "+ Zona", self.add_zona)
        self.bt_editar = self._botao(topo, "Editar", lambda: self.editar(not self.editando))
        self._botao(topo, "Cascata", self.cascata)
        self._botao(topo, "Centro", self.centrar_todos)
        self.bt_mover = self._botao(topo, "Arrastar", lambda: self.modo_arrastar(None))
        self._botao(topo, "Repor", self.repor_todas)
        self._botao(topo, "Apagar tudo", self.apagar_tudo)

        self.lbl_pids = tk.Label(self.root, bg=COR_PAINEL, fg=COR_OURO, justify="left",
                                 wraplength=430, font=("Segoe UI", 9, "bold"), text="")
        self.lbl_pids.pack(fill="x", padx=8, pady=4)

        tk.Label(self.root, bg=COR_PAINEL, fg="#a89878", text="ZONAS — pid por zona (do gestor de tarefas):",
                 font=("Segoe UI", 9, "bold")).pack(fill="x", padx=8)
        self.lista = tk.Frame(self.root, bg=COR_PAINEL)
        self.lista.pack(fill="both", expand=True, padx=8, pady=4)

        self.status = tk.Label(self.root, bg=COR_PAINEL, fg=COR_TEXTO, anchor="w",
                               wraplength=430, font=("Segoe UI", 9), text="pronto")
        self.status.pack(fill="x", side="bottom", padx=8, pady=6)

        self.root.protocol("WM_DELETE_WINDOW", self.sair)
        self.ov.bind("<Escape>", lambda e: self.editar(False))
        self.root.bind("<Escape>", lambda e: self.editar(False))

        self.refrescar()
        self._ciclo()
        eco("=== zonas_tbh v11 (zonas 675x160 em pilha) === iniciado")

    # ---------- helpers UI ----------
    def _botao(self, pai, txt, cmd):
        b = tk.Button(pai, text=txt, command=cmd, bg="#2a241f", fg=COR_OURO,
                      activebackground="#3a3128", activeforeground=COR_OURO,
                      relief="flat", font=("Segoe UI", 9, "bold"), padx=6)
        b.pack(side="left", padx=(0, 4))
        return b

    def dizer(self, msg):
        self.status.configure(text=msg)

    def area(self):
        """Area de trabalho: preferencia para o MONITOR ONDE ESTA' O JOGO
        (adapta-se ao mudar de ecra fisico/virtual); senao o do cursor."""
        ms = monitores()
        try:
            js = janelas_do_jogo(EXE_ALVO)
            if js:
                l, t, r, b = win32gui.GetWindowRect(js[0])
                hm = win32api.MonitorFromRect((l, t, r, b), win32con.MONITOR_DEFAULTTONEAREST)
                for m in ms:
                    if m[0] == hm:
                        return m[2]
        except Exception:
            pass
        try:
            pt = win32api.GetCursorPos()
            hm = win32api.MonitorFromPoint(pt, win32con.MONITOR_DEFAULTTONEAREST)
            for m in ms:
                if m[0] == hm:
                    return m[2]
        except Exception:
            pass
        return ms[0][2]

    # ---------- lista de zonas ----------
    def refrescar(self):
        for w in self.lista.winfo_children():
            w.destroy()
        if not self.zonas:
            tk.Label(self.lista, bg=COR_PAINEL, fg="#6f6350",
                     text="(sem zonas — carrega + Zona)").pack(pady=20)
            return
        for i, z in enumerate(self.zonas):
            linha = tk.Frame(self.lista, bg=COR_PAINEL)
            linha.pack(fill="x", pady=2)
            tk.Label(linha, bg=COR_PAINEL, fg=COR_OURO, width=7, anchor="w",
                     font=("Segoe UI", 10, "bold"), text=f"Zona {i + 1}").pack(side="left")
            if z.get("pid"):
                vivo = "" if janela_do_pid(z["pid"]) else "  (fechada)"
                tk.Label(linha, bg=COR_PAINEL, fg="#7dff7d", font=("Consolas", 10),
                         text=f"pid {z['pid']}{vivo}").pack(side="left", padx=(2, 8))
            else:
                tk.Label(linha, bg=COR_PAINEL, fg="#8a7a5f", font=("Segoe UI", 9),
                         text="sem conta").pack(side="left", padx=(2, 8))
            tk.Button(linha, text="🎯 Mira", command=lambda i=i: self.mirar(i),
                      bg="#26331c", fg="#7dff7d", activebackground="#31452a",
                      relief="flat", font=("Segoe UI", 9, "bold"), padx=6).pack(side="left", padx=(0, 4))
            tk.Button(linha, text="✕", command=lambda i=i: self.apagar_zona(i),
                      bg="#3a1d1d", fg="#ff8080", activebackground="#4a2424",
                      relief="flat", font=("Segoe UI", 10, "bold"), width=3).pack(side="left")

    # ---------- acoes ----------
    def add_zona(self):
        """Zona nova (675x160) ja' no lugar dela da PILHA alinhada a direita:
        zona 1 em cima, zona 2 logo abaixo, ..."""
        work = self.area()
        wl, wt, wr, wb = work
        ww, wh = max(1, wr - wl), max(1, wb - wt)
        idx = len(self.zonas)
        x, y = pos_zona_pilha(idx, work)
        fx = round(max(0.0, min(0.99, (x - wl) / ww)), 4)
        fy = round(max(0.0, min(0.99, (y - wt) / wh)), 4)
        self.zonas.append({"pid": 0, "fx": fx, "fy": fy})  # so' coordenadas
        guardar(self.zonas)
        eco(f"[zona] adicionada zona {idx + 1} na pilha ({fx}, {fy})")
        self.refrescar()
        self.editar(True)  # mostra o retangulo dourado da zona nova
        self.dizer(f"Zona {idx + 1} criada na pilha — arrasta para ajustar")

    def apagar_zona(self, i):
        z = self.zonas.pop(i)
        guardar(self.zonas)
        eco(f"[zona] apagada zona {i + 1} (pid {z.get('pid')})")
        self.refrescar()
        if self.editando:
            self._desenhar()
        self.dizer(f"Zona {i + 1} apagada")

    def apagar_tudo(self):
        self.zonas = []
        guardar(self.zonas)
        eco("[zona] TODAS apagadas")
        self.editar(False)
        self.refrescar()
        self.dizer("Todas as zonas apagadas")

    def atribuir(self, i, pid, hwnd=None):
        """Associa a janela (pid) a' zona i; a janela salta para a zona
        com o tamanho dela (675x160)."""
        for j, zz in enumerate(self.zonas):
            if j != i and zz.get("pid") == pid:
                zz["pid"] = 0  # conta so' pode estar numa zona
        z = self.zonas[i]
        z["pid"] = pid
        h = hwnd or janela_do_pid(pid)
        if h:
            posicionar_janela(h, z, self.area())
        guardar(self.zonas)
        eco(f"[zona] zona {i + 1} <- pid {pid}")
        self.refrescar()
        self.dizer(f"Zona {i + 1}: pid {pid} — janela na zona, tamanho original")

    # ---------- MIRA: clica na janela para a associar ----------
    def mirar(self, i):
        if self.editando:
            self.editar(False)
        self.pick = i
        self.pick_lb = tecla_async(VK_LBUTTON)
        work = self.area()
        self.work0 = work
        wl, wt, wr, wb = work
        self.ov.geometry(f"{wr - wl}x{wb - wt}+{wl}+{wt}")
        self.canvas.configure(width=wr - wl, height=wb - wt)
        self._click_through(True)
        self._desenhar_mira()
        self.ov.deiconify()
        self.dizer(f"MIRA — clica na janela da conta para a Zona {i + 1} · Esc cancela")
        eco(f"[mira] a apontar zona {i + 1}")
        self.root.after(20, self._poll_mira)

    def _desenhar_mira(self):
        wl, wt, wr, wb = self.work0
        ww, wh = wr - wl, wb - wt
        self.canvas.delete("all")
        for j, z in enumerate(self.zonas):
            w, h = tamanho_zona_px(self.work0)
            x = x_faixa(self.work0, z)
            y = wt + z["fy"] * wh
            alvo = (j == self.pick)
            self.canvas.create_rectangle(x, y, x + w, y + h,
                                         outline="#7dff7d" if alvo else COR_OURO,
                                         width=5 if alvo else 2,
                                         dash=None if alvo else (8, 6))
            self.canvas.create_text(x + 10, y + 18, anchor="w",
                                    text=f"ZONA {j + 1}" + (f"  pid {z['pid']}" if z.get("pid") else ""),
                                    fill="#7dff7d" if alvo else COR_OURO,
                                    font=("Segoe UI", 10, "bold"))
        self.canvas.create_text(ww // 2, wh - 26,
                                text=f"MIRA — clica na janela para a ZONA {self.pick + 1} · Esc cancela",
                                fill="#7dff7d", font=("Segoe UI", 12, "bold"))

    def _poll_mira(self):
        if self.pick is None:
            return
        if tecla_async(VK_ESCAPE):
            eco("[mira] cancelada")
            self.dizer("Mira cancelada")
            self._fim_mira()
            return
        # mira (crosshair) segue o rato
        try:
            self.canvas.delete("mira")
            pt = win32gui.GetCursorPos()
            x = pt[0] - self.work0[0]
            y = pt[1] - self.work0[1]
            self.canvas.create_line(x - 16, y, x + 16, y, fill="#ff5050", width=2, tags="mira")
            self.canvas.create_line(x, y - 16, x, y + 16, fill="#ff5050", width=2, tags="mira")
            self.canvas.create_oval(x - 11, y - 11, x + 11, y + 11, outline="#ff5050", width=2, tags="mira")
        except Exception:
            pass
        lb = tecla_async(VK_LBUTTON)
        if lb and not self.pick_lb:
            pt = win32gui.GetCursorPos()
            hwnd = user32.WindowFromPoint(PONTO(pt[0], pt[1]))
            raiz = user32.GetAncestor(hwnd, GA_ROOT) if hwnd else None
            pid = 0
            if raiz:
                try:
                    _, pid = wp.GetWindowThreadProcessId(int(raiz))
                except Exception:
                    pid = 0
            if pid:
                self.atribuir(self.pick, pid, int(raiz))
                self._fim_mira()
                return
        self.pick_lb = lb
        self.root.after(20, self._poll_mira)

    def _fim_mira(self):
        self.pick = None
        self._click_through(False)
        self.ov.withdraw()

    def _click_through(self, on):
        if not self.ov_hwnd:
            return
        try:
            est = win32api.GetWindowLong(self.ov_hwnd, GWL_EXSTYLE)
            if on:
                win32api.SetWindowLong(self.ov_hwnd, GWL_EXSTYLE, est | WS_EX_TRANSPARENT)
            else:
                win32api.SetWindowLong(self.ov_hwnd, GWL_EXSTYLE, est & ~WS_EX_TRANSPARENT)
        except Exception as e:
            eco(f"[erro] click_through: {e}")

    def repor_todas(self):
        work = self.area()
        colocadas = 0
        for i, z in enumerate(self.zonas):
            if not z.get("pid"):
                continue
            h = janela_do_pid(z["pid"])
            if h and posicionar_janela(h, z, work):
                colocadas += 1
        # empilhar: zona 1 por cima
        for z in self.zonas:
            h = janela_do_pid(z.get("pid")) if z.get("pid") else None
            if h:
                try:
                    win32gui.SetWindowPos(h, win32con.HWND_BOTTOM, 0, 0, 0, 0,
                                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
                except Exception:
                    pass
        eco(f"[repor] {colocadas} janelas repostas nas zonas")
        self.dizer(f"Repostas: {colocadas} de {len(self.zonas)} zonas")

    # ---------- ARRASTAR com o rato (janelas borderless nao teem barra) ----------
    def modo_arrastar(self, on):
        """Modo ARRASTAR: clicar numa janela do jogo e LARGAR = a janela
        segue o rato (as janelas do jogo nao teem barra de titulo)."""
        if on is None:
            on = not self.mover
        if self.pick is not None or self.editando:
            return
        self.mover = on
        self.bt_mover.configure(text="Arrastar ON" if on else "Arrastar")
        if on:
            work = self.area()
            self.work0 = work
            wl, wt, wr, wb = work
            self.ov.geometry(f"{wr - wl}x{wb - wt}+{wl}+{wt}")
            self.canvas.configure(width=wr - wl, height=wb - wt)
            self.canvas.delete("all")
            self.canvas.create_text((wr - wl) // 2, 16,
                                    text="ARRASTAR — clica numa janela do jogo e arrasta com o rato · Esc sai",
                                    fill="#7dff7d", font=("Segoe UI", 11, "bold"))
            self._click_through(True)
            self.ov.deiconify()
            self.mover_h = None
            self.mover_lb = tecla_async(VK_LBUTTON)
            eco("[arrastar] modo ligado")
            self.root.after(15, self._poll_arrastar)
        else:
            self.mover_h = None
            self._click_through(False)
            self.ov.withdraw()
            eco("[arrastar] modo desligado")

    def _poll_arrastar(self):
        if not self.mover:
            return
        if tecla_async(VK_ESCAPE):
            self.dizer("Arrastar desligado")
            self.modo_arrastar(False)
            return
        lb = tecla_async(VK_LBUTTON)
        if lb and not self.mover_lb and self.mover_h is None:
            pt = win32gui.GetCursorPos()
            hwnd = user32.WindowFromPoint(PONTO(pt[0], pt[1]))
            raiz = user32.GetAncestor(hwnd, GA_ROOT) if hwnd else None
            if raiz:
                try:
                    _, pid = wp.GetWindowThreadProcessId(int(raiz))
                    if pid and exe_of(pid) == EXE_ALVO:
                        self.mover_h = int(raiz)
                        l, t, r, b = win32gui.GetWindowRect(self.mover_h)
                        self.mover_off = (pt[0] - l, pt[1] - t)
                        eco(f"[arrastar] a pegar {hex(self.mover_h)} pid {pid}")
                except Exception:
                    pass
        if self.mover_h is not None and lb:
            pt = win32gui.GetCursorPos()
            try:
                l, t, r, b = win32gui.GetWindowRect(self.mover_h)
                w, hh = r - l, b - t
                wl, wt, wr, wb = self.work0
                nl = pt[0] - self.mover_off[0]
                nt = pt[1] - self.mover_off[1]
                nl = max(wl - w + 220, min(nl, wr - 220))  # sempre um bocado visivel
                nt = max(wt - hh + 60, min(nt, wb - 60))
                win32gui.MoveWindow(self.mover_h, nl, nt, w, hh, True)
            except Exception:
                self.mover_h = None
        elif not lb and self.mover_h is not None:
            eco("[arrastar] largou")
            self.mover_h = None
        self.mover_lb = lb
        self.root.after(15, self._poll_arrastar)

    # ---------- todas no centro do ecra ----------
    def centrar_todos(self):
        """Todas as janelas do jogo no CENTRO do ecra. A barra de titulo
        fica SEMPRE visivel (nunca sai pelo topo), com pequena cascata."""
        work = self.area()
        wl, wt, wr, wb = work
        js = janelas_do_jogo(EXE_ALVO)
        n = 0
        for i, h in enumerate(js):
            try:
                l, t, r, b = win32gui.GetWindowRect(h)
                w, hh = r - l, b - t
            except Exception:
                continue
            if w <= 0 or hh <= 0:
                continue
            nl = max(wl, wl + (wr - wl - w) // 2)
            nt = wt + min(i * 30, max(0, wb - wt - 60))  # titulo sempre visivel
            nt = max(wt, min(nt, wb - MARGEM - 60))
            try:
                win32gui.MoveWindow(h, nl, nt, w, hh, True)
                n += 1
            except Exception:
                pass
        eco(f"[centro] {n} janelas centradas (titulo sempre visivel)")
        self.dizer(f"{n} janelas no centro — Repor volta a po-las nas zonas")

    # ---------- alinhamento em pilha ----------
    def cascata(self):
        """Todas as zonas/janelas na PILHA alinhada a direita:
        zona 1 em cima, zona 2 logo abaixo, ... (675x160)."""
        work = self.area()
        wl, wt, wr, wb = work
        ww, wh = max(1, wr - wl), max(1, wb - wt)
        colocadas = []
        for i, z in enumerate(self.zonas):
            x, y = pos_zona_pilha(i, work)
            z["fx"] = round(max(0.0, min(0.99, (x - wl) / ww)), 4)
            z["fy"] = round(max(0.0, min(0.99, (y - wt) / wh)), 4)
            if z.get("pid"):
                h = janela_do_pid(z["pid"])
                if h and posicionar_janela(h, z, work):
                    colocadas.append(h)
        guardar(self.zonas)
        # empilhar ao contrario: a ULTIMA zona fica a frente — assim a faixa
        # 675x160 de cada janela fica visivel (as de baixo tapam so' o corpo)
        for h in reversed(colocadas):
            try:
                win32gui.SetWindowPos(h, win32con.HWND_BOTTOM, 0, 0, 0, 0,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
            except Exception:
                pass
        eco(f"[pilha] {len(colocadas)} janelas alinhadas — tamanho original")
        self.refrescar()
        if self.editando:
            self._desenhar()
        self.dizer(f"Pilha: {len(self.zonas)} zonas — janelas com tamanho original, faixas visiveis")

    # ---------- modo edicao (retangulos dourados arrastaveis) ----------
    def editar(self, on):
        if self.pick is not None:
            return  # mira a decorrer
        self.editando = on
        self.bt_editar.configure(text="Terminar edicao" if on else "Editar posicoes")
        if on:
            self._desenhar()
            self.ov.deiconify()
            self.dizer("Edicao: arrasta os retangulos dourados · Esc ou botao para terminar")
        else:
            self.ov.withdraw()
            if self.arrasto is not None:
                self.arrasto = None

    def _desenhar(self):
        work = self.area()
        wl, wt, wr, wb = work
        ww, wh = wr - wl, wb - wt
        w, h = tamanho_zona_px(work)
        self.ov.geometry(f"{ww}x{wh}+{wl}+{wt}")
        self.canvas.configure(width=ww, height=wh)
        self.canvas.delete("all")
        self.canvas.create_text(ww // 2, 16,
                                text="EDITAR ZONAS — arrasta p/ mudar a ALTURA (faixa sempre a direita) · Esc termina",
                                fill=COR_OURO, font=("Segoe UI", 11, "bold"))
        for i, z in enumerate(self.zonas):
            x = x_faixa(work, z)
            y = wt + z["fy"] * wh
            tag = f"z{i}"
            rotulo = f"ZONA {i + 1}" + (f"  pid {z['pid']}" if z.get("pid") else "")
            self.canvas.create_rectangle(x, y, x + w, y + h, outline=COR_OURO, width=3,
                                         dash=(8, 6), tags=tag)
            self.canvas.create_text(x + 10, y + 18, anchor="w", text=rotulo, fill=COR_OURO,
                                    font=("Segoe UI", 10, "bold"), tags=tag)
            self.canvas.tag_bind(tag, "<Button-1>", lambda e, i=i: self._pega(e, i))
            self.canvas.tag_bind(tag, "<B1-Motion>", lambda e, i=i: self._move(e, i))
            self.canvas.tag_bind(tag, "<ButtonRelease-1>", lambda e, i=i: self._larga(i))

    def _pega(self, e, i):
        c = self.canvas.coords(f"z{i}")
        self.arrasto = ("mover", i, e.x - c[0], e.y - c[1])

    def _move(self, e, i):
        if not self.arrasto or self.arrasto[0] != "mover" or self.arrasto[1] != i:
            return
        _, _, dx, dy = self.arrasto
        c = self.canvas.coords(f"z{i}")
        self.canvas.move(f"z{i}", (e.x - dx) - c[0], (e.y - dy) - c[1])

    def _larga(self, i):
        if self.arrasto is None:
            return
        self.arrasto = None
        work = self.area()
        wl, wt, wr, wb = work
        ww, wh = max(1, wr - wl), max(1, wb - wt)
        c = self.canvas.coords(f"z{i}")
        y = c[1]
        z = self.zonas[i]
        # a faixa e' sempre encostada a direita: so' a ALTURA interessa
        z["fx"] = round(max(0.0, min(0.99, (x_faixa(work, z) - wl) / ww)), 4)
        fy_max = max(0.0, min(0.99, (wb - MARGEM - ZONA_A - wt) / wh))
        z["fy"] = round(max(0.0, min(fy_max, y / wh)), 4)
        guardar(self.zonas)
        if z.get("pid"):
            h = janela_do_pid(z["pid"])
            if h:
                posicionar_janela(h, z, work)
        eco(f"[zona] zona {i + 1} -> altura ({z['fy']})")
        self._desenhar()
        self.dizer(f"Zona {i + 1} gravada nesta altura")

    # ---------- ciclo ----------
    def _ciclo(self):
        try:
            # troca de ecra (fisico <-> virtual): zonas adaptam-se sozinhas
            sig = repr(monitores())
            if self.sig_mon is None:
                self.sig_mon = sig
            elif sig != self.sig_mon:
                self.sig_mon = sig
                eco(f"[ecra] monitores mudaram — a adaptar as zonas")
                self.repor_todas()
            js = janelas_do_jogo(EXE_ALVO)
            if js:
                partes = []
                for h in js:
                    try:
                        l, t, r, b = win32gui.GetWindowRect(h)
                        partes.append(f"{pid_de(h)} ({r - l}x{b - t})")
                    except Exception:
                        partes.append(str(pid_de(h)))
                txt = "Pids do jogo: " + ", ".join(partes)
            else:
                txt = "Pids do jogo: (nenhuma janela do jogo aberta)"
            self.lbl_pids.configure(text=txt)
        except Exception:
            pass
        self.root.after(2000, self._ciclo)

    def sair(self):
        eco("=== fim ===")
        try:
            self.ov.destroy()
        except Exception:
            pass
        self.root.destroy()


def main():
    matar_copias_antigas()
    if not unica_instancia():
        user32.MessageBoxW(0, "O zonas_tbh ja esta a correr.", "zonas_tbh", 0)
        return
    try:
        Painel()
        tk.mainloop()
    except Exception:
        eco("[erro] " + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
