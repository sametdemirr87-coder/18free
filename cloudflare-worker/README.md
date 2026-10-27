# Nexus active/passive gateway

The public Worker URL is the only URL used by panels and generated userscripts.
It forwards to Render while the router state is `primary`. If Render is
unreachable or returns 429/500/502/503/504, the state is persisted as
`secondary` in the existing Supabase `app_state` table and the Worker serves
the same API from Supabase directly.

Required encrypted Worker secrets:

- `ADMIN_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`

Non-secret configuration lives in `wrangler.jsonc`. Never commit secret values.

Router admin endpoints use the normal `X-Admin-Token` header:

- `GET /__router/status`
- `POST /__router/switch` with `{ "mode": "primary" }` or
  `{ "mode": "secondary" }`

Automatic failover is one-way. A failed primary cannot automatically become
active again, preventing two backends from flapping or being used at once.
