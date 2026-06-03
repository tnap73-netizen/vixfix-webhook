"""
Fetch a file from bbg_output back to the relay as base64.
Usage: python C:\Users\TNap7\fetch_output.py canvas_screenshot.png
"""
import sys, os, base64, json

filename = sys.argv[1] if len(sys.argv) > 1 else 'canvas_screenshot.png'
path = os.path.join(r'C:\Users\TNap7\bbg_output', filename)

if not os.path.exists(path):
    print(json.dumps({'error': f'File not found: {path}'}))
    sys.exit(1)

with open(path, 'rb') as f:
    data = base64.b64encode(f.read()).decode()

size_kb = len(data) * 3 // 4 // 1024
print(json.dumps({'file': filename, 'size_kb': size_kb, 'b64': data}))
