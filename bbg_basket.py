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


def find_bloomberg():
    hwnds = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if "Bloomberg" in t:
                hwnds.append((hwnd, t))
    win32gui.EnumWindows(cb, None)
    return hwnds


def bring_to_front(hwnd):
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.8)


def type_bbg_command(cmd_str):
    """Click the Bloomberg command line, type command, press F8."""
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.typewrite(cmd_str, interval=0.06)
    time.sleep(0.3)
    pyautogui.press("f8")
    time.sleep(4)


def screenshot_and_encode(path):
    img = ImageGrab.grab()
    img.save(path, "PNG")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


results = {}

windows = find_bloomberg()
if not windows:
    # Try to launch Bloomberg
    print("Bloomberg not found, attempting launch...", flush=True)
    subprocess.Popen([r"C:\blp\terminal\bloomberg.exe"])
    time.sleep(8)
    windows = find_bloomberg()

if not windows:
    print(json.dumps({"error": "Bloomberg window not found. Open Bloomberg first."}))
    sys.exit(1)

hwnd, title = windows[0]
print(f"Found Bloomberg: {title}", flush=True)
bring_to_front(hwnd)
time.sleep(1)

for func in funcs:
    cmd_str = f"{TICKER} US Equity {func}"
    print(f"  Running: {cmd_str}", flush=True)
    type_bbg_command(cmd_str)
    time.sleep(3)
    path = os.path.join(OUT_DIR, f"{TICKER}_{func}.png")
    b64 = screenshot_and_encode(path)
    results[func] = path
    print(f"  Saved: {path} ({len(b64)//1024}KB)", flush=True)

manifest_path = os.path.join(OUT_DIR, f"{TICKER}_B{BASKET}_manifest.json")
with open(manifest_path, "w") as f:
    json.dump({"ticker": TICKER, "basket": BASKET, "functions": funcs, "files": results}, f)

print(f"COMPLETE: {TICKER} Basket {BASKET}")
print(json.dumps({"status": "ok", "ticker": TICKER, "basket": BASKET, "functions": funcs, "output_dir": OUT_DIR}))
