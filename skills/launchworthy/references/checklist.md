# Production Readiness Check List

The audit, organized into 5 domains. Each check has a severity tag. Apply the checks that fit the detected stack; skip the ones that do not and say why. For anything you cannot verify from code, mark `MANUAL CHECK NEEDED` and demand the evidence noted with the check.

Severity: `[CRITICAL]` (fix before any real user), `[HIGH]` (fix this week), `[MEDIUM]` (fix this month), `[LOW]` (nice to have).

---

## Domain 1: Frontend & Experience

What users see when things go right, and especially when they break.

**Error boundaries:**
- [ ] React (Next.js/Vite/Remix): ErrorBoundary components or `error.tsx` covering every major route/view, so one thrown error does not white-screen the whole app. Missing = `[HIGH]`.
- [ ] TanStack Start/Router: routes define an `errorComponent` (or the router sets a `defaultErrorComponent`) and the root route has a `notFoundComponent`. None = `[HIGH]`.
- [ ] SvelteKit: `+error.svelte` pages plus a `handleError` hook in `hooks.server.js`/`hooks.client.js` for logging. Svelte 5 can also use `<svelte:boundary>`. Missing both the route error page and the hook = `[MEDIUM]`.
- [ ] Astro `404.astro`/`500.astro`. Missing = `[MEDIUM]`.

**Loading states:**
- [ ] Next.js `loading.tsx` / Suspense on async routes. Missing = `[HIGH]`.
- [ ] TanStack Start/Router: routes with a `loader` define a `pendingComponent` (or a router `defaultPendingComponent`) so navigation is not a frozen screen. Missing = `[MEDIUM]`.
- [ ] SvelteKit: slow `load` functions have feedback via the `$navigating` store or `{#await}` blocks. Missing = `[MEDIUM]`.
- [ ] Any data-fetching client component renders a loading state, not a blank screen. Missing = `[MEDIUM]`.

**Empty states:**
- [ ] Components that map over arrays handle length 0 with a helpful message, not a void (Svelte: the `{:else}` clause of `{#each}`; React: an explicit `length === 0` branch). Missing = `[MEDIUM]`.

**Responsive:**
- [ ] Responsive utilities used (Tailwind `sm:`/`md:`/`lg:` or media queries). A layout with fixed widths and no responsive handling = `[MEDIUM]`. Fixed pixel widths that should be fluid = `[LOW]`.

**Accessibility:**
- [ ] Every `<img>`/`<Image>` has `alt`. Missing = `[MEDIUM]`.
- [ ] Every `<input>`/`<select>`/`<textarea>` has a `<label>` or `aria-label`. Missing = `[MEDIUM]`.
- [ ] Icon-only buttons/links have `aria-label`. Missing = `[LOW]`.

**Console errors:**
- [ ] MANUAL CHECK NEEDED. Steps: "Open the app, open DevTools Console, click through every main page." Evidence: paste any red errors, or confirm the console is clean.

**Bundle size:**
- [ ] If build output exists, First Load JS over 200KB = `[MEDIUM]`, over 350KB = `[HIGH]`.
- [ ] Heavy client imports: moment.js (prefer date-fns), full lodash import, whole icon libraries. Each = `[MEDIUM]`.

---

## Domain 2: Backend & Data

The engine: how data moves, gets stored, and holds up under load. (Connection pooling, background jobs, webhooks, and external-API resilience live here, not in Infrastructure.)

**No direct DB or admin access from the browser:**
- [ ] No client-side code (files with `'use client'`, anything shipped to the browser) imports a DB driver/ORM or calls an API with an admin/service key. Privileged access goes through server components, API routes, server actions, or edge functions. Violation = `[CRITICAL]`.
- [ ] SvelteKit: database and secret access lives in server-only files (`+page.server.ts`, `+server.ts`, `$lib/server/*`), never in `+page.svelte`, universal `+page.ts`, or shared `$lib`. SvelteKit blocks server imports from client code, but a secret read through a `PUBLIC_` env still leaks. DB or secret reachable from universal/client code = `[CRITICAL]`.
- [ ] TanStack Start: database and secret access lives inside `createServerFn` handlers or server routes, never in components or isomorphic loaders. Privileged access outside a server function = `[CRITICAL]`.
- [ ] Vite/SPA: the browser talks to an API, or to a backend-as-a-service with a public key plus row-level rules, never to a database with a service key. Service key in the browser = `[CRITICAL]`.

**Input validation:**
- [ ] Every mutating entry point validates incoming data before using it: Next.js API routes and server actions, SvelteKit form `actions` and `+server.ts` handlers, TanStack Start `createServerFn` (use its built-in `.validator()`), or any edge function. Use Zod, Valibot, or explicit checks. No validation anywhere = `[HIGH]`. See `fixes/input-validation.md`.

**Business logic location:**
- [ ] Access rules, pricing, and permission decisions are enforced server-side, not only in client code the user can edit in DevTools. Client-only enforcement of a rule that matters = `[HIGH]`.

**API hygiene:**
- [ ] Handlers return meaningful status codes (400/401/403/404/500), not 200 for everything. All-200 = `[MEDIUM]`.
- [ ] No raw error objects or stack traces returned to clients (leaks internals) = `[HIGH]`. Inconsistent error shapes = `[LOW]`.

**Response over-exposure (canonical home for what a response body contains):**

The ownership check in Domain 3 asks whether this caller may see this row. This asks what is inside the row once they may. AI tools reach for `select('*')` and `return user` because it works on the screen, and the screen is the wrong place to look: the fields nobody renders are still in the response body, in the network tab, and in the page source. That is where the email addresses, the password hashes, the reset tokens, the internal flags, and the other user's Stripe id are sitting. Nothing errors, nothing looks wrong, and the endpoint is paginated, so collecting it is a loop and not an exploit.

