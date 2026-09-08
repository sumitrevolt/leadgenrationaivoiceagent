#!/usr/bin/env python3
"""buzz_relay_proxy.py — High-Performance Local TCP Bridge for Buzz Relay.
Forwards loopback 127.0.0.1:3100 directly to live VPS Relay 72.61.245.204:3110.
Supports all HTTP, WebSocket, and ACP telemetry streams transparently.
"""

import asyncio
import sys

LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 3100
REMOTE_HOST = "72.61.245.204"
REMOTE_PORT = 3110

async def pipe(reader, writer):
    try:
        while not reader.at_eof():
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def handle_client(client_reader, client_writer):
    try:
        remote_reader, remote_writer = await asyncio.open_connection(REMOTE_HOST, REMOTE_PORT)
    except Exception as e:
        sys.stderr.write(f"[bridge] failed to connect to remote: {e}\n")
        client_writer.close()
        return

    asyncio.create_task(pipe(client_reader, remote_writer))
    asyncio.create_task(pipe(remote_reader, client_writer))

async def main():
    server = await asyncio.start_server(handle_client, LOCAL_HOST, LOCAL_PORT)
    print(f"[*] Buzz Relay Bridge live on {LOCAL_HOST}:{LOCAL_PORT} -> {REMOTE_HOST}:{REMOTE_PORT}", flush=True)
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
