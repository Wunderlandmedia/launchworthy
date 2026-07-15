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

The engine: how data moves, gets stored, and holds up under load. (Connection pooling, background jobs, and external-API resilience live here, not in Infrastructure.)

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

**Health check:**
- [ ] Self-hosted/Docker with no health check endpoint = `[HIGH]`. No `HEALTHCHECK` in the Dockerfile = `[MEDIUM]`.

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
- [ ] MANUAL CHECK NEEDED. Steps: "Confirm error/uptime alerts actually reach you (email, Slack, SMS)." Evidence: a screenshot of a test alert. Tracking with no alerting is a dashboard nobody looks at.

**Backups and recovery:**
- [ ] No automated database backups = `[HIGH]`. (Supabase/PlanetScale/Neon have them; confirm they are on and check retention. Self-hosted DB with no backup job = `[HIGH]`.)
- [ ] Backups never restore-tested = `[MEDIUM]`. A backup you have never restored is a guess.
- [ ] No incident runbook = `[LOW]` solo, `[MEDIUM]` if a team or client depends on it.
- [ ] MANUAL CHECK NEEDED. Steps: "Confirm your domain registrar has 2FA and a recovery email you control." Losing the domain loses everything.
- [ ] MANUAL CHECK NEEDED. Steps: "Could you rebuild this from scratch in under an hour? Code in git, env vars in a password manager, database restorable from backup, deploy steps written down." Evidence: name which of the four is missing. Any "no" is your real single point of failure.
