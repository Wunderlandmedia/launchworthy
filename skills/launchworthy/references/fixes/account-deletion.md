# Fix: Account Deletion and Data Lifecycle

An app that lets a user sign up but never lets them leave is not finished. Two things are wrong at once: the user has a legal right to erasure (GDPR Article 17, CCPA) that the app cannot honor, and Apple rejects apps that create accounts but cannot delete them in-app (App Store guideline 5.1.1). This playbook builds a deletion path that actually removes the data, not one that flips a flag and reports success.

The trap to avoid is the deletion that lies. Deleting the auth record while the user's rows stay in the database returns a cheerful "your account was deleted" and keeps their name, email, and content forever. That is the worst of the three states: no deletion at least does not claim otherwise.

## Step 1: Decide hard delete vs anonymize, per table

Not every row can be dropped. An invoice you are legally required to keep for tax, an audit log, a moderation record: those stay, but they must not stay tied to a person. So split the user's data in two:

- **Delete outright:** profile, preferences, drafts, uploads, messages, sessions, anything that exists only to serve that user.
- **Anonymize and keep:** records you must retain for a real reason. Replace the foreign key with a sentinel (a shared "deleted user" id) or null it, and strip the PII columns (name, email, IP) to nulls or a hash. The row survives for accounting; the person does not.

Write the split down. "Everything cascades" is wrong for anything you are legally required to retain; "soft delete everything" is wrong for everything else.

## Step 2: Make the cascade real

Grep the schema for foreign keys pointing at the user table and confirm each one has a deletion behavior, in the schema or in the handler.

```bash
# find the references to the user table
grep -rn "references.*users\|userId\|user_id\|REFERENCES.*users\|onDelete" prisma/ drizzle/ supabase/ migrations/ db/
```

**SQL / Prisma / Drizzle: let the database enforce it.** A foreign key with no `onDelete` leaves orphans. Declare the behavior where the relation is defined so it cannot be forgotten in a handler:

```prisma
// Prisma: cascade the owned rows, null the ones you keep
model Post {
  id       String @id @default(cuid())
  author   User   @relation(fields: [authorId], references: [id], onDelete: Cascade)
  authorId String
}

model Invoice {
  id     String  @id @default(cuid())
  user   User?   @relation(fields: [userId], references: [id], onDelete: SetNull)
  userId String?
}
```

```sql
-- raw SQL: the constraint carries the rule
ALTER TABLE posts
  ADD CONSTRAINT posts_author_fkey
  FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE;
```

Prefer database-level `ON DELETE CASCADE` over deleting each table by hand in application code: a hand-rolled delete list rots the moment someone adds a table and forgets to update it, and the orphan it leaves is invisible until an audit finds it.

**Supabase:** the same, and note that a row in `auth.users` deleted via `supabase.auth.admin.deleteUser(id)` only cascades to your `public` tables if their foreign keys reference `auth.users(id)` with `ON DELETE CASCADE`. If your app rows key off a `profiles` table instead, put the cascade there and delete the profile.

## Step 3: Clean up outside the database

The user's data does not all live in your database. A deletion that stops at the DB leaves PII in every third party you integrated. In one handler, in an order where a partial failure is safe:

```ts
// app/api/account/delete/route.ts
export async function POST(req: Request) {
  const { data: { user } } = await supabase.auth.getUser()   // identity from the session, never the body
  if (!user) return new Response("Unauthorized", { status: 401 })

  // 1. cancel billing first, so nothing keeps charging a deleted customer
  const customer = await getStripeCustomerId(user.id)
  if (customer) {
    const subs = await stripe.subscriptions.list({ customer })
    for (const s of subs.data) await stripe.subscriptions.cancel(s.id)
    await stripe.customers.del(customer)
  }

  // 2. remove their objects from storage
  await deleteAllUserObjects(user.id)     // storage bucket prefix / S3 list+delete

  // 3. remove them from the email provider's audience
  await emailProvider.contacts.remove(user.email)

  // 4. delete the DB rows (cascade handles the owned tables from Step 2)
  await db.user.delete({ where: { id: user.id } })

  // 5. delete the auth record and kill every session, last
  await supabase.auth.admin.deleteUser(user.id)

  return new Response(null, { status: 204 })
}
```

Order matters. Cancel billing first so a crash halfway through never leaves a subscription charging a customer who is otherwise gone. Delete the auth record last so a retry can re-run the whole thing: the user still exists and authorizes the call until the final step. Make each external call tolerant of "already gone" so a partial failure can be retried without erroring on the parts that already succeeded.

## Step 4: If you soft delete, schedule the hard delete

A `deleted_at` flag is a reasonable first move (it lets a user recover a fat-fingered deletion, and it keeps referential integrity simple), but on its own it is concealment: the PII is still there. Make it real with a scheduled job that hard-deletes or anonymizes after a stated grace window.

```ts
// a daily cron / scheduled function
const cutoff = subDays(now, 30)                    // the window you promised
const expired = await db.user.findMany({
  where: { deletedAt: { not: null, lt: cutoff } },
})
for (const u of expired) await fullyDeleteUser(u.id)   // the Step 3 sequence
```

Then the answer to "how long until this person's data is actually gone" is a number you can state (30 days), not "never, we only hid it."

## Privacy policy honesty

The deletion path is one half of telling the truth about data; the privacy policy is the other. The audit does not certify the policy's legal wording, but two failures are code-visible and worth fixing:

- **It is a template.** If the policy still says `[Company Name]`, `Last updated: [DATE]`, `example.com`, or names a company that is not yours, it was pasted and never read. Fill it in with the real entity, contact, and date, or it is void.
- **It contradicts the code.** List the third parties your code actually sends data to (grep the deps and the bundle: analytics, Stripe, Sentry, the email provider, any ad or tracking pixel) and make sure the policy names that category of sharing. A policy that says "we do not share your data with third parties" while an analytics SDK and a payment processor are wired in is false, and false is worse than silent. Keep the disclosed list and the integrated list in sync: every time you add an SDK that sees user data, the policy gets a line.

Generate the policy from what you collect, not from a template you hope covers it. The honest version is short and specific: what you collect, why, who you share it with by name or category, how a user deletes it (link the Step 3 path), and how to reach you.

## What not to do

- **Do not delete the auth user and leave the owned rows.** That is the lie. It reports success and retains everything. Cascade or delete the rows in the same operation.
- **Do not call a `deleted_at` flag "deletion" with no job behind it.** Hiding is not erasing. Schedule the scrub or say plainly that you retain the data.
- **Do not skip cancelling the subscription.** A deleted user whose card keeps getting charged is a dispute and a support fire at once.
- **Do not take the user id to delete from the request body.** Delete the caller's own account, identified from the verified session. A delete endpoint that erases whatever id it is handed is an account-takeover-grade bug (see `fixes/auth-ownership.md`).
- **Do not gate deletion behind emailing support.** A manual queue is not a self-serve path and does not satisfy the app-store or erasure requirement.

## Verify

- Create a test account, give it data across every owned table, delete it, then query the database for rows still referencing that user id. Anything that comes back that is not a deliberately anonymized retained record is the finding.
- Confirm the deleted user's Stripe customer has no active subscription and their objects are gone from the storage bucket.
- Confirm every foreign key to the user table has an `ON DELETE` behavior (grep the schema); a key with none is a latent orphan.
- If you soft delete, confirm the scheduled job exists, runs, and actually removes the PII, and that the grace window it enforces is the one you tell users.
- Read the live privacy policy against the list of SDKs the code ships. Every third party that sees user data is named or covered; no placeholder tokens remain.