Find the shape of every response that leaves the server:

```bash
grep -rn "select('\*')\|select(\"\*\")\|SELECT \*" app/ src/ lib/ server/
grep -rn "findMany(\|findFirst(\|findUnique(\|\.query\." app/ src/ lib/ | grep -v "select:\|columns:"
grep -rn "res.json(\|NextResponse.json(\|Response.json(\|return { props:" app/ src/ pages/
```

- [ ] Responses are shaped from an explicit field list, not from whatever the query happened to return. A handler that hands the client a whole database row (`select('*')`, a Prisma `findMany` with no `select`, a Drizzle query with no `columns`, `res.json(row)`) = `[MEDIUM]` on its own, and the severities below when the table holds any of what follows. The fix is a field list at the boundary, not a `delete row.password` on the way out. See `fixes/api-over-exposure.md`.
- [ ] No credential or auth material reaches a client, ever. `password`, `password_hash`, `salt`, `reset_token`, `verification_token`, `two_factor_secret`, `recovery_codes`, `api_key`, `refresh_token`, `session_token`, or a stored third-party `access_token` in a response body = `[CRITICAL]`, whether or not the UI renders it. A hash is cracked offline at leisure and a reset token is an account takeover in a single request, so this is not a privacy finding, it is a break-in.
- [ ] Other users' personal data does not ride along in list, search, feed, comment, leaderboard, or public-profile responses. A join that pulls the full author or owner row (email, phone, address, date of birth, last known IP) into something any logged-in user can request = `[HIGH]`. One paginated endpoint like this is the whole user table's email list, which is why it is the shape that ends up in breach write-ups.
- [ ] Internal and privileged columns stay on the server. `is_admin`, `role`, `banned`, `credits`, `balance`, `internal_notes`, `moderation_status`, `flagged_by`, `cost`, `margin`, unreleased feature flags, another user's `stripe_customer_id` = `[MEDIUM]`, raised to `[HIGH]` where the field is another user's commercial data or where the client uses it to unlock UI (the missing server-side check is then a Domain 3 finding of its own).
- [ ] Server-rendered frameworks leak the same rows without any API to look at. A Next.js server component that passes a full row as a prop to a client component serializes every column into the RSC payload; `getServerSideProps` returning a whole record embeds it in `__NEXT_DATA__`; a SvelteKit `load` or a TanStack Start loader returning a full row ships it in the page data. Not rendering a field does not remove it, view source does. A full row crossing the server-to-client boundary scores the same as returning it from an endpoint.
- [ ] Supabase: row-level security does not do columns. A policy decides which rows come back; `select('*')` from the browser then returns every column of those rows, including the ones added to the table months later by someone who never thought about this query. Where a table mixes public and private columns, grant the browser roles read on the public columns only, put a view over them, and select explicit fields from the client. Client-side `select('*')` against a table holding secrets, PII, or privileged flags = `[HIGH]`. See `fixes/api-over-exposure.md`.
- [ ] MANUAL CHECK NEEDED. Steps: "Open the app, DevTools > Network, load the main list or feed page and your own profile page. Expand the biggest JSON response and read the field names." Evidence: paste the list of field names, never the values. The check is what is present, not what is displayed.
- [ ] Score it by what a stranger can collect, not by what the page shows. Response shape cannot be `PASS` while any response carries auth material or another user's personal data. Report it concretely: the route, the columns that should not be there, and what a paginated loop over that endpoint yields ("`/api/posts` returns every author's email; 40 per page, no cap").

**Webhooks (canonical home; payment and provider callbacks):**

The dangerous property of a webhook is that the caller believes your status code. Return 200 and the provider marks the event delivered and never retries; your dashboards stay green while the work never happened.

- [ ] Webhook endpoints verify the provider signature before processing (Stripe `constructEvent` with the signing secret, svix headers, `x-hub-signature-256`). Missing = `[HIGH]`; if the handler grants access, records a payment, or changes entitlements from the event, a forgeable webhook = `[CRITICAL]`, because anyone who finds the URL can mint the event. See `fixes/webhooks.md`.
- [ ] The handler returns 2xx only after the work succeeded. A catch block that swallows the error and returns 200 anyway is the classic silent revenue failure: the provider sees a successful delivery and moves on, error tracking sees nothing because nothing threw. Swallowed catch returning 2xx = `[HIGH]`. On failure, log to the error tracker and return 5xx so the provider retries. See `fixes/webhooks.md`.
- [ ] Handlers that fulfill, charge, or grant are idempotent. Providers deliver at least once and retry on timeouts, so the same event can arrive twice. No dedup by event id = `[MEDIUM]`.
- [ ] Fast-ack rule: events the app deliberately ignores get an immediate 200 with no work, so retries of irrelevant events do not pile up. Heavy fulfillment inside the webhook request risks the provider's timeout; hand off to a background job for slow work (see Background jobs). Advisory unless timeouts are plausible, then `[MEDIUM]`.
- [ ] MANUAL CHECK NEEDED. Steps: "Open the provider's webhook dashboard (Stripe: Developers > Webhooks > your endpoint) and look at the recent deliveries." Evidence: paste the success/failure counts for the last week and the latest failure's status code, if any. Note: a wall of 200s proves delivery, not that the work happened; the swallowed-catch check above is why this stays code-first.

**Payments lifecycle (only when a payment provider is detected):**

Detecting `stripe` / `@stripe/stripe-js`, `braintree`, `@paddle/paddle-js`, `@lemonsqueezy/*`, `paypal`, or `razorpay` means the app takes money. Taking a first payment is the easy part an AI tool gets right. The lifecycle after it is where revenue leaks: a renewal card that quietly declines, a customer who wanted a refund and could not find how, a chargeback that auto-loses because nobody saw it in time. These are mostly configured in the provider dashboard, not in code, so most are evidence requests, but a few leave code fingerprints and those come first.

