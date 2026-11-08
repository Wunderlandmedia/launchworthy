# Fix: Supabase Row-Level Security

The single most common critical bug in vibe-coded apps. If RLS is off on a table with user data, anyone who opens your site can read the anon key from the network tab and then read or write the entire table. This is not theoretical; exposed Supabase projects are scanned constantly.

## The mental model

- The **anon key** is public by design. It appears in your frontend. That is fine.
- RLS is the wall behind that key. With RLS **on** and policies written, the anon key can only do what your policies allow. With RLS **off**, the anon key can do anything the table's grants allow, which on a table that has the old automatic grants is everything.
- **Grants** come before both. A grant decides whether a role (`anon`, `authenticated`) can touch a table at all; RLS decides which rows. Supabase used to grant every new `public` table to `anon`, `authenticated`, and `service_role` automatically. It stopped for new projects from 2026-05-30 and for new tables on every project from 2026-10-30; tables created before that keep their grants. A table with no grant fails every Data API call with `42501 permission denied for table`, whatever its policies say.
- So the fix is never "hide the anon key." The fix is "turn on RLS, write policies, and grant each role only the access it needs."
- The **service_role key** bypasses RLS entirely. It must live only on a server, never in the browser. If it is in client code, rotate it immediately.
- Newer projects use a **publishable key** (`sb_publishable_...`) in place of the anon key and a **secret key** (`sb_secret_...`) in place of `service_role`; Supabase deprecates the legacy pair by the end of 2026. Same rules: the publishable key is public, the secret key is server-only.

## Do this carefully on a live database

Enabling RLS with no policy **denies all access**. If the app is already live, add the policies in the same migration you enable RLS, or you will lock out your own users mid-session. Test on a branch or staging project first if you have one.

## Step 1: Find tables with RLS off, and who can reach them

Run this in the Supabase SQL editor:

```sql
select c.relname as table_name,
       c.relrowsecurity as rls_on,
       has_any_column_privilege('anon', c.oid, 'select, insert, update')
         or has_table_privilege('anon', c.oid, 'delete') as anon_reach,
       has_any_column_privilege('authenticated', c.oid, 'select, insert, update')
         or has_table_privilege('authenticated', c.oid, 'delete') as authenticated_reach
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r', 'p')
order by c.relrowsecurity, c.relname;
```

Read the columns together, for every table that holds user or private data:

- `rls_on = false` and either reach column `true`: `[CRITICAL]`. Count `authenticated` as public too: with sign-ups open, anyone with an email address is authenticated.
- `rls_on = false` and both reach columns `false`: the Data API cannot reach it today, but one grant makes it wide open. `[MEDIUM]`; enable RLS now, before someone adds a grant to make a query work.

## Step 2: Enable RLS, add ownership policies, then grant access

The common pattern is "a row belongs to the user whose id is in `user_id`." Adjust the column name to your schema.

```sql
-- Enable RLS on the table
alter table public.todos enable row level security;

-- Read your own rows
create policy "read own todos"
on public.todos for select
to authenticated
using ((select auth.uid()) = user_id);

-- Insert rows that belong to you
create policy "insert own todos"
on public.todos for insert
to authenticated
with check ((select auth.uid()) = user_id);

-- Update your own rows
create policy "update own todos"
on public.todos for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

-- Delete your own rows
create policy "delete own todos"
on public.todos for delete
to authenticated
using ((select auth.uid()) = user_id);

-- Grants last, so the table is never reachable without its policies.
-- No grant to anon. An older table may still carry one from the automatic
-- grants; with no policy for anon, RLS returns logged-out visitors nothing.
grant select, insert, update, delete on table public.todos to authenticated;
grant select, insert, update, delete on table public.todos to service_role;
```

Notes:
- `using` filters which existing rows the user can see or act on. `with check` validates the new/updated row. Insert and update need `with check` so a user cannot write a row owned by someone else.
- `(select auth.uid())` instead of a bare `auth.uid()` lets Postgres evaluate it once per query instead of once per row. Same result, faster on big tables.
- On a table that still has the old automatic grants, the `grant` lines change nothing. On a table created after the change, they are what makes it reachable. Keep them either way, so the migration works on any project.
- If the id column is `serial` or `bigserial`, inserts also need the sequence: `grant usage on sequence public.todos_id_seq to authenticated;`. Ids that are `generated ... as identity` or `uuid default gen_random_uuid()` do not.
- A query that fails with `42501 permission denied for table` is missing a grant, not a policy. Grant the role that should have access (usually `authenticated`), never `anon` by reflex.
- `to authenticated` means anonymous visitors get nothing. If a table is genuinely public-readable (a blog, a product catalog), use a read policy `to anon, authenticated using (true)`, grant `select` to `anon`, and keep writes locked to `authenticated` with an ownership check (Step 3).

