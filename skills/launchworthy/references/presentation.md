# Terminal Presentation

How to render the audit in the terminal so every run looks the same, matches the report file, and reads at a glance. This is the format the user sees on screen. The saved report still uses [report-template.md](report-template.md); this is the on-screen companion.

No emojis. No em dashes. Severity words only: `[CRITICAL]`, `[HIGH]`, `[MEDIUM]`, `[LOW]`.

## The one color trick

The skill cannot set text color directly. But a fenced `diff` block gets semantic color from the renderer, and the two surfaces that matter both honor it: Claude Code's terminal and GitHub (your README and sample report).

- A line starting with `+ ` renders green. Use it for `PASS`.
- A line starting with `- ` renders red. Use it for `FAIL`.
- A line starting with `! ` renders amber where the renderer supports it, plain elsewhere. Use it for `WARN`.
- A line starting with a space is uncolored context. Use it for headers and the overall line.

Where a renderer does not colorize diffs, the block degrades to readable plain text with a leading `+`, `-`, or `!`. That is fine. Never rely on color to carry meaning that the verdict word does not already carry.

## The scorecard block

Present the scorecard inside a `diff` fence. Keep domains in numeric order (1 to 5) so it matches the report table. Pad the domain column so the verdict column aligns.

```diff
  Launchworthy · nimbus-notes
  Next.js 14 + Supabase · Vercel · live

  #  Domain                         Verdict  Findings
! 1  Frontend & Experience          WARN     1 high, 2 med, 1 low
- 2  Backend & Data                 FAIL     1 crit, 1 high
- 3  Auth & Security                FAIL     2 crit, 2 high
! 4  Infrastructure & Deployment    WARN     1 high, 1 med
- 5  Operations & Recovery          FAIL     3 high, 1 med

  Overall: 0/5 domains green · 2 crit, 8 high, 5 med, 1 low
```

The re-run, once the blockers are fixed, is the payoff. Show it the same way so the color flips from red to green in place:

```diff
+ 1  Frontend & Experience          PASS
+ 2  Backend & Data                 PASS
+ 3  Auth & Security                PASS
+ 4  Infrastructure & Deployment    PASS
+ 5  Operations & Recovery          PASS

  Overall: 5/5 domains green · launchworthy
```

If a domain is still provisional because a manual check is unresolved (see [evidence-interview.md](evidence-interview.md)), append ` (provisional)` to its Findings cell and keep it at `WARN` at best. Do not show a green `PASS` for a domain whose critical check you have not actually seen the evidence for.

## Findings, worst first

Under the scorecard, list findings worst first, outside the diff fence (severity tags carry the meaning). Bold the tag. One line each, with the file path.

```
[CRITICAL]  Supabase RLS disabled on 4 tables            supabase/migrations/
[CRITICAL]  service_role key shipped in the client       lib/supabase.ts:12
[HIGH]      No rate limit on /api/generate (paid model)  app/api/generate/route.ts
[HIGH]      No error tracking (Sentry not configured)    app/global-error.tsx
[MEDIUM]    White screen when the API returns 500        app/error.tsx
```

Note: `service_role` in the bundle is the real critical, not the anon key. The anon key in the frontend is by design and must never be listed as a finding (see checklist.md, Domain 3). Getting this pair right is the skill's whole credibility; a report that flags the anon key reads as amateur.

## Fix Now, with exact files

Then the top blockers as a numbered list, each pointing at the file to change with a `->` arrow, worst first.

```
Fix Now
  1. Enable RLS + ownership policies        -> supabase/migrations/
  2. Move the service key server-side       -> lib/supabase.ts
  3. Rate-limit the AI endpoint             -> app/api/generate/route.ts
  4. Wire up Sentry (client + server)       -> app/global-error.tsx
```

Keep it to the Fix Now group on screen. The full punch list (Fix This Week / Month / Nice to Have) lives in the saved report; point the user to it rather than dumping every tier in the terminal.

## Close the presentation

End with the score line and where the report went, so the next action is obvious.

```
Score: 0/5 domains green. Full report: tmp/hardening-nimbus-notes-2026-07-04.md
```

## Order on screen

1. One or two context lines: project name, detected stack, host, pre-launch or live.
2. The scorecard diff block.
3. Findings, worst first.
4. Fix Now.
5. Score line and report path.

Lead your spoken summary with the overall score and the single worst finding in plain language, then show the blocks. The blocks are the evidence; your sentence is the headline.
