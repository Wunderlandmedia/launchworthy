# Production Hardening Audit: taskflow

Date: 2026-07-01
Stack: Vite + React + Supabase, hosted on Vercel
Status: pre-launch (about to share with first users)

This is a real-shaped example of what the skill produces on a typical app built with Lovable. Names and paths are illustrative.

## Scorecard

| # | Domain | Score | Findings |
|---|---|---|---|
| 1 | Frontend & Experience | WARN | 0 critical, 1 high, 2 medium, 1 low |
| 2 | Backend & Data | WARN | 0 critical, 1 high, 1 medium, 0 low |
| 3 | Auth & Security | FAIL | 2 critical, 2 high, 0 medium, 0 low |
| 4 | Infrastructure & Deployment | WARN | 0 critical, 1 high, 1 medium, 0 low |
| 5 | Operations & Recovery | FAIL | 0 critical, 3 high, 1 medium, 0 low |

**Overall: 0/5 domains passing. 2 critical, 8 high, 5 medium, 1 low.**

The app works and looks finished. It is also one changed URL away from leaking every user's tasks, and you would not find out because nothing is being tracked. Two hours of fixes moves this from "do not launch" to "safe to launch."

## Fix Now

1. **[CRITICAL] Supabase RLS is off on `tasks` and `profiles`.** Anyone who loads the site can read the anon key from the network tab and then read and write every user's rows. This is the whole ballgame. `supabase/migrations/` has no `enable row level security` anywhere. Fix with the `supabase-rls.md` playbook: enable RLS and add ownership policies keyed on `user_id`. Do the policy and the enable in one migration so you do not lock yourself out.
2. **[CRITICAL] `service_role` key is in the client bundle.** `src/lib/supabase.ts:4` creates the client with `import.meta.env.VITE_SUPABASE_SERVICE_ROLE`. Any `VITE_`-prefixed value ships to the browser, and the service_role key bypasses RLS entirely, so this hands full database access to every visitor even after you fix finding 1. Rotate the key in the Supabase dashboard now (the current one is compromised the moment this was deployed), then use the anon key on the client and keep service_role server-side only.

## Fix This Week

3. **[HIGH] No rate limit on `src/api/generate-summary.ts`** which calls the OpenAI API. One script can run this in a loop overnight and hand you a four-figure bill. Add Upstash Ratelimit per the `rate-limiting.md` playbook, keyed by user id, 5 per minute.
4. **[HIGH] No input validation on the task-create call.** `src/api/tasks.ts:22` writes `req.body` straight to Supabase. Add a Zod schema (`input-validation.md`).
5. **[HIGH] No error tracking anywhere.** No Sentry, no global handler. When something breaks in production you will not know. Install Sentry client + server and add an error boundary (`error-tracking.md`).
6. **[HIGH] No automated backups configured.** Confirm Supabase daily backups are on for your plan and note the retention. Free tier has limited backups; consider a scheduled `pg_dump` if you are on it.
7. **[HIGH] No error boundary.** `src/App.tsx` has no `Sentry.ErrorBoundary` or equivalent, so one render error white-screens the whole app. Wrap the app.
8. **[HIGH] One environment only.** Production and development share the same Supabase project. A bad migration in dev can corrupt live data. Create a separate project or use branching.

## Fix This Month

9. **[MEDIUM] No loading states** on the dashboard data fetch (`src/pages/Dashboard.tsx`); users see a blank screen on slow connections.
10. **[MEDIUM] No empty state** on the task list; a new user with zero tasks sees a void, not a "create your first task" prompt.
11. **[MEDIUM] Security headers missing.** No `vercel.json` headers block. Add HSTS and the base four (`security-headers.md`).
12. **[MEDIUM] N+1 query** in `src/pages/Dashboard.tsx:40`: a `.map` that fetches each project's task count in a separate call. Fetch counts in one query.
13. **[MEDIUM] No uptime monitoring.** Add a free UptimeRobot check on the health URL.

## Nice to Have

14. **[LOW] Fixed pixel widths** on the sidebar (`src/components/Sidebar.tsx`) that could be fluid.

## Manual Checks Required

- **Secret-in-bundle test.** Run `npm run build`, open the app, DevTools > Sources, search for `service_role`. Given finding 2, expect a hit. After the fix, re-run and confirm it is gone. Evidence: screenshot.
- **User A cannot read User B.** After enabling RLS, log in as two accounts, try to fetch B's task by id as A. Evidence: paste the empty result.
- **Alerting reaches you.** After installing Sentry, throw a test error and confirm the alert arrives in email/Slack. Evidence: screenshot.
- **Rebuild in an hour.** Code is in git. Are the env vars saved in a password manager, and can you restore the database from a backup? Note which is missing.

---
Audited with the launchworthy skill by Kemal Esensoy / Wunderlandmedia (wunderlandmedia.com).