- [ ] Failed renewal payments are retried and dunned. On a subscription, a renewal charge fails routinely (expired card, insufficient funds). With no retry schedule and no failed-payment email, the subscription lapses silently: the customer stops paying and either keeps access unpaid or is cut off with no warning and churns. Code signal: a webhook that grants access on `checkout.session.completed` or `invoice.paid` but has no `invoice.payment_failed` branch at all is handling only the happy path = `[HIGH]`. The retry schedule and dunning emails themselves are dashboard settings: MANUAL CHECK NEEDED, evidence is the provider's retry configuration (Stripe: Billing > Revenue recovery / Smart Retries) and a sample dunning email. See `fixes/payments-lifecycle.md`.
- [ ] A refund and cancellation policy is linked from the point of charge. Grep the checkout / pricing / paywall route for a link to refund, cancellation, or billing terms (a `refund`, `/terms`, `/cancellation`, `billing-policy` href near the pay button). None reachable from where money changes hands = `[MEDIUM]`. Card networks and app stores expect it, its absence raises the dispute rate (a customer who cannot find how to cancel disputes instead), and "no refunds" is a policy you can state but not one you can hide.
- [ ] Disputes and chargebacks are seen in time to answer. A chargeback gives you a fixed, short window (often about 7 days) to submit evidence, and an unanswered dispute is auto-lost. Code signal: no `charge.dispute.created` (or provider equivalent) webhook handler and no alert means the first you hear of a dispute is a lost-balance line later = `[MEDIUM]`, raised to `[HIGH]` if that path also revokes access or entitlements, because the money left with no notice. Whether you actually retain the evidence to win (what was sold, when, access and usage logs, the ToS acceptance) is MANUAL CHECK NEEDED: evidence is the provider's dispute settings and a description of what you would submit. See `fixes/payments-lifecycle.md`.
- [ ] Score it as a lifecycle, not a checkout. A payment integration that charges once but never notices a failed renewal, never offers a refund path, and never answers a dispute is a demo that happens to move money. Payments cannot be `PASS` while the renewal-failure path is unhandled in code; report the specific gap (the missing `invoice.payment_failed` branch, the checkout with no policy link) with its file and route, and record the dashboard-side items as `MANUAL CHECK NEEDED`, never as self-certified passes.

**Schema, indexes, migrations:**
- [ ] Schema changes are tracked (Prisma/Drizzle/Supabase migrations, raw SQL, CMS snapshots). Schema that only lives in a dashboard with no migration history = `[HIGH]`; nobody can rebuild it.
- [ ] Foreign keys and frequently filtered columns are indexed. Missing on a hot path = `[MEDIUM]`.
- [ ] Tables with 20+ columns can signal denormalization = `[MEDIUM]`.

**Connection pooling (canonical home):**
- [ ] Serverless + SQL: the connection string uses a pooler (Supabase pooler port 6543 vs direct 5432, PgBouncer, Prisma Accelerate, Neon/PlanetScale serverless driver). A serverless function opening a direct connection per invocation exhausts the database under load = `[HIGH]`.
- [ ] Long-lived server (Docker/VPS) with a normal pool: missing pooling = `[LOW]`.

**N+1 queries:**
- [ ] Loops making one DB/API call per item. Each = `[MEDIUM]`. Fetch related data in one query with a join/expand.

**Background jobs and heavy work (canonical home):**
- [ ] Heavy work (email, image/video processing, long AI calls) done inline in the request with no queue = `[HIGH]` at scale.
- [ ] Operations that can exceed the host's function duration limit with no awareness = `[MEDIUM]`. The limit depends on the host and the plan; the specific mismatches, and how they fail, are in Platform limits below.

**Platform limits the code does not know about (canonical home for host ceilings):**

There are two limits on every request and only one of them is in the repo. The app has its own: a validated max file size, an `export const maxDuration`, a retry count. The host has another: a request-body cap, a function timeout on this plan. When the app's number is the larger one, the host wins, and it wins from outside the handler. The request is killed before or around your code, so no `catch` runs, no `finally` runs, and nothing reaches error tracking. The user gets a blank failure and the team gets silence.

This never shows up in development, which is the whole reason it ships. `next dev`, `netlify dev`, and `wrangler dev` enforce none of these caps. A 40 MB upload and a 90 second generation both work perfectly on the machine where the feature was built.

The numbers below are anchors, not gospel; plans change and they differ per host, so read the current limit for the plan this project is actually on and compare it to what the code permits.

