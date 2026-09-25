import os
import sys
import time
import queue
import threading
import ctypes
import tkinter as tk
from tkinter import ttk

import numpy as np
import cv2
import mss
import winsound
import win32gui
import win32con
import win32api
import win32process
import pyautogui

pyautogui.FAILSAFE = False
ctypes.windll.user32.SetProcessDPIAware()

BASE = os.path.dirname(os.path.abspath(__file__))
TPL_DIR = os.path.join(BASE, "templates")
GAME_EXE = "taskbarhero.exe"
VK_F8 = 0x77
VK_LBUTTON = 0x01
GA_ROOT = 2

CATS = ("bau", "cubo", "menu", "sintese")


def load_templates():
    cats = {c: [] for c in CATS}
    cats["sprite"] = []
    if not os.path.isdir(TPL_DIR):
        return cats
    for f in sorted(os.listdir(TPL_DIR)):
        if not f.endswith(".png"):
            continue
        img = cv2.imread(os.path.join(TPL_DIR, f), cv2.IMREAD_GRAYSCALE)
        if img is None or img.shape[0] < 10 or img.shape[1] < 10:
            continue
        base = f[:-4]
        if base.startswith("tela_learn"):
            cat = "bau"
        elif base.startswith("tela_"):
            cat = base.split("_")[1] if base.split("_")[1] in CATS else "bau"
        else:
            cat = "sprite"
        cats[cat].append((base, img))
    return cats


CATEGORIES = load_templates()


def exe_of(pid):
    try:
        h = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
        try:
            return os.path.basename(win32process.GetModuleFileNameEx(h, 0)).lower()
        finally:
            win32api.CloseHandle(h)
    except Exception:
        return ""


def find_game_windows():
    out = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return
        if exe_of(pid) != GAME_EXE:
            return
        out.append({"hwnd": hwnd, "pid": pid, "title": win32gui.GetWindowText(hwnd)})
    win32gui.EnumWindows(cb, None)
    return out


def client_box(hwnd):
    l, t, r, b = win32gui.GetClientRect(hwnd)
    pt = win32gui.ClientToScreen(hwnd, (l, t))
    return {"left": pt[0], "top": pt[1], "width": r - l, "height": b - t}


def post_click(hwnd, x, y):
    lp = (int(y) << 16) | (int(x) & 0xFFFF)
    win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lp)
    time.sleep(0.02)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
    time.sleep(0.05)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lp)


def grab_region(x, y, w, h):
    x = max(0, int(x))
    y = max(0, int(y))
    with mss.MSS() as sct:
        img = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


def nms(points, thresh_dist=45):
    kept = []
    for p in points:
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 > thresh_dist ** 2 for q in kept):
            kept.append(p)
    return kept


def find_hits(gray, templates, threshold):
    hits = []
    for name, tpl in templates:
        th, tw = tpl.shape[:2]
        if th >= gray.shape[0] or tw >= gray.shape[1]:
            continue
        res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(res >= threshold)
        for x, y in zip(xs, ys):
            hits.append((int(x + tw / 2), int(y + th / 2)))
    return hits


