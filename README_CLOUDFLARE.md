# Cloudflare temp-email provider

Registration needs a throwaway inbox that can receive the Blackbox OTP. This
provider talks to a self-hosted [cloudflare_temp_email](https://github.com/dreamhunter2333/cloudflare_temp_email)
Worker, so you own the domains and nothing depends on a public temp-mail site.

## Setup

1. Deploy the Worker and point one or more domains at it via Email Routing.
2. Write the domains to `domains.txt` in the repo root, one per line. The file
   is gitignored; `providers/cf_domains.py` falls back to `example.com` when it
   is missing, and picks a random domain per account.
3. Copy `.env.example` to `.env` and set:

```
CF_API_URL=https://your-worker.workers.dev
CF_DEFAULT_DOMAIN=example.com
PROXY_FILE=proxies.txt
```

4. Optional: put one proxy URL per line in `proxies.txt`
   (`http://user:pass@host:port`). Absent file means no proxy. Also gitignored.

Verify the Worker is reachable before a real run:

```bash
.venv/bin/python list_domains.py
```

## How registration uses it

`providers/cloudflare_tempmail.py` wraps three Worker endpoints:

| Call | Endpoint | Purpose |
| --- | --- | --- |
| `create_address` | `POST /api/new_address` | returns `{jwt, address}` |
| `fetch_messages` | `GET /api/mails` | list inbox, `Authorization: Bearer <jwt>` |
| `read_message` | `GET /api/mails/:id` | full body when the list is truncated |

`wait_for_otp` sleeps briefly so the Worker has time to accept the inbound
mail, then polls until it finds a 6-digit code. The sleep happens *before* the
deadline is computed — otherwise it eats into the polling budget, which is what
made OTP waits fail on slow proxies.

Keys land in `output/keys.txt` and `output/keys_9router.txt` (`email|sk-key`),
both gitignored.

## Troubleshooting

**No OTP received** — check `list_domains.py` first; a Worker returning 4xx
looks identical to a missing mail. Then confirm the domain actually routes mail
(send yourself a test), and try without a proxy to rule out a slow exit node.

**Same domain every time** — `domains.txt` is missing or has one entry, so the
fallback is in use.
