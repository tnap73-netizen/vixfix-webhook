"""
TN Client — HTTP long-poll version
No WebSocket required. Polls Railway for commands, posts results back.
Run: python C:\tn_client.py
"""
import requests
import json
import subprocess
import time
import os
import sys

RELAY   = os.environ.get('RELAY_URL', 'https://web-production-76c25d.up.railway.app')
SECRET  = os.environ.get('BRIDGE_SECRET', 'BGSM2024')
HEADERS = {'X-Secret': SECRET, 'Content-Type': 'application/json'}

def execute(cmd, timeout=30):
    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout_bytes, stderr_bytes = proc.communicate()
            return {'stdout': '', 'stderr': 'timeout', 'returncode': -1}
        
        # Decode with fallback encodings
        def decode(b):
            for enc in ('utf-8', 'cp1252', 'latin-1'):
                try:
                    return b.decode(enc)
                except Exception:
                    continue
            return b.decode('utf-8', errors='replace')
        
        return {
            'stdout': decode(stdout_bytes),
            'stderr': decode(stderr_bytes),
            'returncode': proc.returncode
        }
    except Exception as e:
        return {'stdout': '', 'stderr': str(e), 'returncode': -1}

def main():
    print(f'TN Bridge Client starting (HTTP long-poll)')
    print(f'Relay: {RELAY}')
    errors = 0

    while True:
        try:
            r = requests.get(
                f'{RELAY}/tn/poll',
                headers=HEADERS,
                params={'secret': SECRET},
                timeout=35
            )
            errors = 0

            if r.status_code != 200:
                print(f'Poll error {r.status_code}')
                time.sleep(2)
                continue

            data = r.json()
            item = data.get('cmd')
            if item is None:
                continue

            cmd_id = item.get('id')
            cmd    = item.get('cmd', '')
            print(f'Executing: {cmd}')

            result = execute(cmd)
            print(f'  rc={result["returncode"]} stdout={repr(result["stdout"][:80])}')

            requests.post(
                f'{RELAY}/tn/result',
                headers=HEADERS,
                params={'secret': SECRET},
                json={'id': cmd_id, 'result': result},
                timeout=10
            )

        except Exception as e:
            errors += 1
            print(f'Error ({errors}): {e}')
            time.sleep(min(errors * 2, 15))

if __name__ == '__main__':
    main()