- [ ] Upload path accepts files larger than the host's request-body cap = `[MEDIUM]`, raised to `[HIGH]` when uploading is a core flow (the product is a photo app, a document tool, a resume parser). Typical caps: Vercel serverless and edge functions about 4.5 MB and not configurable, Netlify Functions about 6 MB of base64 payload, AWS Lambda behind API Gateway about 6 to 10 MB, Cloudflare Workers about 100 MB on the free plan and higher on paid. Grep for the file crossing the function: `formData()`, `multipart/form-data`, `multer`, `busboy`, `formidable`, `req.file`, `<input type="file">`, a `supabase.storage.from(...).upload(` on a server route, an `@vercel/blob` `put(` on the server. The fix is not a bigger cap, it is not sending the bytes through the function at all. See `fixes/platform-limits.md`.
- [ ] The limit the app advertises contradicts the limit the platform enforces = `[MEDIUM]`. A dropzone labeled "up to 50MB", a Zod schema with `.max(20 * 1024 * 1024)`, or a `bodyParser: { sizeLimit: '25mb' }` on a host that stops the request at 4.5 MB is a promise the deployment cannot keep. Both numbers are readable, so the mismatch is a code finding, not a hunch.
- [ ] A route declares more runtime than its plan allows = `[MEDIUM]`. `export const maxDuration = 800` does not buy 800 seconds on a plan whose ceiling is lower; the plan clamps it and the declaration reads as coverage. Check every `maxDuration`, `vercel.json` `functions.maxDuration`, `netlify.toml` timeout, and `wrangler.toml` limits against the plan in use.
- [ ] A slow route has a paid call or a mutation sitting after the slow step = `[HIGH]`. This is the expensive shape of the timeout. The AI provider, the PDF renderer, or the video encoder was already invoked and already billed; the function is killed before the line that writes the result, decrements the credit, or marks the job done. The customer paid, the app has no record, and because a kill is not an exception there is no event anywhere to reconcile against. Streaming hides it further: the 200 and the first tokens already went out, so the client sees a truncated success rather than an error. See `fixes/platform-limits.md`.
- [ ] MANUAL CHECK NEEDED (which plan, and the largest real input). Steps: "In your host's dashboard, name the plan this project is on and open the function settings; paste the request-size and duration limits it shows. Then tell me the largest file a real user would upload and the slowest generation this app performs." Evidence: the plan name plus the two limits, and a realistic input size. Every ceiling in this cluster depends on the plan, so an unknown plan leaves these checks provisional rather than passing.
- [ ] **Scoring rule:** platform limits cannot be scored `PASS` because nothing has broken yet. Local development enforces none of them, so "it works" is evidence about a laptop. Report the comparison in both numbers and name the route: "`app/api/upload/route.ts` accepts up to 25 MB, the deploy target stops the request at 4.5 MB." Where the plan is unknown, say so and mark it provisional.

**External and AI API resilience (canonical home for 429 handling):**
- [ ] AI calls have error handling; they fail and time out often. None = `[HIGH]`. No loading feedback = `[MEDIUM]`.
- [ ] No handling of HTTP 429 (rate limited) from external APIs you depend on = `[MEDIUM]`.

**App-level caching (canonical home for cache correctness):**
- [ ] Identical DB/API/CMS queries repeated with no caching or revalidation = `[MEDIUM]`.
- [ ] Identical AI calls repeated with no caching = `[MEDIUM]`; it is also expensive.

**Cached authority data (the inverse failure: cached too long, not too little):**

Missing caching is slow. Caching the wrong thing is wrong, and it is quieter. Authority data is anything the app uses to decide what a user may do or pay: roles and permissions, subscription or entitlement status, account status (active, suspended, deleted), pricing and plan limits, inventory or remaining quota. When that data is served from a TTL cache with no event-driven invalidation, a revoked user keeps access until the TTL expires, and nothing throws. No 500, no Sentry event, no failed request: the app is confidently serving a stale answer, so monitoring cannot see it and the only signal is a customer or an auditor.

Look for authority data behind: `unstable_cache` / `"use cache"` / `cacheLife`, `fetch(..., { next: { revalidate: N } })` or `cache: "force-cache"`, route segment `export const revalidate = N`, ISR on a page that renders plan or permission state, React Query `staleTime` / `gcTime` on a session or entitlement query, a Redis/KV/Upstash `set` with `EX`/`ttl`, an in-memory `Map` populated at module scope, and `localStorage` / `sessionStorage` holding a role, plan, or feature-flag set.

- [ ] Permissions, roles, entitlements, subscription status, or account status served from a cache whose only expiry is a TTL = `[HIGH]`. The window between the revocation and the TTL is a window of unpaid or unauthorized access, and it repeats for every cached principal. Fix: invalidate on the event that changes the fact (the webhook, the admin action, the mutation), and keep the TTL only as a backstop. See `fixes/cache-invalidation.md`.
- [ ] Prices, plan limits, or inventory counts read from a cache with no invalidation on write = `[HIGH]` when the cached value is used to charge, gate, or promise. Selling at last week's price or accepting an order for stock that is gone is a money bug, not a staleness annoyance. Displaying a stale count next to a fresh authoritative check at commit time = `[LOW]`.
- [ ] The mutation path that changes authority data also clears or rewrites every cache that holds it. A Stripe webhook that updates the subscription row but never calls `revalidateTag`, `revalidatePath`, `redis.del`, or `queryClient.invalidateQueries` = `[HIGH]`; the payment succeeded and the app still behaves as if it did not. Cache keyed per user but invalidated globally, or the reverse (one global key holding per-user authority data) = `[HIGH]`, because the invalidation misses.
- [ ] Authority data cached in the browser (`localStorage`, `sessionStorage`, a persisted client store) and trusted by the client to unlock UI, with no server-side re-check on the action = `[HIGH]`. This is a stale-cache bug and an authorization bug at once; the server check is the one that matters (see Domain 3).
- [ ] Revocation has a stated bound. Whatever the design, the answer to "a user is deactivated right now, how long until they are actually locked out" must be a number the code justifies, not an unknown. No invalidation and no bound = `[HIGH]`; long-lived sessions or JWTs carrying claims that are never re-checked server-side belong here too. See `fixes/cache-invalidation.md`.
- [ ] Score it honestly. Caching cannot be `PASS` while any authority path is TTL-only. Report it as the staleness false green: name the cache, the field, and the revocation window in real units ("a suspended account keeps admin access for up to 60 minutes"), because that number is what makes the finding land.

**Account deletion and data lifecycle (only when auth and user-owned data are present):**

Signing users up is the part an AI tool gets right. Letting them leave is the part it skips, because nothing in a demo asks for it. An app with accounts and no way to delete one is not merely missing a feature: it is holding personal data it has no lawful basis to keep once the user wants out (GDPR Article 17, CCPA), and Apple rejects apps that let a user create an account but not delete it in-app (App Store guideline 5.1.1). These are code-adjacent checks; the audit flags the gaps it can see in code and leaves the legal sufficiency of any policy to a human.

