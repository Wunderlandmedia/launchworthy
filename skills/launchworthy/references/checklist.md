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

**Webhooks (canonical home; payment and provider callbacks):**

The dangerous property of a webhook is that the caller believes your status code. Return 200 and the provider marks the event delivered and never retries; your dashboards stay green while the work never happened.

- [ ] Webhook endpoints verify the provider signature before processing (Stripe `constructEvent` with the signing secret, svix headers, `x-hub-signature-256`). Missing = `[HIGH]`; if the handler grants access, records a payment, or changes entitlements from the event, a forgeable webhook = `[CRITICAL]`, because anyone who finds the URL can mint the event. See `fixes/webhooks.md`.
- [ ] The handler returns 2xx only after the work succeeded. A catch block that swallows the error and returns 200 anyway is the classic silent revenue failure: the provider sees a successful delivery and moves on, error tracking sees nothing because nothing threw. Swallowed catch returning 2xx = `[HIGH]`. On failure, log to the error tracker and return 5xx so the provider retries. See `fixes/webhooks.md`.
- [ ] Handlers that fulfill, charge, or grant are idempotent. Providers deliver at least once and retry on timeouts, so the same event can arrive twice. No dedup by event id = `[MEDIUM]`.
- [ ] Fast-ack rule: events the app deliberately ignores get an immediate 200 with no work, so retries of irrelevant events do not pile up. Heavy fulfillment inside the webhook request risks the provider's timeout; hand off to a background job for slow work (see Background jobs). Advisory unless timeouts are plausible, then `[MEDIUM]`.
- [ ] MANUAL CHECK NEEDED. Steps: "Open the provider's webhook dashboard (Stripe: Developers > Webhooks > your endpoint) and look at the recent deliveries." Evidence: paste the success/failure counts for the last week and the latest failure's status code, if any. Note: a wall of 200s proves delivery, not that the work happened; the swallowed-catch check above is why this stays code-first.

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
- [ ] Operations that can exceed platform limits (Vercel 10s hobby / 60s pro, Netlify 10s, Workers CPU limits) with no awareness = `[MEDIUM]`.

**External and AI API resilience (canonical home for 429 handling):**
- [ ] AI calls have error handling; they fail and time out often. None = `[HIGH]`. No loading feedback = `[MEDIUM]`.
- [ ] No handling of HTTP 429 (rate limited) from external APIs you depend on = `[MEDIUM]`.

**App-level caching:**
- [ ] Identical DB/API/CMS queries repeated with no caching or revalidation = `[MEDIUM]`.
- [ ] Identical AI calls repeated with no caching = `[MEDIUM]`; it is also expensive.

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
- [ ] The single most common critical bug in vibe-coded apps. Every table with user or private data must have RLS enabled AND have policies. RLS enabled with no policy = locked out; RLS disabled = wide open to anyone with the anon key. Any user-data table with RLS off = `[CRITICAL]`. See `fixes/supabase-rls.md`.
- [ ] The anon key is designed to be public and WILL appear in the frontend. That is fine on its own, and is only safe when RLS is on. Do not flag the anon key as a leak; flag missing RLS as the real problem. Flagging the anon key while RLS is off and calling it handled is wrong.
- [ ] The `service_role` key must never appear in client-side or public code = `[CRITICAL]`.

**Service-role paths bypass RLS (the RLS false green):**

RLS enabled on every table is not the whole answer. A server route that queries with the `service_role` client bypasses every policy on every table, by design. The wall is still up; that code walks around it. Grep the server side for `service_role`, `SUPABASE_SERVICE_ROLE_KEY`, `createClient(..., serviceKey)`, and any shared admin client (`supabaseAdmin`, `serverClient`) and trace what each one reads or writes.

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
- [ ] Any admin token, service key, database URL, or third-party secret behind a public env prefix (`NEXT_PUBLIC_`, `VITE_`, `PUBLIC_`, `EXPO_PUBLIC_`, `REACT_APP_`) = `[CRITICAL]`. SvelteKit note: anything under `PUBLIC_` (read via `$env/static/public`) ships to the browser; secrets must use a non-public name via `$env/static/private`. Exceptions: Supabase anon key and Firebase config are meant to be public.
- [ ] Hardcoded secrets in client code = `[CRITICAL]`.
- [ ] MANUAL CHECK NEEDED (secret-in-bundle test). Steps: "Build the app, open it in a browser, DevTools > Sources, search bundled JS for: key, secret, token, password, apikey, service_role." Evidence: screenshot or paste hits. A real backend secret in the frontend is critical. (Supabase anon key and Firebase config are expected.)

**Cookie configuration:**
- [ ] Auth cookies: `httpOnly` true (missing = `[HIGH]`), `secure` true in production (missing = `[HIGH]`), `sameSite` lax/strict (missing = `[MEDIUM]`).

**Dependencies and git hygiene:**
- [ ] Run `npm audit` (or `pnpm audit`/`pip-audit`). Critical vulns = `[HIGH]`, high vulns = `[MEDIUM]`.
- [ ] `.env*` missing from `.gitignore` = `[CRITICAL]`. `.env` ever committed = `[HIGH]`, and the secrets must be rotated, not just deleted.
- [ ] Hardcoded `http://` URLs in production config = `[MEDIUM]`.

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
- [ ] No automated database backups = `[HIGH]`. (Supabase/PlanetScale/Neon have them; confirm they are on and check retention. Self-hosted DB with no backup job = `[HIGH]`.)
- [ ] Backups never restore-tested = `[MEDIUM]`. A backup you have never restored is a guess.
- [ ] No incident runbook = `[LOW]` solo, `[MEDIUM]` if a team or client depends on it.
- [ ] MANUAL CHECK NEEDED. Steps: "Confirm your domain registrar has 2FA and a recovery email you control." Losing the domain loses everything.
- [ ] MANUAL CHECK NEEDED. Steps: "Could you rebuild this from scratch in under an hour? Code in git, env vars in a password manager, database restorable from backup, deploy steps written down." Evidence: name which of the four is missing. Any "no" is your real single point of failure.
