# Fix: Cache Invalidation for Authority Data

Most caching advice is about adding caching. This playbook is about the opposite failure: data that should never be stale, served from a cache whose only expiry is a clock.

The distinction that matters is not hot versus cold, it is **display data versus authority data**.

- **Display data** can be a little old without hurting anyone: a blog post, a marketing page, a dashboard chart, an avatar. Cache it aggressively with a TTL and move on.
- **Authority data** decides what a user may do or pay: roles, permissions, entitlements, subscription status, account status, prices, plan limits, inventory. A stale answer here is not slow, it is wrong.

The failure is quiet by construction. A deactivated user whose permission set is cached for an hour keeps their access for an hour, and every request succeeds. Nothing returns 500, error tracking stays empty, the uptime monitor stays green. You find out from a customer, a chargeback, or an audit.

## Step 1: Find the authority data behind a TTL

Grep for the caches first, then decide what each one holds.

```bash
# Next.js
grep -rn "unstable_cache\|\"use cache\"\|cacheLife\|revalidate:\|export const revalidate\|force-cache" app/ src/ lib/
# client caches
grep -rn "staleTime\|gcTime\|cacheTime\|localStorage.setItem\|sessionStorage.setItem" app/ src/
# server-side stores
grep -rn "setex\|EX:\|expirationTtl\|ttl:\|new Map()" app/ src/ lib/ server/
```

For each hit, ask one question: **if this value were wrong for the length of its TTL, could a user do something they should not, or pay an amount they should not?** If yes, it is authority data and a TTL alone is not enough.

Two patterns that hide in plain sight:

- A module-scope `const cache = new Map()` in a serverless function. It survives between invocations on a warm instance, with no TTL at all, so the entry can outlive the fact indefinitely and differ per instance.
- A JWT or session cookie carrying `role` or `plan` as a claim. That is a cache with a TTL equal to the token lifetime, and nothing invalidates it when the role changes.

## Step 2: Invalidate on the event, not on the clock

The rule: **whatever writes the fact clears the cache that holds it, in the same code path.** The TTL stays, but demoted to a backstop for the case where the invalidation itself fails.

**Next.js, tag the read and purge on the write**

```ts
// lib/entitlements.ts
import { unstable_cache } from "next/cache"

export const getEntitlements = (userId: string) =>
  unstable_cache(
    async () => db.entitlements.findFirst({ where: { userId } }),
    ["entitlements", userId],
    { tags: [`entitlements:${userId}`], revalidate: 3600 }  // backstop, not the mechanism
  )()
```

```ts
// app/api/webhooks/stripe/route.ts
import { revalidateTag } from "next/cache"

// after the subscription row is written, in the same handler, before returning 2xx
await db.entitlements.upsert({ /* ... */ })
revalidateTag(`entitlements:${userId}`)
```

The tag is per user and the purge is per user. A global tag purged on every write throws away the whole cache; a global tag never purged means one user's change never reaches another's key.

**Redis / KV**

```ts
// write path: admin suspends an account
await db.user.update({ where: { id: userId }, data: { status: "suspended" } })
await redis.del(`perms:${userId}`)          // same transaction boundary as the write
```

Delete rather than rewrite. A delete is idempotent and cannot lose a race with a concurrent write; a rewrite can put the old value back.

**React Query on the client**

```ts
const { mutate } = useMutation({
  mutationFn: updatePlan,
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ["entitlements", userId] }),
})
```

Client invalidation only covers the tab that made the change. Another logged-in tab or device still holds the old value until its own `staleTime` lapses, which is why the server check in Step 3 is not optional.

**Every entry point, not just the obvious one**

Entitlements change from more places than the happy path. Trace all of them and add the purge to each: the payment webhook (subscription created, updated, deleted, payment failed), the admin action, the self-serve cancel, the background job that expires trials, the manual SQL someone will eventually run. The last one is the argument for keeping a sane TTL as a backstop.

## Step 3: Check the authority at the moment of the action

Caching decisions for the UI is fine. Trusting them at the point of effect is not.

```ts
// app/api/export/route.ts
export async function POST(req: Request) {
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return new Response("Unauthorized", { status: 401 })

  // uncached read, straight from the source, on the action that matters
  const sub = await db.subscriptions.findFirst({
    where: { userId: user.id },
    select: { status: true, plan: true },
  })
  if (sub?.status !== "active") return new Response("Payment required", { status: 402 })

  // ...do the expensive thing
}
```

Hide the button with cached data if you like. Decide with fresh data. The set of actions that deserve an uncached check is small: anything that spends money, grants access, exports data, or crosses a plan limit.

## Step 4: State the revocation window

Write down, in a comment or the runbook, the answer to: *an account is suspended right now, how long until it is actually locked out?* The number should come from the code, not from hope.

- Event-driven invalidation plus an uncached check on the action: effectively immediate.
- Event-driven invalidation only: immediate for the paths that read the cache, minus whatever a stale JWT still carries.
- TTL only: the full TTL, per cached principal, every time.
- A role claim inside a 30-day session token with no server re-check: 30 days.

If that number is unacceptable for the worst thing a revoked user can do, shorten it deliberately rather than discovering it later.

## What not to do

- **Do not cache the permission check itself.** Cache the underlying data with a tag you can purge; a memoized `canUserDoX()` result is invisible to every invalidation you write.
- **Do not fix this by shortening the TTL to 30 seconds.** That trades a big wrong window for a small one, multiplies your read load, and still fails the audit question. Invalidate on the event.
- **Do not put per-user authority data behind one global cache key.** Either every purge nukes every user, or one user's stale value is served to everyone.
- **Do not trust `localStorage` for what a user is allowed to do.** It is editable by the user, and stale on top of that.
- **Do not let ISR render plan-gated pages.** A page prerendered with `revalidate: 3600` that shows premium content serves the premium build to whoever asks until it rebuilds. Gate on a dynamic server read.

## Verify

- Change the fact in the database (suspend an account, cancel the subscription) and reload as that user. If the old capability survives, note how long it survives; that number is the finding.
- Send the real event (Stripe CLI: `stripe trigger customer.subscription.deleted`) and confirm the app reflects it on the next request, not on the next TTL expiry.
- Grep the write paths for the fact and confirm each one purges: webhook, admin action, self-serve action, expiry job.
- Confirm the caches are keyed per user and purged per user, so one user's change does not clear or leak into another's.
- Confirm the money and access actions read uncached at the moment they act, however the UI got its state.