- [ ] There is a self-serve account-deletion path. Grep for a delete route, handler, or action (`delete-account`, `deleteAccount`, `deleteUser`, `account/delete`, `DELETE /api/account`, a `supabase.auth.admin.deleteUser`, a Firebase `deleteUser`, a settings action that removes the account). Auth and user-owned tables present with no deletion path anywhere = `[MEDIUM]`. A "email us to delete your account" support line is not a path; it is a queue nobody drains.
- [ ] The deletion path cascades to everything the user owns. Deleting only the auth record while the user's rows (profile, posts, uploads, messages, PII in related tables) stay behind is worse than no deletion: it returns success and silently keeps the very data the user asked you to erase, and it orphans rows pointing at a user id that no longer exists. Check the schema for `ON DELETE CASCADE` / `ON DELETE SET NULL` on foreign keys to the user table, or explicit deletes of each owned table inside the handler. A delete that removes the auth user but neither cascades nor deletes the owned rows = `[HIGH]`. See `fixes/account-deletion.md`.
- [ ] A soft delete actually removes or anonymizes the PII on a schedule. A `deleted_at` / `is_deleted` / `status = 'deleted'` flag that hides the account from the UI but keeps the name, email, and content in the database forever is concealment, not erasure. It is an acceptable first step only if a scheduled hard delete or anonymization job scrubs the PII within a stated window. A soft-delete flag with no such job = `[MEDIUM]`; name the window it should honor.
- [ ] Deletion also cancels billing and cleans up external systems. When a payment provider is detected, a deletion path that never calls `subscriptions.cancel` / `customers.del` keeps billing a customer who no longer exists. When a storage SDK or an email provider is detected, deletion that leaves the user's objects in the bucket or their address on the list is a partial erasure that keeps PII in a third party. Delete path with no subscription cancel (payments detected), no storage cleanup (storage detected), or no session revocation = `[MEDIUM]`. See `fixes/account-deletion.md`.
- [ ] Score it by whether the data is gone. Deletion cannot be `PASS` while the path leaves user PII in the database or keeps a deleted user's subscription billing. Report the specific orphan: the tables with a foreign key to the user that neither cascade nor get deleted, named with their file and line, so the finding is a fix list and not a worry.

**Privacy policy honesty (only when the app collects personal data):**

An app with auth, forms, or analytics collects personal data and needs a privacy policy that is reachable and true. The audit cannot judge whether the policy is legally sufficient, but it can catch the two code-visible failures: there is no policy at all, or there is one the code contradicts.

- [ ] A privacy policy exists and is reachable. Grep for a privacy route, page, or link (`privacy`, `privacy-policy`, `PrivacyPolicy`, an href containing `privacy`). App collects PII with no privacy page anywhere = `[MEDIUM]`. Every app store, ad platform, and OAuth consent screen requires the link, so its absence also blocks distribution.
- [ ] The policy is not an unedited template. Grep the policy text for placeholder tokens: `[Company Name]`, `[Your Company]`, `[email]`, `[DATE]`, `[Website URL]`, `Last updated: [`, `example.com`, `lorem ipsum`, or a company name that is not this app's. A privacy policy still carrying template placeholders is void on its face and tells the reader nobody checked it = `[MEDIUM]`.
- [ ] The policy matches the data the code actually collects and shares. This is the honesty check and the one worth doing from code. Reconcile the third parties the policy discloses against the integrations the code ships: analytics (GA, Plausible, PostHog, Mixpanel, Segment), payments (Stripe), error tracking (Sentry), email (Resend, SendGrid, Postmark), auth and database (Supabase, Firebase, Clerk, Auth0), ad or tracking pixels. A policy that discloses none of them while the code loads several, or that states "we do not share your data with third parties" while an analytics SDK and a tracking pixel sit in the bundle, is affirmatively false = `[MEDIUM]`. Whether the wording is otherwise adequate is MANUAL CHECK NEEDED, a human or lawyer's call; this check fires only on the contradiction the code proves. See `fixes/account-deletion.md`.

---

## Domain 3: Auth & Security

Keeping the wrong people out, and the bills safe from abuse. This is the domain where AI-built apps fail hardest. Give it the most attention.

**Authentication exists:**
- [ ] User-specific features but no real auth (login, session, tokens) = `[CRITICAL]`.
- [ ] Cookie/session auth handles refresh/rotation, not just the initial login. Missing refresh flow = `[HIGH]`.

**Authorization, user A cannot access user B's data:**
- [ ] Endpoints returning user-owned data verify the current user owns the requested resource, not just that someone is logged in. No ownership check = `[CRITICAL]`. See `fixes/auth-ownership.md`.
- [ ] MANUAL CHECK NEEDED. Steps: "Log in as User A. In a request URL or API call, change an ID to one that belongs to User B." Evidence: paste the response. If you can see or edit User B's data, that is critical.

**Supabase row-level security (if Supabase):**

Key names: Supabase is replacing the legacy `anon` and `service_role` keys (JWTs starting `eyJ`) with publishable keys (`sb_publishable_...`) and secret keys (`sb_secret_...`), and deprecates the legacy pair by the end of 2026. Wherever this checklist says anon key, the same holds for a publishable key; wherever it says `service_role`, the same holds for a secret key.

