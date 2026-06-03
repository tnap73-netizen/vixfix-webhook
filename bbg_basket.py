"""
Bloomberg Basket Caller
Usage: python bbg_basket.py WMT 1
Baskets: 1=GP/ANR/ATPR  2=GF/OWN/ALTD/NLRT  3=OMON/TONE/ERN
"""
import subprocess, time, sys, os, json, base64

TICKER  = sys.argv[1] if len(sys.argv) > 1 else "WMT"
BASKET  = int(sys.argv[2]) if len(sys.argv) > 2 else 1
OUT_DIR = r"C:\Users\TNap7\bbg_output"
os.makedirs(OUT_DIR, exist_ok=True)

BASKETS = {
    1: ["GP", "ANR", "ATPR"],
    2: ["GF", "OWN", "ALTD", "NLRT"],
    3: ["OMON", "TONE", "ERN"],
}

funcs = BASKETS.get(BASKET, BASKETS[1])

try:
    import pyautogui
    import win32gui, win32con
    from PIL import ImageGrab
except ImportError as e:
    print(json.dumps({"error": f"Missing package: {e}"}))
    sys.exit(1)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.1


def find_bloomberg():
    """Find bplus64 (Bloomberg Anywhere) window."""
    hwnds = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            pid_arr = []
            import win32process
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            t = win32gui.GetWindowText(hwnd)
            if t:
                hwnds.append((hwnd, t, pid))
    win32gui.EnumWindows(cb, None)
    return hwnds


def get_bloomberg_hwnd():
    """Get the main Bloomberg window handle."""
    import win32process
    # Find all bplus64 PIDs
    result = subprocess.run(
        'tasklist /FI "IMAGENAME eq bplus64.exe" /FO CSV',
        shell=True, capture_output=True, text=True
    )
    pids = []
    for line in result.stdout.strip().split('\n')[1:]:
        parts = line.strip('"').split('","')
        if len(parts) > 1:
            try:
                pids.append(int(parts[1]))
            except:
                pass

    if not pids:
        return None, None

    # Find window belonging to bplus64
    best = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid in pids:
                t = win32gui.GetWindowText(hwnd)
                if t:
                    best.append((hwnd, t))
    win32gui.EnumWindows(cb, None)

    if not best:
        return None, None
    # Prefer windows that look like Bloomberg panels (not "New Tab")
    for hwnd, t in best:
        if "New Tab" not in t and "IB Manager" not in t:
            return hwnd, t
    return best[0]


def bring_to_front(hwnd):
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(1)


def type_bbg_command(cmd_str):
    """Type Bloomberg command into the command bar and press F8."""
    # Click the center-top area where Bloomberg command bar is
    pyautogui.click(768, 50)
    time.sleep(0.3)
    # Select all and clear
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.typewrite(cmd_str, interval=0.07)
    time.sleep(0.3)
    pyautogui.press("f8")
    time.sleep(5)  # wait for Bloomberg to load the function


def screenshot_and_encode(path):
    img = ImageGrab.grab()
    img.save(path, "PNG")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# --- MAIN ---
hwnd, title = get_bloomberg_hwnd()

if not hwnd:
    print(json.dumps({"error": "Bloomberg (bplus64) not found. Is Bloomberg Anywhere open?"}))
    sys.exit(1)

print(f"Found Bloomberg: {title} (hwnd={hwnd})", flush=True)
bring_to_front(hwnd)
time.sleep(1.5)

results = {}
for func in funcs:
    cmd_str = f"{TICKER} US Equity {func}"
    print(f"  Typing: {cmd_str}", flush=True)
    type_bbg_command(cmd_str)
    path = os.path.join(OUT_DIR, f"{TICKER}_{func}.png")
    b64 = screenshot_and_encode(path)
    results[func] = {"path": path, "size_kb": len(b64) // 1024}
    print(f"  Saved: {path} ({results[func]['size_kb']}KB)", flush=True)
    time.sleep(1)

manifest_path = os.path.join(OUT_DIR, f"{TICKER}_B{BASKET}_manifest.json")
with open(manifest_path, "w") as f:
    json.dump({"ticker": TICKER, "basket": BASKET, "functions": funcs, "files": results}, f)

print(f"COMPLETE: {TICKER} Basket {BASKET}")
print(json.dumps({"status": "ok", "ticker": TICKER, "basket": BASKET,
                  "functions": funcs, "output_dir": OUT_DIR}))
