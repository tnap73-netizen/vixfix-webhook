import win32gui, win32con, time, os, base64
from PIL import ImageGrab

out_dir = os.path.join(os.path.expanduser("~"), "bbg_output")
os.makedirs(out_dir, exist_ok=True)

target = None
def cb(hwnd, extra):
    global target
    if win32gui.IsWindowVisible(hwnd):
        t = win32gui.GetWindowText(hwnd)
        if any(x in t for x in ["Canvas", "MSG", "Bloomberg", "Equity", "bplus"]):
            target = (hwnd, t)
win32gui.EnumWindows(cb, None)

if target:
    hwnd, title = target
    print("Found: " + title)
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(2)
else:
    print("No Bloomberg window found, screenshotting desktop")

path = os.path.join(out_dir, "canvas_screenshot.png")
img = ImageGrab.grab()
img.save(path, "PNG")
print("Saved: " + path)
print("Size: " + str(os.path.getsize(path) // 1024) + "KB")
print("DONE")
