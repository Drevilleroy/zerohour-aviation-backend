from __future__ import annotations

import argparse
import asyncio
import time

import httpx


async def submit(client: httpx.AsyncClient, url: str, index: int) -> int:
    response = await client.post(
        url,
        json={
            "email": f"load-{index}@example.com",
            "password": "correct-horse-battery-staple",
            "name": f"Load User {index}",
            "plan_type": "monthly",
            "passenger_full_name": f"Load User {index}",
            "passenger_date_of_birth": "1990-01-01",
        },
    )
    return response.status_code


async def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate concurrent signup queue traffic.")
    parser.add_argument("--url", default="http://localhost:8000/auth/register")
    parser.add_argument("--requests", type=int, default=10_000)
    parser.add_argument("--concurrency", type=int, default=500)
    args = parser.parse_args()

    started = time.perf_counter()
    counts: dict[int, int] = {}
    async with httpx.AsyncClient(timeout=20) as client:
        for offset in range(0, args.requests, args.concurrency):
            batch = range(offset, min(offset + args.concurrency, args.requests))
            statuses = await asyncio.gather(*(submit(client, args.url, idx) for idx in batch))
            for status in statuses:
                counts[status] = counts.get(status, 0) + 1
    elapsed = time.perf_counter() - started
    print({"requests": args.requests, "elapsed_seconds": round(elapsed, 2), "status_counts": counts})


if __name__ == "__main__":
    asyncio.run(main())
