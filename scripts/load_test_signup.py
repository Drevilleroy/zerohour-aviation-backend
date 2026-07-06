from __future__ import annotations

import argparse
import asyncio
import time
from urllib.parse import urlparse

import httpx


async def submit(client: httpx.AsyncClient, url: str, index: int, email_domain: str) -> int:
    response = await client.post(
        url,
        json={
            "email": f"load-{index}-{int(time.time())}@{email_domain}",
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
    parser.add_argument("--email-domain", default="example.com")
    parser.add_argument(
        "--allow-non-local",
        action="store_true",
        help="Required when the target URL is not localhost/127.0.0.1.",
    )
    args = parser.parse_args()
    _validate_target(args.url, allow_non_local=args.allow_non_local)

    started = time.perf_counter()
    counts: dict[int, int] = {}
    async with httpx.AsyncClient(timeout=20) as client:
        for offset in range(0, args.requests, args.concurrency):
            batch = range(offset, min(offset + args.concurrency, args.requests))
            statuses = await asyncio.gather(
                *(submit(client, args.url, idx, args.email_domain) for idx in batch)
            )
            for status in statuses:
                counts[status] = counts.get(status, 0) + 1
    elapsed = time.perf_counter() - started
    print({"requests": args.requests, "elapsed_seconds": round(elapsed, 2), "status_counts": counts})


def _validate_target(url: str, *, allow_non_local: bool) -> None:
    hostname = urlparse(url).hostname
    if allow_non_local or hostname in {"localhost", "127.0.0.1", "::1"}:
        return
    raise SystemExit(
        "Refusing to run signup load test against a non-local target. "
        "Pass --allow-non-local only after confirming this will create test accounts."
    )


if __name__ == "__main__":
    asyncio.run(main())
