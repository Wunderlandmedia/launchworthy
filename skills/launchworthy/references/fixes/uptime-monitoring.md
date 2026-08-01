# Fix: Uptime Monitoring and Synthetic Checks

Error tracking tells you a request failed. It cannot tell you the site is gone, because a dead process, an expired certificate, or a DNS record pointing at nothing sends no events at all. Uptime monitoring covers that blind spot, but only if it satisfies two conditions people usually miss:

1. **The check runs from outside your infrastructure.** A checker inside the deployment goes down with it.
2. **The check touches what the app actually needs.** An endpoint that returns 200 no matter what is a green light wired to nothing.

A monitoring setup that fails either one produces confident green during a real outage, which is worse than having none, because the dashboard is the reason nobody looked.

## Step 1: Make the health endpoint tell the truth

The endpoint the monitor pings has to fail when the app is unusable. That means touching the dependencies the app cannot work without: the database, and any external service the core flow requires. Keep it cheap (it runs every minute) and keep it honest (the status code carries the verdict).

**Next.js App Router**

```ts
// app/api/health/route.ts
import { NextResponse } from "next/server"
import { createClient } from "@supabase/supabase-js"

export const dynamic = "force-dynamic"   // never let this be cached or prerendered

export async function GET() {
  const checks: Record<string, boolean> = {}

  try {
    const supabase = createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.SUPABASE_SERVICE_ROLE_KEY!
    )
    // cheapest possible round trip that proves the DB answers
    const { error } = await supabase.from("health_probe").select("id").limit(1)
    checks.database = !error
  } catch {
    checks.database = false
  }

  const healthy = Object.values(checks).every(Boolean)
  return NextResponse.json(
    { status: healthy ? "ok" : "degraded", checks },
    { status: healthy ? 200 : 503 }
  )
}
```

**Express / Node**

```ts
app.get("/health", async (req, res) => {
  try {
    await db.query("SELECT 1")
    res.status(200).json({ status: "ok" })
  } catch {
    res.status(503).json({ status: "degraded", checks: { database: false } })
  }
})
```

Three rules for whatever stack you are on:

- **Return a non-2xx when a dependency is down.** 503 is the right code. Monitors read the status code and nothing else; a 200 body that says `{ db: false }` is invisible.
- **Keep it out of the cache.** A health route served from a CDN or prerendered at build time reports the state of the build, not the state of the app. Mark it dynamic and send `Cache-Control: no-store`.
- **Do not put secrets or a full diagnostic dump in the body.** The endpoint is public. Names of the checks and booleans, nothing more. If you must expose detail, gate it behind a header token.

Do not check things the app can survive without. If a broken analytics provider makes `/health` return 503, you have built a pager that fires for nothing, and pages that fire for nothing get muted.

## Step 2: Put an external monitor in front of it

Free tiers are enough: UptimeRobot, Better Stack, Cronitor, Pingdom, or whatever your host offers (Vercel, Fly, Render all have one). What matters is that the check originates on someone else's network.

Configure:

- **URL:** the production URL users actually type, through the CDN or proxy they actually hit. Not the origin, not a preview deploy, not `localhost`.
- **Interval:** every 1 to 5 minutes.
- **Alerting:** email, Slack, or SMS to a human. A monitor with no notification channel is a chart.
- **Confirmation window:** alert after 2 consecutive failures so a single blip does not page you, but not so many that a 20 minute outage stays quiet.
- **Certificate expiry:** turn it on if offered. An expired TLS certificate takes the whole site down and gives no warning otherwise.

Then verify by breaking it on purpose: stop the database (or point the health check at a dependency you shut off) and confirm the monitor goes red and the alert reaches you. An untested monitor is an assumption.

## Step 3: Add a synthetic pass through the critical path

Uptime is the floor, not the goal. The homepage can return 200 for weeks while signup throws on the insert, checkout stops charging, or the core action returns an empty result. Every one of those is invisible to a ping.

Pick the one flow that has to work for the app to be worth running, and run it end to end against production on a schedule.

**Option A: an E2E test scheduled against production.** If Playwright is already in the repo, this is nearly free:

```ts
// e2e/critical-path.spec.ts
import { test, expect } from "@playwright/test"

test("signup writes a real account", async ({ page }) => {
  const email = `synthetic+${Date.now()}@yourdomain.com`
  await page.goto(process.env.PROD_URL!)
  await page.getByRole("link", { name: "Sign up" }).click()
  await page.getByLabel("Email").fill(email)
  await page.getByLabel("Password").fill(process.env.SYNTHETIC_PASSWORD!)
  await page.getByRole("button", { name: "Create account" }).click()
  await expect(page.getByText("Welcome")).toBeVisible({ timeout: 15_000 })
})
```

Run it from CI on a cron schedule (GitHub Actions `schedule:`), not only on push, and make a failure notify you the same way an outage does.

**Option B: a scripted transaction in the monitor.** Better Stack, Checkly, and Datadog can run a multi-step browser or API check on a schedule with no CI involved. Same idea, less to maintain.

**Option C: a deep check endpoint.** If a browser test is too much, add an authenticated `/api/health/deep` that performs the real write path against a dedicated test account and rolls it back, then point a monitor at it. Weaker than a browser pass (it skips the frontend) but far stronger than a ping.

Whichever you pick, handle the data it creates: use a dedicated synthetic account, prefix the records so they are identifiable, and clean them up or exclude them from analytics and billing. A synthetic check that pollutes your metrics gets deleted within a month.

## What not to do

- **Do not monitor from inside the deployment.** A cron job on the same box, a container in the same compose file, or a scheduled function in the same project cannot report the outage that took it down too.
- **Do not point the monitor at a route that skips the stack.** A static page served entirely by the CDN returns 200 while every server route is failing.
- **Do not let the health endpoint return 200 for a degraded state.** Either it is serving users or it is not.
- **Do not treat "the monitoring dashboard is green" as "the product works."** Green means a URL answered. Step 3 is the part that knows whether anyone can actually sign up.
- **Do not skip the alert channel.** Most people who discover an outage from a customer email had a monitor that caught it 40 minutes earlier and told nobody.

## Verify

- Confirm the health endpoint fails, with a non-2xx status, when a required dependency is unavailable. Break it once and watch.
- Confirm the monitor's target URL is the production host users reach, and that its most recent check is minutes old, not weeks.
- Confirm the alert arrives at a channel a human reads, by triggering it deliberately rather than assuming.
- Confirm something exercises the critical path end to end on a schedule, and name when it last ran. If the answer is "nothing does," the uptime check is a floor and the critical path is still unmonitored.