class Instance(threading.Thread):
    def __init__(self, info, mode, interval, threshold, events, capacity=0, sound_chest=True, auto_syn=False, syn_crafts=5):
        super().__init__(daemon=True)
        self.hwnd = info["hwnd"]
        self.pid = info["pid"]
        self.mode = mode
        self.interval = interval
        self.threshold = threshold
        self.events = events
        self.capacity = capacity
        self.sound_chest = sound_chest
        self.auto_syn = auto_syn
        self.syn_crafts = syn_crafts
        self.chests = 0
        self.stop_flag = threading.Event()

    def run(self):
        while not self.stop_flag.is_set():
            if win32api.GetAsyncKeyState(VK_F8) & 0x8000:
                self.events.put(("stopall", self.pid, 0))
                break
            try:
                box = client_box(self.hwnd)
                if box["width"] < 50 or box["height"] < 20:
                    self.events.put(("status", self.pid, "janela invalida/minimizada"))
                    time.sleep(1)
                    continue
                with mss.MSS() as sct:
                    img = np.array(sct.grab(box))
                gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                hits = find_hits(gray, CATEGORIES["bau"], self.threshold)
                hits += find_hits(gray, CATEGORIES["sprite"], min(0.92, self.threshold + 0.12))
                hits = nms(hits)
                for x, y in hits:
                    if self.stop_flag.is_set():
                        break
                    if self.mode == "post":
                        post_click(self.hwnd, x, y)
                    else:
                        pyautogui.click(box["left"] + x, box["top"] + y)
                    self.chests += 1
                    if self.sound_chest:
                        winsound.Beep(1300, 25)
                    self.events.put(("chest", self.pid, self.chests))
                    if self.capacity and self.chests >= self.capacity:
                        for _ in range(3):
                            winsound.Beep(700, 140)
                            winsound.Beep(1000, 140)
                        if self.auto_syn:
                            self.events.put(("status", self.pid, "cheio: a abrir CUBO + SINTESE..."))
                            self.do_synthesis()
                            self.chests = 0
                            self.events.put(("chest", self.pid, 0))
                            self.events.put(("syn", self.pid, 0))
                            time.sleep(1.0)
                        else:
                            self.events.put(("full", self.pid, self.chests))
                            return
                        break
                    time.sleep(0.15)
                if not hits:
                    self.events.put(("status", self.pid, "a procura de baus..."))
                time.sleep(self.interval / 1000.0)
            except Exception as e:
                self.events.put(("status", self.pid, "erro: " + str(e)[:60]))
                time.sleep(1)

    def do_synthesis(self):
        # fase 1: abrir o cubo
        opened = False
        for _ in range(4):
            if self.stop_flag.is_set():
                return
            try:
                box = client_box(self.hwnd)
                gray = cv2.cvtColor(grab_region(box["left"], box["top"], box["width"], box["height"]), cv2.COLOR_BGR2GRAY)
                hits = nms(find_hits(gray, CATEGORIES["cubo"], self.threshold))
                if hits:
                    x, y = hits[0]
                    if self.mode == "post":
                        post_click(self.hwnd, x, y)
                    else:
                        pyautogui.click(box["left"] + x, box["top"] + y)
                    opened = True
                    self.events.put(("status", self.pid, "cubo aberto"))
                    break
            except Exception as e:
                self.events.put(("status", self.pid, "cubo erro: " + str(e)[:40]))
            time.sleep(0.5)
        if not opened:
            self.events.put(("status", self.pid, "cubo nao encontrado - retomo a apanha"))
            return
        time.sleep(1.5)
        # fase 2: sintese (craft) repetida
        for i in range(self.syn_crafts):
            if self.stop_flag.is_set():
                return
            try:
                box = client_box(self.hwnd)
                gray = cv2.cvtColor(grab_region(box["left"], box["top"], box["width"], box["height"]), cv2.COLOR_BGR2GRAY)
                hits = nms(find_hits(gray, CATEGORIES["sintese"], self.threshold))
                if not hits:
                    self.events.put(("status", self.pid, f"sintese: botao nao visto (#{i+1})"))
                    time.sleep(0.8)
                    continue
                x, y = hits[0]
                if self.mode == "post":
                    post_click(self.hwnd, x, y)
                else:
                    pyautogui.click(box["left"] + x, box["top"] + y)
                self.events.put(("status", self.pid, f"sintese: item #{i+1}"))
            except Exception as e:
                self.events.put(("status", self.pid, "sintese erro: " + str(e)[:40]))
            time.sleep(1.2)


