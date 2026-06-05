# Load Testing Plan

## 1,000 Simultaneous Signups

- Tool: Locust or k6.
- Flow: `POST /api/v1/auth/signup` with unique email and 1-5 ZIPs.
- Assertions:
  - API p95 below 750 ms for accepted signup.
  - No external scraping or scoring in request logs.
  - 100% durable `provisioning_jobs` creation.
  - Provisioning queue drains within target SLA under configured worker count.

## 100,000 Daily Digests

- Seed active users and ZIP subscriptions.
- Enqueue digest generation batches.
- Measure queue age, provider send retries, personalization time, and email provider throttling.

## Failure Injection

- Pause Redis: dashboard should fall back to Postgres materialized cache or degraded shell.
- Force provider 429/500: ingestion run marks provider health degraded and preserves existing ZIP cache.
- Stripe webhook spike: replay duplicate events and verify idempotency/audit records.
- Direct mail provider failure: no credit double-spend, campaign remains retryable.

