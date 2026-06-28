import asyncio
import json
import os

import httpx


async def check_lifecycle():
    print("--- Diagnostic: Lifecycle Status ---")
    headers = {}
    token = os.getenv("API_TOKEN")
    if token:
        headers["X-API-Key"] = token

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        try:
            r = await client.get("/lifecycle/status", headers=headers)
            print(f"Status: {r.status_code}")
            if r.status_code == 200:
                print(json.dumps(r.json(), indent=2))
            else:
                print(f"Error: {r.text}")
        except Exception as e:
            print(f"Request failed: {e}")


if __name__ == "__main__":
    asyncio.run(check_lifecycle())