class App:
    def __init__(self, root):
        self.root = root
        root.title("DarkMode")
        root.geometry("860x500")
        self.queue = queue.Queue()
        self.workers = {}
        self.rows = {}
        self.learn_on = False
        self.learn_count = len([f for f in os.listdir(TPL_DIR) if f.startswith("tela_")])

        style = ttk.Style()
        style.theme_use("clam")
        dark = "#161310"
        panel = "#1d1913"
        gold = "#ffd86b"
        root.config(bg=dark)
        style.configure(".", background=dark, foreground="#e8dcc0", fieldbackground=panel)
        style.configure("TFrame", background=dark)
        style.configure("TLabel", background=dark, foreground="#e8dcc0")
        style.configure("TButton", background="#241f18", foreground=gold, bordercolor="#5a4e38")
        style.map("TButton", background=[("active", "#2a2317")])
        style.configure("TCheckbutton", background=dark, foreground="#e8dcc0")
        style.map("TCheckbutton", background=[("active", dark)])
        style.configure("TRadiobutton", background=dark, foreground="#e8dcc0")
        style.map("TRadiobutton", background=[("active", dark)])
        style.configure("TEntry", fieldbackground=panel, foreground="#e8dcc0")
        style.configure("Treeview", background=panel, foreground="#e8dcc0", fieldbackground=panel, rowheight=24)
        style.configure("Treeview.Heading", background="#241f18", foreground=gold)
        style.map("Treeview", background=[("selected", gold)], foreground=[("selected", "#141210")])

        top = ttk.Frame(root)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Button(top, text="Atualizar processos", command=self.refresh).pack(side="left")
        self.mode_var = tk.StringVar(value="post")
        ttk.Label(top, text="Clique:").pack(side="left", padx=(16, 4))
        ttk.Radiobutton(top, text="PostMessage", variable=self.mode_var, value="post").pack(side="left")
        ttk.Radiobutton(top, text="Rato direto", variable=self.mode_var, value="direct").pack(side="left")

        opts = ttk.Frame(root)
        opts.pack(fill="x", padx=8)
        ttk.Label(opts, text="Intervalo (ms):").pack(side="left")
        self.interval_var = tk.StringVar(value="700")
        ttk.Entry(opts, textvariable=self.interval_var, width=7).pack(side="left", padx=(2, 12))
        ttk.Label(opts, text="Sensibilidade:").pack(side="left")
        self.thresh_var = tk.StringVar(value="0.70")
        ttk.Entry(opts, textvariable=self.thresh_var, width=6).pack(side="left", padx=(2, 12))
        self.sound_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Bip no baú", variable=self.sound_var).pack(side="left", padx=(0, 12))
        ttk.Label(opts, text="Max baús (0=inf):").pack(side="left")
        self.cap_var = tk.StringVar(value="0")
        ttk.Entry(opts, textvariable=self.cap_var, width=5).pack(side="left", padx=(2, 12))
        self.auto_syn_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Auto-sintese ao encher", variable=self.auto_syn_var).pack(side="left", padx=(0, 4))
        ttk.Label(opts, text="Crafts:").pack(side="left")
        self.crafts_var = tk.StringVar(value="5")
        ttk.Entry(opts, textvariable=self.crafts_var, width=4).pack(side="left", padx=(2, 12))
        ttk.Label(opts, text="F8 = parar tudo").pack(side="left")

        self.tree = ttk.Treeview(root, columns=("pid", "hwnd", "titulo", "estado", "baus"), show="headings", height=7)
        for cid, txt in (("pid", "PID"), ("hwnd", "HWND"), ("titulo", "Titulo"), ("estado", "Estado"), ("baus", "Baús")):
            self.tree.heading(cid, text=txt)
            self.tree.column(cid, width=110 if cid != "titulo" else 230)
        self.tree.pack(fill="both", expand=True, padx=8, pady=6)

        btns = ttk.Frame(root)
        btns.pack(fill="x", padx=8)
        ttk.Button(btns, text="Iniciar selecionado(s)", command=self.start_selected).pack(side="left")
        ttk.Button(btns, text="Parar selecionado(s)", command=self.stop_selected).pack(side="left", padx=6)
        ttk.Button(btns, text="Teste: 1 clique no centro", command=self.test_click).pack(side="left", padx=6)
        ttk.Button(btns, text="Guardar captura", command=self.save_capture).pack(side="left", padx=6)

        row2 = ttk.Frame(root)
        row2.pack(fill="x", padx=8, pady=(8, 0))
        ttk.Label(row2, text="Aprender:").pack(side="left")
        self.learn_cat = tk.StringVar(value="bau")
        self.learn_sel = ttk.Combobox(row2, textvariable=self.learn_cat, values=list(CATS), width=8, state="readonly")
        self.learn_sel.pack(side="left", padx=(4, 8))
        self.learn_btn = ttk.Button(row2, text="OFF", command=self.toggle_learn)
        self.learn_btn.pack(side="left")
        self.learn_lbl = ttk.Label(row2, text=f"templates: {self.learn_count}")
        self.learn_lbl.pack(side="left", padx=(6, 14))
        ttk.Label(row2, text="Ação:").pack(side="left")
        ttk.Button(row2, text="Clicar BAU", command=lambda: self.click_cat("bau")).pack(side="left", padx=(4, 4))
        ttk.Button(row2, text="Abrir CUBO", command=lambda: self.click_cat("cubo")).pack(side="left", padx=4)
        ttk.Button(row2, text="Abrir MENU", command=lambda: self.click_cat("menu")).pack(side="left", padx=4)
        ttk.Button(row2, text="SINTESE", command=lambda: self.click_cat("sintese")).pack(side="left", padx=4)

        row3 = ttk.Frame(root)
        row3.pack(fill="x", padx=8, pady=(6, 0))
        self.point_btn = ttk.Button(row3, text="Apontar janela (clique nela)", command=self.point_window)
        self.point_btn.pack(side="left")
        self.info_lbl = ttk.Label(row3, text="")
        self.info_lbl.pack(side="left", padx=8)

        ttk.Label(root, text="Aviso: automação pode violar os ToS do jogo — usa por tua conta e risco. Janelas visíveis (não minimizadas).", foreground="#a05a5a").pack(fill="x", padx=8, pady=(4, 6))
        self.refresh()
        self.root.after(200, self.poll)

    def refresh(self):
        for pid in list(self.workers):
            self.stop_one(pid)
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        wins = find_game_windows()
        seen = set()
        for w in wins:
            if w["pid"] in seen:
                continue
            seen.add(w["pid"])
            iid = self.tree.insert("", "end", values=(w["pid"], hex(w["hwnd"]), w["title"], "parado", 0))
            self.rows[iid] = w
        if not wins:
            self.tree.insert("", "end", values=("-", "-", "nenhum TaskBarHero.exe encontrado", "-", "-"))

    def sel_info(self):
        return [(iid, self.rows[iid]) for iid in self.tree.selection() if iid in self.rows]

    def start_selected(self):
        try:
            interval = max(150, int(self.interval_var.get()))
        except ValueError:
            interval = 700
        try:
            threshold = min(0.95, max(0.5, float(self.thresh_var.get())))
        except ValueError:
            threshold = 0.70
        try:
            capacity = max(0, int(self.cap_var.get()))
        except ValueError:
            capacity = 0
        sound = self.sound_var.get()
        mode = self.mode_var.get()
        for iid, w in self.sel_info():
            pid = w["pid"]
            if pid in self.workers and self.workers[pid].is_alive():
                continue
            try:
                syn_crafts = max(1, int(self.crafts_var.get()))
            except ValueError:
                syn_crafts = 5
            wk = Instance(w, mode, interval, threshold, self.queue, capacity=capacity, sound_chest=sound, auto_syn=self.auto_syn_var.get(), syn_crafts=syn_crafts)
            self.workers[pid] = wk
            wk.start()
            self.tree.set(iid, "estado", "a correr")
            self.tree.set(iid, "baus", 0)

    def stop_selected(self):
        for iid, w in self.sel_info():
            self.stop_one(w["pid"])
            self.tree.set(iid, "estado", "parado")

    def stop_one(self, pid):
        wk = self.workers.get(pid)
        if wk:
            wk.stop_flag.set()

    def test_click(self):
        for iid, w in self.sel_info():
            try:
                box = client_box(w["hwnd"])
                post_click(w["hwnd"], box["width"] // 2, box["height"] // 2)
                self.tree.set(iid, "estado", "clique de teste enviado")
            except Exception as e:
                self.tree.set(iid, "estado", "erro: " + str(e)[:40])

    def save_capture(self):
        for iid, w in self.sel_info():
            try:
                box = client_box(w["hwnd"])
                img = grab_region(box["left"], box["top"], box["width"], box["height"])
                path = os.path.join(BASE, f"captura_{w['pid']}.png")
                cv2.imwrite(path, img)
                self.tree.set(iid, "estado", "captura: " + os.path.basename(path))
            except Exception as e:
                self.tree.set(iid, "estado", "erro: " + str(e)[:40])

    def click_cat(self, cat):
        try:
            threshold = min(0.95, max(0.5, float(self.thresh_var.get())))
        except ValueError:
            threshold = 0.70
        mode = self.mode_var.get()
        for iid, w in self.sel_info():
            try:
                box = client_box(w["hwnd"])
                gray = cv2.cvtColor(grab_region(box["left"], box["top"], box["width"], box["height"]), cv2.COLOR_BGR2GRAY)
                hits = nms(find_hits(gray, CATEGORIES[cat], threshold))
                for x, y in hits:
                    if mode == "post":
                        post_click(w["hwnd"], x, y)
                    else:
                        pyautogui.click(box["left"] + x, box["top"] + y)
                    time.sleep(0.15)
                self.tree.set(iid, "estado", f"{cat}: {len(hits)} cliques")
            except Exception as e:
                self.tree.set(iid, "estado", "erro: " + str(e)[:40])

    def toggle_learn(self):
        self.learn_on = not self.learn_on
        cat = self.learn_cat.get()
        if self.learn_on:
            self.learn_btn.config(text=f"ON — clica nos {cat.upper()} do jogo!")
            threading.Thread(target=self.learn_loop, daemon=True).start()
        else:
            self.learn_btn.config(text="OFF")

    def learn_loop(self):
        prev = False
        while self.learn_on:
            down = bool(win32api.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
            if down and not prev and time.time() - getattr(self, "_last_learn", 0) > 0.5:
                self._last_learn = time.time()
                time.sleep(0.06)
                x, y = win32api.GetCursorPos()
                img = grab_region(x - 34, y - 34, 68, 68)
                if img is not None:
                    self.learn_count += 1
                    cat = self.learn_cat.get()
                    path = os.path.join(TPL_DIR, f"tela_{cat}_learn_{self.learn_count:03d}.png")
                    cv2.imwrite(path, img)
                    globals()["CATEGORIES"] = load_templates()
                    self.learn_lbl.config(text=f"templates: {self.learn_count} (ultimo: {cat})")
            prev = down
            time.sleep(0.02)

    def point_window(self):
        self.info_lbl.config(text="3s... clica NA janela do jogo!")
        threading.Thread(target=self._point_wait, daemon=True).start()

    def _point_wait(self):
        end = time.time() + 3
        prev = False
        while time.time() < end:
            down = bool(win32api.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
            if down and not prev:
                x, y = win32api.GetCursorPos()
                hwnd = win32gui.WindowFromPoint((x, y))
                root_h = win32gui.GetAncestor(hwnd, GA_ROOT)
                for iid, w in self.rows.items():
                    if w["hwnd"] == root_h:
                        def select(iid=iid, w=w):
                            self.tree.selection_set(iid)
                            self.tree.focus(iid)
                        self.root.after(0, select)
                        self.root.after(0, lambda w=w: self.info_lbl.config(text=f"apontada! PID {w['pid']}"))
                        return
                self.root.after(0, lambda: self.info_lbl.config(text="essa nao e uma janela do jogo"))
                return
            prev = down
            time.sleep(0.02)
        self.root.after(0, lambda: self.info_lbl.config(text="tempo esgotado"))

    def poll(self):
        for iid, w in self.rows.items():
            wk = self.workers.get(w["pid"])
            if wk and wk.is_alive() and not wk.stop_flag.is_set():
                cur = self.tree.set(iid, "estado")
                if not (cur.startswith("BAUS") or cur.startswith("erro")):
                    self.tree.set(iid, "estado", "a correr")
        try:
            while True:
                kind, pid, val = self.queue.get_nowait()
                for iid, w in self.rows.items():
                    if w["pid"] == pid:
                        if kind == "chest":
                            self.tree.set(iid, "baus", val)
                            self.tree.set(iid, "estado", "a correr")
                        elif kind == "status":
                            self.tree.set(iid, "estado", val)
                        elif kind == "full":
                            self.stop_one(pid)
                            self.tree.set(iid, "estado", "BAUS CHEIOS - pausado")
                            self.tree.set(iid, "baus", val)
                        elif kind == "syn":
                            self.tree.set(iid, "estado", "SINTESE feita - a retomar")
                        elif kind == "stopall":
                            self.stop_one(pid)
                            self.tree.set(iid, "estado", "parado (F8)")
                        break
        except queue.Empty:
            pass
        self.root.after(200, self.poll)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
