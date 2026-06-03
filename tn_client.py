"""
TN Client — HTTP long-poll version
Run: python C:\tn_client.py
"""
import requests
import json
import subprocess
import time
import os

RELAY   = os.environ.get('RELAY_URL', 'https://web-production-76c25d.up.railway.app')
SECRET  = os.environ.get('BRIDGE_SECRET', 'BGSM2024')
HEADERS = {'X-Secret': SECRET}

def execute(cmd, timeout=30):
    try:
        proc = subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            return {'stdout': '', 'stderr': 'timeout', 'returncode': -1}
        def dec(b):
            for enc in ('utf-8', 'cp1252', 'latin-1'):
                try: return b.decode(enc)
                except: pass
            return b.decode('utf-8', errors='replace')
        return {'stdout': dec(out), 'stderr': dec(err), 'returncode': proc.returncode}
    except Exception as e:
        return {'stdout': '', 'stderr': str(e), 'returncode': -1}

def main():
    print('TN Bridge Client starting...')
    print(f'Relay: {RELAY}')
    errors = 0
    poll_num = 0

    while True:
        try:
            poll_num += 1
            print(f'Polling #{poll_num}...', flush=True)
            r = requests.get(
                f'{RELAY}/tn/poll',
                headers=HEADERS,
                params={'secret': SECRET},
                timeout=30
            )
            errors = 0
            print(f'  HTTP {r.status_code}', flush=True)

            if r.status_code != 200:
                time.sleep(2)
                continue

            item = r.json().get('cmd')
            if item is None:
                continue  # nothing pending, poll again immediately

            cmd_id = item.get('id')
            cmd    = item.get('cmd', '')
            print(f'  Executing: {cmd}', flush=True)

            result = execute(cmd)
            print(f'  rc={result["returncode"]} out={repr(result["stdout"][:60])}', flush=True)

            requests.post(
                f'{RELAY}/tn/result',
                headers={**HEADERS, 'Content-Type': 'application/json'},
                params={'secret': SECRET},
                json={'id': cmd_id, 'result': result},
                timeout=10
            )
            print(f'  Result posted.', flush=True)

        except Exception as e:
            errors += 1
            print(f'Error ({errors}): {e}', flush=True)
            time.sleep(min(errors * 2, 15))

if __name__ == '__main__':
    main()
