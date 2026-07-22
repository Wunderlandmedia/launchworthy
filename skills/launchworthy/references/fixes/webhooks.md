# Fix: Webhooks

A webhook is a provider telling you money moved or state changed. Two failure modes cost real revenue:

- **Forged events.** No signature check means anyone who finds the URL can POST a fake `payment_intent.succeeded` and get whatever your handler grants.
- **Swallowed failures.** A catch block that returns 200 anyway tells the provider the event was delivered. It never retries, error tracking sees nothing because nothing threw, and the revenue path dies with every dashboard green.

The rule that fixes both: verify before you trust, and return 2xx only after the work succeeded.

## Signature verification (Stripe, Next.js example)

The raw request body is required; a parsed-then-reserialized body fails verification.

```ts
// app/api/webhooks/stripe/route.ts
import Stripe from "stripe"

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!)

export async function POST(req: Request) {
  const body = await req.text()                       // raw body, not req.json()
  const sig = req.headers.get("stripe-signature")
  if (!sig) return new Response("Missing signature", { status: 400 })

  let event: Stripe.Event
  try {
    event = stripe.webhooks.constructEvent(body, sig, process.env.STRIPE_WEBHOOK_SECRET!)
  } catch {
    return new Response("Invalid signature", { status: 400 })
  }

  // ... handle event (below)
}
```

Per stack:

- **SvelteKit:** same pattern in `+server.ts` with `await request.text()` and `request.headers.get('stripe-signature')`.
- **Express:** mount `express.raw({ type: 'application/json' })` on the webhook route only, before any global `express.json()`, then pass `req.body` (a Buffer) to `constructEvent`.
- **Other providers:** Clerk/Resend and others sign with svix headers (use the `svix` package's `Webhook.verify`); GitHub uses `x-hub-signature-256` (HMAC-SHA256 of the raw body with your secret, compare with a timing-safe equal).

The signing secret is server-side env only, never a public prefix, and it is a different value per environment (Stripe issues one per endpoint, and a separate one for `stripe listen`).

## Honest status codes

The anti-pattern the audit flags:

```ts
try {
  await fulfillOrder(event)         // fails
} catch (e) {
  console.log(e)                    // swallowed
}
return new Response("ok")           // provider sees 200, never retries
```

The fix: report the failure and let the provider retry (Stripe retries with backoff for up to 3 days).

```ts
try {
  await fulfillOrder(event)
} catch (e) {
  Sentry.captureException(e, { extra: { eventId: event.id, type: event.type } })
  return new Response("Handler failed", { status: 500 })  // provider will retry
}
return new Response("ok")
```

Two caveats:

- Event types you deliberately do not handle get an immediate 200 with no work, so the provider does not retry noise at you.
- If fulfillment is slow (near the platform's function timeout), ack fast and hand the event to a background job or queue; a timeout looks like a failure to the provider and triggers retries of work that may have half-happened.

## Idempotency

Providers deliver at least once. Retries after a timeout mean the same event can arrive twice, and a non-idempotent handler double-fulfills. Dedup on the provider's event id:

```ts
// processed_webhook_events: id text primary key, received_at timestamptz
const inserted = await db.execute(
  sql`insert into processed_webhook_events (id) values (${event.id}) on conflict do nothing`
)
if (inserted.rowCount === 0) return new Response("ok")   // already handled
await fulfillOrder(event)
```

A unique constraint plus insert-first is race-safe where a read-then-write check is not.

## Verify

- Run `stripe listen --forward-to localhost:3000/api/webhooks/stripe`, then `stripe trigger payment_intent.succeeded`, and confirm the side effect happened (the row, the email), not just a 200.
- Tamper with the body or send without the signature header and confirm a 400, with no work performed.
- Force the handler to throw and confirm a 5xx, the error in the tracker, and the event marked failed (and retried) in the provider dashboard.
- Deliver the same event twice and confirm single fulfillment.
- Grep for the webhook secret behind a public env prefix (`NEXT_PUBLIC_`, `VITE_`, `PUBLIC_`); it must not be there.
