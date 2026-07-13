# Fix: Rate Limiting

Rate limiting is not about scale, it is about abuse and cost. The two endpoints that must have it in v1:
- Anything that calls a **paid API** (OpenAI, Anthropic, Stripe, SMS, email). One script overnight is a real bill.
- **Auth endpoints** (login, register, password reset). Without a limit they invite credential stuffing and spam.

## Default: Upstash Ratelimit

Works on serverless (Vercel, Netlify, Cloudflare) and long-lived servers. Free tier is enough to start. Needs a free Upstash Redis database; put the two credentials in server-side env (never a public prefix).

```bash
npm install @upstash/ratelimit @upstash/redis
```

```ts
// lib/ratelimit.ts
import { Ratelimit } from "@upstash/ratelimit"
import { Redis } from "@upstash/redis"

export const ratelimit = new Ratelimit({
  redis: Redis.fromEnv(),                          // UPSTASH_REDIS_REST_URL + _TOKEN
  limiter: Ratelimit.slidingWindow(10, "60 s"),    // 10 requests per minute
  analytics: true,
})
```

Use it at the top of the endpoint, keyed by user id if you have one, otherwise IP:

```ts
// app/api/generate/route.ts (Next.js example)
import { ratelimit } from "@/lib/ratelimit"

export async function POST(req: Request) {
  const user = await getCurrentUser(req)
  const key = user?.id ?? req.headers.get("x-forwarded-for") ?? "anonymous"

  const { success, limit, remaining, reset } = await ratelimit.limit(key)
  if (!success) {
    return new Response("Too many requests", {
      status: 429,
      headers: {
        "Retry-After": String(Math.ceil((reset - Date.now()) / 1000)),
        "X-RateLimit-Remaining": String(remaining),
      },
    })
  }

  // ... the expensive AI/paid call
}
```

Tune the window per endpoint: an AI generation route might allow 5 per minute; a login route 5 per 10 minutes per IP.

## Platform-native alternatives

- **Cloudflare:** Rate Limiting Rules in the dashboard, or the Workers rate limiting binding. No extra service.
- **Vercel:** the Firewall / rate limiting on Pro, or Upstash as above on any plan.
- **Express/Node server:** `express-rate-limit` with a Redis store (in-memory only works for a single instance).

```ts
import rateLimit from "express-rate-limit"
app.use("/api/auth", rateLimit({ windowMs: 10 * 60 * 1000, max: 5 }))
```

- **SvelteKit:** call the Upstash limiter above from the `handle` hook (to cover routes centrally) or at the top of a `+server.ts` handler, keyed by `event.locals.user?.id ?? event.getClientAddress()`. Return a 429 with `throw error(429, "Too many requests")`.
- **TanStack Start:** call the limiter at the top of the `createServerFn` handler for the expensive route, keyed by the session user id, and throw when the limit is hit.

## Verify

- Confirm the limiter runs before the expensive work, not after.
- Hit the endpoint in a loop past the limit and confirm you get a 429 with a `Retry-After` header.
- Confirm the Upstash credentials are server-side only: grep for them behind `VITE_`/`NEXT_PUBLIC_` (they must not be).
