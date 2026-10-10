import asyncio, json, sys
import urllib.request
try:
    import websockets
except ImportError:
    print("installing websockets...", flush=True)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "websockets", "requests"])
    import websockets
import requests
import time

async def listen(stop_after=14):
    seen = {"log": 0, "stage": 0, "job_update": 0, "status": 0, "stages": []}
    async with websockets.connect("ws://127.0.0.1:8000/ws/system") as ws:
        # Create a job
        r = requests.post("http://127.0.0.1:8000/api/downloads/batch", json={
            "platform": "instagram",
            "source_type": "link",
            "items": [{"url": "https://instagram.com/instagram/", "author": "instagram", "content_type": "post"}]
        }, timeout=10)
        ids = r.json().get("ids", [])
        print(f"[client] created download ids={ids}", flush=True)
        try:
            requests.post("http://127.0.0.1:8000/api/downloads/run-pending?platform=instagram", timeout=5)
            print(f"[client] run-pending triggered", flush=True)
        except Exception as e:
            print(f"[client] run-pending error: {e}", flush=True)
        deadline = time.time() + stop_after
        while time.time() < deadline:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                ev = json.loads(msg)
                t = ev.get("type")
                seen[t] = seen.get(t, 0) + 1
                if t == "stage":
                    stage = ev["data"].get("stage")
                    seen["stages"].append(stage)
                    print(f"  STAGE  {stage:14} | {ev['data'].get('message')}", flush=True)
                elif t == "log":
                    print(f"  LOG    {ev['data'].get('level','?'):7} | {ev['data'].get('message','')[:90]}", flush=True)
                elif t in ("job_update", "status"):
                    print(f"  {t.upper():10} {ev['data']}", flush=True)
            except asyncio.TimeoutError:
                break
    print("\n=== summary ===", flush=True)
    for k, v in seen.items():
        if k == "stages":
            print(f"  stages seen: {v}")
        else:
            print(f"  {k}: {v}")

asyncio.run(listen(15))