- [ ] The single most common critical bug in vibe-coded apps. Every table with user or private data must have RLS enabled AND have policies. RLS enabled with no policy = locked out; RLS disabled = wide open to anyone with the anon key, as far as the table's grants reach. Any user-data table with RLS off = `[CRITICAL]`. See `fixes/supabase-rls.md`.
- [ ] Grants decide whether `anon` and `authenticated` can reach a table at all. Supabase stopped granting new `public` tables to them automatically (new projects from 2026-05-30, new tables on every project from 2026-10-30); older tables keep the grants. From code alone, assume the grants exist and score RLS off as above. Lower it to `[MEDIUM]` only when the grants query in `fixes/supabase-rls.md` (Step 1) shows neither role can reach the table: unreachable today, one grant away from wide open. A migration that grants a table to `anon` or `authenticated`, or runs `alter default privileges ... grant ... to anon`, on a table without `enable row level security` = `[CRITICAL]`.
- [ ] The anon key (or publishable key) is designed to be public and WILL appear in the frontend. That is fine on its own, and is only safe when RLS is on. Do not flag the anon key as a leak; flag missing RLS as the real problem. Flagging the anon key while RLS is off and calling it handled is wrong.
- [ ] The `service_role` key, or a secret key (`sb_secret_...`), must never appear in client-side or public code = `[CRITICAL]`. A secret key returns 401 when a browser sends it; that is not protection, because from curl or a script it still works and bypasses RLS.

**Service-role paths bypass RLS (the RLS false green):**

RLS enabled on every table is not the whole answer. A server route that queries with the `service_role` client bypasses every policy on every table, by design. The wall is still up; that code walks around it. Grep the server side for `service_role`, `SUPABASE_SERVICE_ROLE_KEY`, `sb_secret_`, `SUPABASE_SECRET_KEY`, `createClient(..., serviceKey)`, and any shared admin client (`supabaseAdmin`, `serverClient`) and trace what each one reads or writes.

- [ ] Every server path that uses the service-role client and touches user-owned data does its own ownership check: the user id comes from the verified session (`supabase.auth.getUser()` on the server, or a validated JWT), never from a request body, query param, or header the caller controls. Service-role query filtered by a caller-supplied id with no session check = `[CRITICAL]`. See `fixes/supabase-rls.md`.
- [ ] Reaching for the service-role client to make a query work is a finding, not a fix. A route using service-role for reads that an ordinary authenticated client could do under RLS = `[HIGH]`; it removes the safety net for no gain. The legitimate uses are narrow: cross-user admin work, background jobs with no user session, webhook handlers.
- [ ] Score RLS accordingly. Any data path that reaches user data through service-role code without its own ownership check keeps the RLS check off `PASS`, however clean `pg_tables` looks. Report it as the RLS false green, name the file and route, and treat the tables reachable that way as unprotected on that path.

**Firebase Security Rules (if Firebase):**
- [ ] The Firebase config object (apiKey, projectId, etc.) is public by design and belongs in the frontend. Do not flag it as a secret leak; security comes from Rules, not from hiding the config.
- [ ] Check `firestore.rules` / database rules. Test/open mode (`allow read, write: if true;` or a global open expiry) = `[CRITICAL]`. No rules file tracked in the repo = `[HIGH]`. See `fixes/firebase-rules.md`.

**Admin protection:**
- [ ] Admin pages enforce auth at middleware/layout level, not a hidden URL. Reachable by guessing the path = `[CRITICAL]`.
- [ ] Admin/privileged endpoints verify the caller's role server-side. Missing = `[CRITICAL]`.

**Secret exposure:**
- [ ] Any admin token, service key, database URL, or third-party secret behind a public env prefix (`NEXT_PUBLIC_`, `VITE_`, `PUBLIC_`, `EXPO_PUBLIC_`, `REACT_APP_`) = `[CRITICAL]`. SvelteKit note: anything under `PUBLIC_` (read via `$env/static/public`) ships to the browser; secrets must use a non-public name via `$env/static/private`. Exceptions: the Supabase anon or publishable key and the Firebase config are meant to be public.
- [ ] Hardcoded secrets in client code = `[CRITICAL]`.
- [ ] MANUAL CHECK NEEDED (secret-in-bundle test). Searching the bundle for `service_role` finds nothing even when the key is there: the build replaces `import.meta.env.X` or `process.env.NEXT_PUBLIC_X` with the value, so the variable name never reaches the bundle, and a Supabase key is a JWT (`eyJ...`) whose role sits base64-encoded inside it. Decode instead of searching: run the deployed-bundle probe in `evidence-interview.md` against the production URL. It reads the role inside every JWT the page's scripts carry and flags secret-key prefixes (`sb_secret_`, `sk_live_`, `rk_live_`, `sk-proj-`, `sk-ant-`, `AKIA`, private keys), printing names, never values. Evidence: its output. `role=service_role` or any secret prefix = `[CRITICAL]`. Test the deployed site, not a local build: a local build inlines your local `.env` files, not the variables set on the host, so it can show a leak but cannot rule one out. (The Supabase anon or publishable key and the Firebase config are expected.)

**Cookie configuration:**
- [ ] Auth cookies: `httpOnly` true (missing = `[HIGH]`), `secure` true in production (missing = `[HIGH]`), `sameSite` lax/strict (missing = `[MEDIUM]`).

**Dependencies and git hygiene:**
- [ ] Run `npm audit` (or `pnpm audit`/`pip-audit`). Critical vulns = `[HIGH]`, high vulns = `[MEDIUM]`.
- [ ] `.env*` missing from `.gitignore` = `[CRITICAL]`. `.env` ever committed = `[HIGH]`, and the secrets must be rotated, not just deleted.
- [ ] Hardcoded `http://` URLs in production config = `[MEDIUM]`.

**Secrets in git history (canonical home for the history scan):**
- [ ] The working tree is not the whole repo. A key pasted into `lib/stripe.ts`, committed, then moved to an env var in the next commit is gone from every grep of the current files and still sitting in the history, readable by anyone who can clone. `.gitignore` was added after the fact, the file was deleted, the commit was amended: none of that removes the blob. Scan history, not just the checkout.
- [ ] Scan with a real scanner when one is available, since it catches formats a hand-written grep will not:
  ```bash
  gitleaks detect --source . --redact          # scans full history by default
  trufflehog git file://. --results=verified   # verified means the key still works
  ```
