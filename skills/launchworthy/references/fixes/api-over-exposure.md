# Fix: API Over-Exposure

The ownership fix (`fixes/auth-ownership.md`) decides who may read a row. This one decides what is in the row when they do.

The bug is boring and that is why it ships: a query says `*`, the handler returns what the query returned, and the component renders the three fields it needs. The other fourteen are still in the response. The browser has them, the network tab shows them, and on a server-rendered page the page source carries them. Rendering is not filtering.

What actually leaks this way, in rough order of how much it costs you:

- Auth material: `password_hash`, `reset_token`, `verification_token`, `two_factor_secret`, a stored OAuth `access_token`. A hash is cracked offline; a reset token is an account takeover in one request.
- Other people's personal data: emails, phone numbers, addresses, IPs, pulled in by an author or owner join on a list endpoint. Paginated, so it is a loop, not an exploit.
- Internal state: `is_admin`, `banned`, `credits`, `internal_notes`, `moderation_status`, `cost` and `margin`, flags for features you have not announced.

## Step 1: Find what the responses actually contain

Read the query, not the component.

```bash
# explicit star selects
grep -rn "select('\*')\|select(\"\*\")\|SELECT \*" app/ src/ lib/ server/
# ORM reads with no projection
grep -rn "findMany(\|findFirst(\|findUnique(" app/ src/ lib/ | grep -v "select:\|omit:"
grep -rn "db.query\." app/ src/ lib/ | grep -v "columns:"
# what leaves the server
grep -rn "res.json(\|NextResponse.json(\|Response.json(\|return { props:" app/ src/ pages/
```

Then, for each table a response touches, read the schema and list the columns the client does not need. That list is the finding. If the schema is not in the repo, get the column list from the database:

```sql
select column_name from information_schema.columns where table_name = 'users';
```

The two cases the grep misses:

- A join or `include` that expands a relation. `select('*, author(*)')` in Supabase, or a Prisma `include: { user: true }`, returns the whole related row even when the outer select looks careful.
- A server-to-client boundary with no HTTP call at all. A Next.js server component passing a row as a prop to a `'use client'` component serializes the whole object into the RSC payload; `getServerSideProps` returning a record embeds it in `__NEXT_DATA__`; a SvelteKit `load` or a TanStack Start loader returning a row ships it in the page data. Same leak, no endpoint to inspect.

## Step 2: Select the fields, do not delete them afterwards

Ask the database for what the client needs. A projection cannot forget a column that gets added next month; a delete list can, and will.

**Supabase**

```ts
// before
const { data } = await supabase.from("profiles").select("*")

// after
const { data } = await supabase
  .from("profiles")
  .select("id, display_name, avatar_url, created_at")
```

**Prisma**

```ts
const users = await prisma.user.findMany({
  select: { id: true, displayName: true, avatarUrl: true },
})
```

`select` is safer than `omit`: `select` is a list of what is allowed out, `omit` is a list of what is denied, and only one of those stays correct when someone adds `stripe_customer_id` to the model.

**Drizzle**

```ts
const rows = await db.query.users.findMany({
  columns: { id: true, displayName: true, avatarUrl: true },
})
```

**Relations too**

```ts
// posts with their author, without the author's account record
const { data } = await supabase
  .from("posts")
  .select("id, title, body, created_at, author:profiles(id, display_name, avatar_url)")
```

## Step 3: Give each resource one public shape

Once more than one route returns the same entity, the field list belongs in one place, next to the type, so a new route cannot invent its own.

```ts
// lib/serializers.ts
export const PUBLIC_USER_FIELDS = ["id", "displayName", "avatarUrl"] as const

export function toPublicUser(user: User) {
  return {
    id: user.id,
    displayName: user.displayName,
    avatarUrl: user.avatarUrl,
  }
}

// the caller's own record can carry more, and says so by name
export function toPrivateUser(user: User) {
  return { ...toPublicUser(user), email: user.email, plan: user.plan }
}
```

