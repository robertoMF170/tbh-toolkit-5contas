# Analisa janelas do TaskBarHero: % pixels pretos e estilos de janela (layered/transparent)
import sys, json
import numpy as np
import mss
import win32gui, win32api, win32con, win32process, win32process as wp

GAME = "taskbarhero.exe"
GA_ROOT = 2
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000

def exe_of(pid):
    try:
        h = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
        try:
            import os
            return os.path.basename(wp.GetModuleFileNameEx(h, 0)).lower(), wp.GetModuleFileNameEx(h, 0)
        finally:
            win32api.CloseHandle(h)
    except Exception as e:
        return "", str(e)

def find_windows():
    out = []
    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            _, pid = wp.GetWindowThreadProcessId(hwnd)
        except Exception:
            return
        name, path = exe_of(pid)
        if name != GAME:
            return
        out.append((hwnd, pid, path))
    win32gui.EnumWindows(cb, None)
    return out

def analyze(hwnd):
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    cl, ct, cr, cb_ = win32gui.GetClientRect(hwnd)
    pt = win32gui.ClientToScreen(hwnd, (cl, ct))
    box = {"left": pt[0], "top": pt[1], "width": cr - cl, "height": cb_ - ct}
    exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    res = {
        "hwnd": hex(hwnd),
        "window_rect": [l, t, r, b],
        "client_box": [box["left"], box["top"], box["width"], box["height"]],
        "title": win32gui.GetWindowText(hwnd),
        "class": win32gui.GetClassName(hwnd),
        "exstyle_hex": hex(exstyle),
        "WS_EX_LAYERED": bool(exstyle & WS_EX_LAYERED),
        "WS_EX_TRANSPARENT": bool(exstyle & WS_EX_TRANSPARENT),
        "WS_EX_NOACTIVATE": bool(exstyle & WS_EX_NOACTIVATE),
    }
    try:
        with mss.mss() as sct:
            img = np.array(sct.grab(box))[:,:,:3].astype(np.int32)
        total = img.shape[0] * img.shape[1]
        near_black = int(((img < 12).all(axis=2)).sum())
        res["pct_near_black"] = round(100.0 * near_black / total, 2)
        # banda de 6px nas bordas (a "moldura" a volta do jogo)
        band = 6
        h, w = img.shape[:2]
        border = np.concatenate([
            img[:band].reshape(-1,3), img[-band:].reshape(-1,3),
            img[:, :band].reshape(-1,3), img[:, -band:].reshape(-1,3)])
        bn = int(((border < 12).all(axis=1)).sum())
        res["pct_black_border"] = round(100.0 * bn / border.shape[0], 2)
        # cor media da moldura
        res["border_mean_rgb"] = [int(x) for x in border.mean(axis=0)]
    except Exception as e:
        res["capture_error"] = str(e)
    return res

if __name__ == "__main__":
    target_pid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    wins = find_windows()
    out = {"found": [], "ts": __import__("time").strftime("%H:%M:%S")}
    for hwnd, pid, path in wins:
        if target_pid and pid != target_pid:
            continue
        r = analyze(hwnd)
        r["pid"] = pid
        r["path"] = path
        out["found"].append(r)
    with open("analysis_result.json", "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))