- [ ] No scanner installed? Do not skip the check, run the targeted version. Search every reachable commit for the high-signal prefixes:
  ```bash
  git grep -nEI "sk_live_|sk-[A-Za-z0-9_-]{20,}|rk_live_|sb_secret_|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20}|github_pat_|AIza[0-9A-Za-z_-]{20}|xox[baprs]-|service_role|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|postgres(ql)?://[^:]+:[^@]+@" $(git rev-list --all) 2>/dev/null | head -50
  git log --all --diff-filter=D --name-only -- '*.env' '*.env.*' '*.pem' '*.p12' '*-key.json' | head -50
  ```
  On a long history, bound it (`$(git rev-list --all -n 500)`) and say in the report that the scan was bounded, so a clean result is not read as a full-history clean bill.
- [ ] Any live credential reachable in history = `[HIGH]`, raised to `[CRITICAL]` when the remote is public (`git remote -v`, then check the repo's visibility) or when the repo was ever public, or when the credential is a service-role key, cloud provider key, or database URL with a password. A public repo means assume harvested: bots scan new commits within minutes, and the clock started at the commit date, not at discovery.
- [ ] The second command above catches the deleted-file case: an `.env`, `.pem`, or service-account JSON that exists in no current directory but is intact in the commit that removed it.
- [ ] MANUAL CHECK NEEDED (is the found credential still valid). Steps: "For each key the scan found, open the provider dashboard and check whether that key still exists and when it was last used. Tell me the key's name and its created/last-used dates, never the value." A key that was rotated after the leaking commit is a closed finding; one that is still active is open regardless of how old the commit is.
- [ ] The remedy is rotation, not history rewriting. Report it that way. `git filter-repo` or BFG changes what a fresh clone sees; it does not reach the clones, forks, CI caches, and provider-side cached views that already have the blob. Rewriting first and rotating later, or never, is the common and wrong order. See `fixes/git-history-secrets.md`.
- [ ] Scoring rule for git hygiene: it cannot be scored `PASS` while a credential is reachable in history and has not been rotated, however clean the current tree is. A clean working tree with an unrotated key three commits back is a false green, and it is the exact shape this audit exists to catch.

**Security headers:**
- [ ] Where headers are set depends on the stack: Next.js `headers()` in config; SvelteKit `handle` hook plus the built-in `kit.csp` in `svelte.config.js`; TanStack Start server middleware or host config; Astro/Netlify/Cloudflare `public/_headers`; Vite SPA at the host/CDN. Missing CSP = `[HIGH]`, HSTS = `[HIGH]`, X-Frame-Options = `[MEDIUM]`, X-Content-Type-Options = `[MEDIUM]`. See `fixes/security-headers.md`.

**Rate limiting (canonical home):**
- [ ] No rate limit on endpoints calling paid APIs (OpenAI, Anthropic, Stripe, SMS, email) = `[HIGH]`; one abusive user runs up a real bill.
- [ ] No rate limit on auth endpoints (login, register, password reset) = `[HIGH]`; credential stuffing and spam.
- [ ] No rate limiting anywhere = `[HIGH]`. See `fixes/rate-limiting.md`.

---

## Domain 4: Infrastructure & Deployment

Shipping it, rolling it back, and serving it fast. (Rollback lives here, not in CI/CD.)

**Environment separation:**
- [ ] Only one environment, no way to test before production = `[HIGH]`.
- [ ] Production env vars pointing at localhost = `[HIGH]`.
- [ ] Hardcoded production URLs/config in source instead of env = `[MEDIUM]`.

**Preview deploys:**
- [ ] No preview/branch deploys = `[MEDIUM]`. (Vercel/Netlify/Cloudflare give these free; self-hosted usually does not.)

**Rollback (canonical home):**
- [ ] Self-hosted/Docker with no previous image retained = `[HIGH]`. Vercel/Netlify/Cloudflare have instant rollback built in = PASS.
- [ ] No documented or built-in way to roll back a bad deploy = `[HIGH]`.

**Health check (canonical home for the endpoint itself; monitoring of it is Domain 5):**
- [ ] Self-hosted/Docker with no health check endpoint = `[HIGH]`. No `HEALTHCHECK` in the Dockerfile = `[MEDIUM]`.
- [ ] Health endpoint that checks nothing = `[MEDIUM]`. A handler whose whole body is `return new Response("ok")`, `res.send("ok")`, `res.json({ status: "ok" })`, or `return { ok: true }` proves only that the process is running and can serve a route. It cannot see a dead database, an expired third-party key, or a queue that stopped draining, so it returns 200 through the outages people actually have. Raise to `[HIGH]` when it is the only signal wired to a monitor, because it is then an active false green. Fix: touch the dependencies the app cannot work without (one cheap DB query, one check per critical external service) and return a non-2xx when one is down. See `fixes/uptime-monitoring.md`.
- [ ] Health endpoint that returns 200 with a failing body = `[HIGH]`. A handler that catches its own dependency errors and still responds 200 with `{ status: "degraded" }` or `{ db: false }` is invisible to every monitor, because monitors read the status code. The status code has to carry the failure.

**Version control and CI:**
- [ ] No `.git` directory at all = `[CRITICAL]`; no undo, no history, no recovery.
- [ ] MANUAL CHECK NEEDED. Steps: "Confirm the main branch has protection rules in your Git host settings." Evidence: screenshot of the branch protection page.
- [ ] No CI config at all = `[HIGH]`. CI that only deploys with no lint/typecheck/test = `[MEDIUM]`.

**CDN and edge (static-asset caching lives here):**
- [ ] Self-hosted with no CDN in front of static assets = `[MEDIUM]`. Vercel/Netlify/Cloudflare = PASS.

**Survives load:**
- [ ] A database connection limit that real traffic will exceed = `[HIGH]` (fix via pooling, see Domain 2).
- [ ] Expecting 10+ concurrent users on serverless + direct DB with no pooling = `[HIGH]`.
- [ ] The plan's own ceilings (request body size, function duration) are a Domain 2 finding, scored under Platform limits there. Note the plan here, because that is what decides the numbers, and audit the mismatch against the code in Domain 2.

---

## Domain 5: Operations & Recovery

Knowing when it breaks, and surviving when it does.

**Error tracking and logs:**
- [ ] No error tracking SDK (Sentry, Highlight, LogRocket). You find out it broke when a user leaves = `[HIGH]`. See `fixes/error-tracking.md`.
- [ ] Installed but inert: the SDK is present but wired so it never fires. A false green here is worse than no tracking, because it buys confidence it has not earned. Flag any of these at `[HIGH]`: DSN is empty, a placeholder, or hardcoded to a dummy value; DSN reads from an env var with no evidence it is set (not in `.env.example`, not referenced in deploy config); `init` is gated behind a prod-only condition (`if (import.meta.env.PROD)`, `NODE_ENV === 'production'`, `enabled: false`) with no confirmation the prod env actually carries the DSN; `sampleRate: 0` or a `beforeSend` that returns `null` unconditionally. See `fixes/error-tracking.md`.
- [ ] Tracking on client only or server only, not both = `[MEDIUM]`.
- [ ] No global error handler (`error.tsx`/`global-error.tsx`/framework equivalent) = `[HIGH]`.
- [ ] Only `console.log`, no structured logging = `[LOW]`. No logging at all = `[MEDIUM]`.
- [ ] MANUAL CHECK NEEDED (error tracking actually fires). Steps: "Trigger a test error on your live deployment (not localhost) and confirm it appears in your tracker's dashboard within a minute." Evidence: paste the issue title that showed up, or say nothing arrived. Installed but silent counts as no tracking.

**Monitoring and alerting:**
- [ ] No uptime monitoring = `[MEDIUM]`.
- [ ] Monitoring that only runs inside the thing it watches = `[MEDIUM]`. A self-hosted checker in the same `docker-compose.yml`, a cron job on the same box, or a scheduled function in the same project asks the server whether it feels okay. When the host, the region, the DNS record, the TLS certificate, or the deploy itself is what broke, that checker is down too and reports nothing, which reads as silence rather than as an outage. At least one check has to originate outside your infrastructure. See `fixes/uptime-monitoring.md`.
- [ ] Monitor pointed somewhere that is not production = `[MEDIUM]`. A monitor config in the repo whose target is `localhost`, a preview URL, or a staging host is watching a thing no user visits. Same for a check that hits the health route on the origin while users reach the app through a CDN or proxy, since it skips the layer that usually fails.
- [ ] MANUAL CHECK NEEDED (the monitor is real and outside-in). Steps: "Open your uptime monitor (UptimeRobot, Better Stack, Cronitor, or your host's). Paste the URL it checks, the interval, and the timestamp of its most recent successful check." Evidence: those three values. A monitor that exists but was paused, or whose last check is weeks old, is inert and scores the same as no monitoring. Reported without artifacts, record as `reported by user, unverified`, never `PASS`.
- [ ] MANUAL CHECK NEEDED (synthetic pass through the critical path). Steps: "Name the one flow that has to work for this app to be worth running (signup, login, checkout, the core generate/upload action). Then say what routinely exercises it end to end against production, on a schedule, and when it last ran." Evidence: the scheduled synthetic check, the E2E suite that runs against prod, or the honest answer that nothing does. A 200 from the homepage says nothing about whether signup still writes a row or checkout still charges a card. Uptime green while the critical path is broken is the expensive version of this gap, because the dashboard is the reason nobody looked. See `fixes/uptime-monitoring.md`.
- [ ] MANUAL CHECK NEEDED. Steps: "Confirm error/uptime alerts actually reach you (email, Slack, SMS)." Evidence: a screenshot of a test alert. Tracking with no alerting is a dashboard nobody looks at.

**Scoring rule for monitoring:** uptime monitoring cannot be scored `PASS` while the only evidence is a health endpoint that returns a static 200, a checker that lives inside the deployment it watches, or a monitor the user says exists but cannot show a recent check for. Presence of a monitoring account is not coverage; a check that runs from outside and fails when the app is broken is.

**Backups and recovery:**
- [ ] No automated database backups = `[HIGH]`. Managed does not mean backed up: it depends on the plan. Supabase Free has no automatic backups (Pro keeps 7 days, Team 14, Enterprise up to 30). Self-hosted DB with no backup job = `[HIGH]`.
- [ ] Uploaded files are not in the database backup. Supabase backups leave out Storage objects on every plan; the database holds only their metadata. User files that matter (uploads, documents, avatars a user cannot re-create) with no separate copy = `[MEDIUM]`.
- [ ] Backups never restore-tested = `[MEDIUM]`. A backup you have never restored is a guess.
- [ ] No incident runbook = `[LOW]` solo, `[MEDIUM]` if a team or client depends on it.
- [ ] MANUAL CHECK NEEDED. Steps: "Confirm your domain registrar has 2FA and a recovery email you control." Losing the domain loses everything.
- [ ] MANUAL CHECK NEEDED. Steps: "Could you rebuild this from scratch in under an hour? Code in git, env vars in a password manager, database restorable from backup, deploy steps written down." Evidence: name which of the four is missing. Any "no" is your real single point of failure.
