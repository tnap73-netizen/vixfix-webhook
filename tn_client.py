"""
TN Client — runs on TN Windows machine
Connects OUTBOUND to Railway relay via WebSocket
Auto-reconnects on disconnect
"""
import asyncio
import json
import subprocess
import os
import ssl

RELAY_URL = os.environ.get('RELAY_URL', 'wss://web-production-76c25d.up.railway.app/tn/ws')
SECRET = os.environ.get('BRIDGE_SECRET', 'BGSM2024')
RECONNECT_DELAY = 5

async def execute_command(cmd, timeout=30):
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
    except subprocess.TimeoutExpired:
        return {'stdout': '', 'stderr': 'Command timed out', 'returncode': -1}
    except Exception as e:
        return {'stdout': '', 'stderr': str(e), 'returncode': -1}

async def connect_and_run():
    import websockets

    # websockets 16.x uses connect() as async context manager
    ssl_ctx = ssl.create_default_context()
    
    async with websockets.connect(
        RELAY_URL,
        ssl=ssl_ctx,
        ping_interval=20,
        ping_timeout=10,
        additional_headers={'User-Agent': 'tn-client/1.0'},
        max_size=10 * 1024 * 1024
    ) as ws:
        # Authenticate
        await ws.send(json.dumps({'secret': SECRET}))
        print('Connected and authenticated. Waiting for commands...')

        async for message in ws:
            try:
                msg = json.loads(message)
                cmd_id = msg.get('id')
                cmd = msg.get('cmd', '')
                print(f'Executing: {cmd}')
                result = await execute_command(cmd)
                await ws.send(json.dumps({'id': cmd_id, 'result': result}))
                print(f'Done: {cmd_id[:8] if cmd_id else "?"}')
            except Exception as e:
                print(f'Error: {e}')
                if cmd_id:
                    await ws.send(json.dumps({
                        'id': cmd_id,
                        'result': {'stdout': '', 'stderr': str(e), 'returncode': -1}
                    }))

async def main():
    while True:
        try:
            await connect_and_run()
        except Exception as e:
            print(f'Connection error: {e}')
        print(f'Reconnecting in {RECONNECT_DELAY}s...')
        await asyncio.sleep(RECONNECT_DELAY)

if __name__ == '__main__':
    print('TN Bridge Client starting...')
    print(f'Relay: {RELAY_URL}')
    asyncio.run(main())
