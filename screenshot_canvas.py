"""
Screenshot the active Bloomberg window and save to bbg_output.
Run: python C:\Users\TNap7\screenshot_canvas.py
"""
import win32gui, win32con, time, os, base64
from PIL import ImageGrab

out_dir = r'C:\Users\TNap7\bbg_output'
os.makedirs(out_dir, exist_ok=True)

# Find Bloomberg Canvas / MSG window
target = None
def cb(hwnd, _):
    global target
    if win32gui.IsWindowVisible(hwnd):
        t = win32gui.GetWindowText(hwnd)
        if any(x in t for x in ['Canvas', 'MSG', 'Bloomberg', 'Equity']):
            target = (hwnd, t)
win32gui.EnumWindows(cb, None)

if target:
    hwnd, title = target
    print(f'Found window: {title}', flush=True)
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except:
        pass
    time.sleep(2)
else:
    print('No Bloomberg window found — screenshotting full desktop', flush=True)

path = os.path.join(out_dir, 'canvas_screenshot.png')
img = ImageGrab.grab()
img.save(path, 'PNG')
print(f'Saved: {path}', flush=True)
print(f'Size: {os.path.getsize(path) // 1024}KB', flush=True)
print('DONE', flush=True)