## Step 3: Public-read, owner-write example

For content everyone can read but only the author can change:

```sql
alter table public.posts enable row level security;

create policy "anyone can read posts"
on public.posts for select
to anon, authenticated
using (true);

create policy "authors manage own posts"
on public.posts for all
to authenticated
using ((select auth.uid()) = author_id)
with check ((select auth.uid()) = author_id);

-- Everyone reads; only logged-in users write, and the policy narrows that to authors.
grant select on table public.posts to anon;
grant select, insert, update, delete on table public.posts to authenticated;
grant select, insert, update, delete on table public.posts to service_role;
```

## Step 4: Close the service-role bypass on the server

RLS on every table is necessary, not sufficient. The `service_role` client bypasses every policy by design, so any server route that uses it is outside the wall. If that route filters by an id the caller supplied, the caller can pass someone else's id and the database will happily comply. The tables still show `rls_on = true`, which is what makes this a false green.

Find the service-role paths:

```bash
grep -rn "SUPABASE_SERVICE_ROLE\|service_role\|SUPABASE_SECRET\|sb_secret_\|supabaseAdmin\|createServiceClient" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.sql" .
```

For each hit, ask what user data it reads or writes and where the user id comes from.

Vulnerable, because `userId` arrives from the client:

```ts
// app/api/orders/route.ts
const admin = createClient(url, process.env.SUPABASE_SERVICE_ROLE_KEY!)

export async function GET(req: Request) {
  const userId = new URL(req.url).searchParams.get('userId')
  const { data } = await admin.from('orders').select('*').eq('user_id', userId)
  return Response.json(data) // any id the caller types, RLS never consulted
}
```

Fix A, preferred: use the request's authenticated client so RLS applies.

```ts
// The session-scoped server client runs as the logged-in user, so the
// "read own orders" policy filters the rows. No id from the caller at all.
const supabase = createServerClient(url, anonKey, { cookies })
const { data: { user } } = await supabase.auth.getUser()
if (!user) return new Response('Unauthorized', { status: 401 })

const { data } = await supabase.from('orders').select('*')
```

Fix B, when service-role is genuinely required (cross-user admin work, background jobs, webhook handlers): derive the identity from the verified session and enforce ownership in the query yourself.

```ts
const supabase = createServerClient(url, anonKey, { cookies })
const { data: { user } } = await supabase.auth.getUser()
if (!user) return new Response('Unauthorized', { status: 401 })

// The id comes from the verified session, never from the request.
const { data } = await admin.from('orders').select('*').eq('user_id', user.id)
```

For a route that must act across users, check the caller's role server-side first (see `fixes/auth-ownership.md`), and keep the admin client in a server-only module so it cannot be imported into a client component.

Rules of thumb:
- Never trust a user id from a request body, query param, or header when using the service-role client.
- `getUser()` verifies the token with Supabase. `getSession()` reads it from the cookie; do not use it as the authorization source on the server.
- If service-role was introduced to make a query work, the real bug is a missing policy. Fix the policy and drop back to the authenticated client.

## Step 5: Verify

- In the SQL editor, re-run the Step 1 query. Every user-data table shows `rls_on = true`, and `anon_reach` is `true` only on tables meant to be public.
- MANUAL: log in as User A, then try to fetch a row owned by User B through the client. You should get nothing back. Paste the result into the audit as evidence.
- Confirm `service_role` appears nowhere in client code: search the repo for `service_role`, `SUPABASE_SERVICE_ROLE`, `sb_secret_`, and `SUPABASE_SECRET`. It belongs only in server-side env, never behind a `VITE_`/`NEXT_PUBLIC_` prefix.

## What not to do

- Do not "fix" this by moving the anon key into an env var and calling it secured. The anon key is supposed to be public. RLS is the fix.
- Do not silence `42501 permission denied` with `grant all on ... to anon`, a grant on every table in the schema, or `alter default privileges ... grant ... to anon`. Each one re-opens tables nobody meant to expose, and on a table with RLS off it hands the whole table to anyone.
- Do not disable RLS to make a query work. If a legitimate server task needs to bypass RLS, do it from the server with the service_role key, not by turning the wall off for everyone, and give that path its own ownership check (Step 4).
- Do not treat "RLS is on for every table" as the finish line. A service-role route that filters by a caller-supplied id is the same data leak with a green checkmark over it.
