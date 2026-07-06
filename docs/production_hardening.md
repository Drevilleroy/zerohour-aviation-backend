# ZeroHour Production Hardening

## Cloudflare Required Rules

Apply these rules before scaling paid traffic.

### DNS and Proxy

- `flyzerohour.com`: proxied through Cloudflare.
- `www.flyzerohour.com`: proxied through Cloudflare.
- Backend API hostname, if exposed separately: proxied through Cloudflare.
- SSL/TLS mode: Full strict.
- Always Use HTTPS: enabled.

### Rate Limits

Create Cloudflare WAF/rate limiting rules:

- Signup endpoints: `POST /auth/register` and `POST /api/v1/auth/register`
  - Limit: 20 requests per minute per IP.
  - Action: Managed challenge, then block if repeated.
- Login endpoints: `POST /auth/login` and `POST /api/v1/auth/login`
  - Limit: 20 requests per hour per IP.
  - Action: Managed challenge.
- Authenticated API endpoints:
  - Limit: 100 requests per minute per IP.
  - Exclude: `/health`, `/health/live`, `/health/ready`, webhook endpoints.
- Flight search endpoint: `POST /flights/search`
  - Limit: 60 requests per minute per IP.
  - Action: Managed challenge.
- Webhook endpoints: `/webhooks/*`
  - Do not browser-challenge.
  - Restrict by provider signature validation in the application.

### DDoS and Bot Protection

- Enable Cloudflare DDoS protection.
- Enable Bot Fight Mode or equivalent bot protection.
- Keep Under Attack Mode off by default; enable temporarily during an active attack.

### Caching

- Cache static assets at the edge:
  - `*.js`, `*.css`, images, fonts, and static PWA assets.
- Do not cache API responses by default.
- Explicitly bypass cache for:
  - `/auth/*`
  - `/api/*`
  - `/flights/*`
  - `/bookings/*`
  - `/signals/*`
  - `/webhooks/*`
  - `/health*`

### Verification

- `https://flyzerohour.com/health` should only be expected to work if the root domain points to the backend.
- If `flyzerohour.com` points to the PWA, verify backend health on the Railway API domain:
  - `https://zerohour-aviation-backend-production.up.railway.app/health`
- Expected health response:

```json
{"status":"ok"}
```
