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

RELAY    = os.environ.get('RELAY_URL', 'https://web-production-76c25d.up.railway.app')
SECRET   = os.environ.get('BRIDGE_SECRET', 'BGSM2024')
HEADERS  = {'X-Secret': SECRET, 'Content-Type': 'application/json'}

def execute(cmd, timeout=30):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {'stdout': result.stdout, 'stderr': result.stderr, 'returncode': result.returncode}
    except subprocess.TimeoutExpired:
        return {'stdout': '', 'stderr': 'timeout', 'returncode': -1}
    except Exception as e:
        return {'stdout': '', 'stderr': str(e), 'returncode': -1}

def main():
    print(f'TN Bridge Client starting (HTTP long-poll)')
    print(f'Relay: {RELAY}')
    consecutive_errors = 0
    
    while True:
        try:
            # Long-poll for a command (server holds for up to 25s)
            r = requests.get(f'{RELAY}/tn/poll', headers=HEADERS, params={'secret': SECRET}, timeout=35)
            consecutive_errors = 0
            
            if r.status_code != 200:
                print(f'Poll error: {r.status_code}')
                time.sleep(2)
                continue
            
            data = r.json()
            item = data.get('cmd')
            
            if item is None:
                # Nothing pending — immediately poll again
                continue
            
            cmd_id = item.get('id')
            cmd    = item.get('cmd', '')
            print(f'Executing: {cmd}')
            
            result = execute(cmd)
            
            # Post result back
            requests.post(
                f'{RELAY}/tn/result',
                headers=HEADERS,
                params={'secret': SECRET},
                json={'id': cmd_id, 'result': result},
                timeout=10
            )
            print(f'Done: {cmd[:40]}')
            
        except Exception as e:
            consecutive_errors += 1
            print(f'Error ({consecutive_errors}): {e}')
            time.sleep(min(consecutive_errors * 2, 30))

if __name__ == '__main__':
    main()
