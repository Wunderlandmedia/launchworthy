# Fix: Error Tracking

Without error tracking you learn about bugs when a user gives up and leaves, if they bother to tell you at all. You need three things: a tracker that captures both client and server errors, a global handler so nothing escapes silently, and alerting that actually reaches you. A dashboard nobody looks at is not monitoring.

## Default: Sentry

Free tier is enough to start. The wizard sets up most of it.

```bash
npx @sentry/wizard@latest -i nextjs   # or: react, sveltekit, remix, node
```

That creates the client, server, and edge configs and wires up source maps. The key point the wizard cannot decide for you: **capture both sides**. A client-only setup misses API and database errors; a server-only setup misses the white screens your users actually see.

## Global error handlers (so nothing escapes)

**Next.js App Router** needs both files:

```tsx
// app/error.tsx  (catches errors in a route segment)
"use client"
export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div>
      <h2>Something went wrong</h2>
      <button onClick={reset}>Try again</button>
    </div>
  )
}
```

```tsx
// app/global-error.tsx  (catches errors in the root layout)
"use client"
export default function GlobalError({ error }: { error: Error }) {
  return (
    <html><body><h2>Something went wrong</h2></body></html>
  )
}
```

Sentry's Next.js SDK reports errors from these automatically once installed.

**Vite / React SPA:** wrap the app in an error boundary:

```tsx
import * as Sentry from "@sentry/react"

<Sentry.ErrorBoundary fallback={<p>Something went wrong.</p>}>
  <App />
</Sentry.ErrorBoundary>
```

**SvelteKit:** install `@sentry/sveltekit` and wrap the `handleError` hooks on both sides. This is the one global catch point in SvelteKit, so it is where logging belongs:

```ts
// src/hooks.server.ts
import { handleErrorWithSentry } from "@sentry/sveltekit"
export const handleError = handleErrorWithSentry(({ error, event }) => {
  return { message: "Something went wrong" }   // safe message shown to the user
})
```

```ts
// src/hooks.client.ts  (same pattern for client-side errors)
import { handleErrorWithSentry } from "@sentry/sveltekit"
export const handleError = handleErrorWithSentry()
```

Keep your `+error.svelte` pages for the UI; the hook is what reports the error.

**TanStack Start:** use `@sentry/react` for the client, capture exceptions inside `createServerFn` handlers (wrap the body in try/catch and `Sentry.captureException`), and make sure the router has a `defaultErrorComponent` so nothing renders a blank screen. The router error component shows the UI; the server-function catch and the SDK do the reporting.

**Node/Express:** add an error-handling middleware last, and capture unhandled rejections:

```ts
process.on("unhandledRejection", (err) => Sentry.captureException(err))
app.use((err, req, res, next) => {
  Sentry.captureException(err)
  res.status(500).json({ error: "Internal server error" })
})
```

## Alerting (the part people skip)

Tracking with no alert is a diary. In Sentry, set an alert rule: notify on a new issue, or when an issue crosses N events in an hour, delivered to email or Slack. Then trigger a test error and confirm the alert actually arrives. That confirmation is the evidence the audit asks for.

## Common silent failures (installed but inert)

The trap is not forgetting to install Sentry. It is installing it, seeing the wizard finish, and shipping something that never sends a single event. It looks done and reports nothing, which is worse than an empty dashboard because you trust it. Check for all of these:

- **Empty or placeholder DSN.** `dsn: ""`, `dsn: "YOUR_DSN_HERE"`, or a DSN left as the example value. Sentry silently no-ops with a falsy DSN; it does not throw.
- **DSN from an env var nobody set.** `dsn: process.env.SENTRY_DSN` is correct only if that var exists in the deployed environment. If it is absent from `.env.example` and unmentioned in your host's env config, it is almost certainly unset in production, and init runs with an empty DSN.
- **Gated behind a prod-only condition.** `if (import.meta.env.PROD) Sentry.init(...)` or `enabled: process.env.NODE_ENV === 'production'` means tracking only exists in prod. Fine in principle, but now the DSN env var must be set specifically in prod, which is exactly where people forget it. You test in dev where init never runs, then ship to prod where the DSN is missing.
- **Sampling or filtering set to zero.** `sampleRate: 0`, or a `beforeSend` that returns `null` unconditionally, drops every event before it leaves the browser.

Confirming the DSN is present is not enough; the only proof is a test error that actually lands (below).

## Add uptime monitoring

Separate from error tracking: a free uptime monitor (UptimeRobot, Better Stack, or the one your host provides) that pings your health check URL every few minutes and pages you when the whole site is down, which error tracking cannot tell you because a dead server reports nothing.

## Verify

- Confirm both client and server configs exist, not just one.
- Confirm `error.tsx` and `global-error.tsx` (or the framework equivalent) exist.
- Confirm the DSN is real, not empty or a placeholder, and that whatever env var it reads from is actually set in the deployed environment (not just locally). Check init is not gated behind a prod-only condition whose env var nobody set.
- Throw a test error against the deployed app, not localhost, confirm it lands in Sentry, and confirm the alert reaches your inbox or Slack. Paste that into the audit as evidence. A tracker with the SDK present but no test event landing is inert, and scores the same as no tracking.
