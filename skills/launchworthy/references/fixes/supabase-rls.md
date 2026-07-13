# Fix: Supabase Row-Level Security

The single most common critical bug in vibe-coded apps. If RLS is off on a table with user data, anyone who opens your site can read the anon key from the network tab and then read or write the entire table. This is not theoretical; exposed Supabase projects are scanned constantly.

## The mental model

- The **anon key** is public by design. It appears in your frontend. That is fine.
- RLS is the wall behind that key. With RLS **on** and policies written, the anon key can only do what your policies allow. With RLS **off**, the anon key can do anything.
- So the fix is never "hide the anon key." The fix is "turn on RLS and write policies."
- The **service_role key** bypasses RLS entirely. It must live only on a server, never in the browser. If it is in client code, rotate it immediately.

## Do this carefully on a live database

Enabling RLS with no policy **denies all access**. If the app is already live, add the policies in the same migration you enable RLS, or you will lock out your own users mid-session. Test on a branch or staging project first if you have one.

## Step 1: Find tables with RLS off

Run this in the Supabase SQL editor:

```sql
select tablename, rowsecurity
from pg_tables
where schemaname = 'public'
order by rowsecurity, tablename;
```

Any row with `rowsecurity = false` that holds user or private data is a `[CRITICAL]` finding.

## Step 2: Enable RLS and add ownership policies

The common pattern is "a row belongs to the user whose id is in `user_id`." Adjust the column name to your schema.

```sql
-- Enable RLS on the table
alter table public.todos enable row level security;

-- Read your own rows
create policy "read own todos"
on public.todos for select
to authenticated
using (auth.uid() = user_id);

-- Insert rows that belong to you
create policy "insert own todos"
on public.todos for insert
to authenticated
with check (auth.uid() = user_id);

-- Update your own rows
create policy "update own todos"
on public.todos for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

-- Delete your own rows
create policy "delete own todos"
on public.todos for delete
to authenticated
using (auth.uid() = user_id);
```

Notes:
- `using` filters which existing rows the user can see or act on. `with check` validates the new/updated row. Insert and update need `with check` so a user cannot write a row owned by someone else.
- `to authenticated` means anonymous visitors get nothing. If a table is genuinely public-readable (a blog, a product catalog), use a read policy `to anon, authenticated using (true)` and keep writes locked to `authenticated` with an ownership check.

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
using (auth.uid() = author_id)
with check (auth.uid() = author_id);
```

## Step 4: Verify

- In the SQL editor: `select tablename, rowsecurity from pg_tables where schemaname = 'public';` and confirm every user-data table is now `true`.
- MANUAL: log in as User A, then try to fetch a row owned by User B through the client. You should get nothing back. Paste the result into the audit as evidence.
- Confirm `service_role` appears nowhere in client code: search the repo for `service_role` and `SUPABASE_SERVICE_ROLE`. It belongs only in server-side env, never behind a `VITE_`/`NEXT_PUBLIC_` prefix.

## What not to do

- Do not "fix" this by moving the anon key into an env var and calling it secured. The anon key is supposed to be public. RLS is the fix.
- Do not disable RLS to make a query work. If a legitimate server task needs to bypass RLS, do it from the server with the service_role key, not by turning the wall off for everyone.
