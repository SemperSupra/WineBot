import asyncio

import httpx


async def check_api():
    print("--- Diagnostic: API ---")
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        try:
            print("Checking /health...")
            r = await client.get("/health")
            print(f"/health: {r.status_code} {r.text[:100]}")
        except Exception as e:
            print(f"/health FAIL: {e}")

        try:
            print("Checking /ui/...")
            r = await client.get("/ui/")
            print(f"/ui/: {r.status_code} {r.headers.get('content-type', 'unknown')}")
        except Exception as e:
            print(f"/ui/ FAIL: {e}")


if __name__ == "__main__":
    asyncio.run(check_api())
