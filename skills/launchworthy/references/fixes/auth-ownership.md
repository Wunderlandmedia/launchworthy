# Fix: Server-Side Ownership Checks

The "user A can read user B's data" hole. It happens when an endpoint checks that *someone* is logged in but not that *this* someone owns the thing they asked for. If your data layer enforces ownership (Supabase RLS, Firebase Rules), that is your primary defense. This playbook is for the cases where you query with a privileged key from a server route, ORM, or API, and the database is not filtering for you.

## The bug

```ts
// BROKEN: any logged-in user can read any order by guessing the id
export async function GET(req, { params }) {
  const order = await db.order.findUnique({ where: { id: params.id } })
  return Response.json(order)
}
```

The user is authenticated, so this "works," but it returns other people's orders.

## The fix: scope every query to the current user

```ts
// FIXED: the query itself is constrained to rows the user owns
export async function GET(req, { params }) {
  const user = await getCurrentUser(req)          // your session/JWT lookup
  if (!user) return new Response("Unauthorized", { status: 401 })

  const order = await db.order.findFirst({
    where: { id: params.id, userId: user.id },    // ownership is part of the query
  })
  if (!order) return new Response("Not found", { status: 404 })
  return Response.json(order)
}
```

Two principles:
1. **Put ownership in the `where` clause, not in an `if` after the fetch.** Filtering in the query means the database can never hand you a row you should not see. Return 404 (not 403) for someone else's resource so you do not confirm it exists.
2. **Derive the user id from the session/token on the server, never from the request body or a query param.** If the client sends `userId`, an attacker sends someone else's.

## Same idea for a service-key Supabase call from a server

```ts
// If you must use the service_role key server-side, YOU enforce ownership,
// because service_role bypasses RLS.
const { data } = await supabaseAdmin
  .from('orders')
  .select('*')
  .eq('id', orderId)
  .eq('user_id', session.user.id)   // do not omit this
  .single()
```

## SvelteKit

Resolve the user once in `hooks.server.ts` into `event.locals`, then scope every server `load` and action to it. The user comes from the session, never from a param.

```ts
// src/routes/orders/[id]/+page.server.ts
import { error } from "@sveltejs/kit"

export async function load({ params, locals }) {
  if (!locals.user) throw error(401, "Unauthorized")

  const order = await db.order.findFirst({
    where: { id: params.id, userId: locals.user.id },   // ownership in the query
  })
  if (!order) throw error(404, "Not found")
  return { order }
}
```

## TanStack Start

Read the session inside the server function (or a shared auth middleware) and put ownership in the query. Never trust an id or user field from the client input.

```ts
import { createServerFn } from "@tanstack/react-start"

export const getOrder = createServerFn({ method: "GET" })
  .validator((d: unknown) => z.object({ id: z.string() }).parse(d))
  .handler(async ({ data }) => {
    const user = await getSessionUser()          // from cookie/session, server-side
    if (!user) throw new Error("Unauthorized")

    const order = await db.order.findFirst({
      where: { id: data.id, userId: user.id },   // ownership in the query
    })
    if (!order) throw new Error("Not found")
    return order
  })
```

## Admin routes

Admin access is the same check one level up: verify a role, server-side, on every privileged endpoint and not just by hiding the link.

```ts
const user = await getCurrentUser(req)
if (!user || user.role !== 'admin') {
  return new Response("Forbidden", { status: 403 })
}
```

## Verify

- Grep your API routes and server actions for queries that fetch by id without a user/owner constraint.
- MANUAL: log in as User A, call the endpoint with an id owned by User B, paste the response. A 404 is correct. Returning B's data is `[CRITICAL]`.
