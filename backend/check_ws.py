import asyncio, json, websockets

async def main():
    uri = "ws://localhost:8000/ws/system"
    async with websockets.connect(uri) as ws:
        print("[ws] connected OK")
        # Test ping-pong
        await ws.send("ping")
        try:
            reply = await asyncio.wait_for(ws.recv(), timeout=2)
            print(f"[ws] first reply: {reply[:80]!r}")
        except asyncio.TimeoutError:
            print("[ws] no reply within 2s (server may not send until event)")
            # Wait for any inbound
            try:
                reply = await asyncio.wait_for(ws.recv(), timeout=5)
                print(f"[ws] event arrived: {reply[:200]!r}")
            except asyncio.TimeoutError:
                print("[ws] still no inbound (truly silent)")

asyncio.run(main())