Two shapes, chosen by who is asking: `toPrivateUser` only for the row belonging to the verified session, `toPublicUser` for everyone else. A single "user" shape that includes the email is how another user's address ends up in a comment thread.

## Step 4: Supabase, keep private columns out of the browser's reach

Row-level security decides which rows come back. It says nothing about columns, so a browser holding the anon key can `select('*')` on any row a policy allows and read every column of it, including whatever gets added later.

Close it with column privileges: take table-wide read away from the browser roles, give them read on the public columns only, and put a view over those columns so the client still has something it can `select('*')` from.

```sql
-- the browser roles may read only the public columns of profiles
revoke select on public.profiles from anon, authenticated;
grant select (id, display_name, avatar_url, created_at) on public.profiles to anon, authenticated;

-- a view over exactly those columns; security_invoker keeps the table's RLS in force
create view public.public_profiles with (security_invoker = on) as
  select id, display_name, avatar_url, created_at
  from public.profiles;

grant select on public.public_profiles to anon, authenticated;
```

What changes for the app:

- `select('*')` on `profiles` from the browser now fails with permission denied instead of returning every column. Read `public_profiles`, or name the columns.
- Row policies keep working, including ones that test a private column: RLS filters rows through the view the same way it does on the table.
- Writes keep their grants, since only `select` was revoked. A write that asks for the row back, `update(...).select()`, must name public columns too.
- A user's own private fields (their email, their plan) are no longer readable through the browser client, and not through a session-scoped server client either, since it runs as the same role. Read them on the server with the service-role client, filtered by the verified user's id (Fix B in `fixes/supabase-rls.md` Step 4), or take the email from `supabase.auth.getUser()`.

Do not pair `security_invoker = on` with revoking all table access from `anon` and `authenticated`. The view runs as the caller, the caller can no longer read the table, and every read through the view fails with permission denied.

For a table that is mostly private, moving the private columns into their own table with owner-only policies is the simpler shape to live with.

## Step 5: Fix the server-to-client boundary

```tsx
// app/dashboard/page.tsx  (server component)
const user = await db.user.findUnique({ where: { id: session.userId } })

// wrong: the whole row is serialized into the RSC payload
return <ProfileCard user={user} />

// right: pass the fields the component renders
return <ProfileCard id={user.id} name={user.displayName} avatar={user.avatarUrl} />
```

The same rule covers `getServerSideProps` return values, SvelteKit `load` return values, and TanStack Start loader data. Whatever you return crosses the wire in full.

## What not to do

- **Do not filter in the frontend.** Hiding a field in JSX changes nothing about the response. The network tab is not a privileged view; it is the same data the page already received.
- **Do not `delete row.password_hash` on the way out.** It is a denylist maintained by memory. The next sensitive column, added by someone else, is not in it. Project in the query.
- **Do not rely on RLS or an ownership check for columns.** Both are about rows. A user who legitimately owns a row still should not receive its `internal_notes`.
- **Do not return the full row on writes either.** `insert(...).select('*')` and `update(...).returning()` hand back everything, including columns set by triggers and defaults.
- **Do not treat "the field is not documented" as protection.** An undocumented field in a JSON response is a documented field.

## Verify

- Open the app with DevTools > Network, load the list, feed, and profile pages, and read the field names in the largest JSON responses. Anything in there that the page does not render is over-exposure.
- Curl the list endpoint directly and count the keys per object; the count should match the field list in the serializer, not the column count of the table.
- View source on a server-rendered page and search the HTML for a known-sensitive column name (`email`, `stripe_customer_id`). The RSC payload and `__NEXT_DATA__` are in that source.
- Supabase: from the browser (or with the anon key), `select('*')` the table. It should fail with permission denied, and `select('*')` on the view should return only the public columns. If the table hands back every column, the grants are not in place.
- Add a column to a user table, change nothing else, and re-run the first check. A correct projection does not start returning it.
