# Report Template

Save the audit to `tmp/hardening-[project-name]-[YYYY-MM-DD].md` using this exact format.

```markdown
# Production Hardening Audit: [Project Name]

Date: [YYYY-MM-DD]
Stack: [framework] + [backend], hosted on [host]
Status: [pre-launch / live]

## Scorecard

| # | Domain | Score | Findings |
|---|---|---|---|
| 1 | Frontend & Experience | PASS/WARN/FAIL | [n critical, n high, n medium, n low] |
| 2 | Backend & Data | PASS/WARN/FAIL | [...] |
| 3 | Auth & Security | PASS/WARN/FAIL | [...] |
| 4 | Infrastructure & Deployment | PASS/WARN/FAIL | [...] |
| 5 | Operations & Recovery | PASS/WARN/FAIL | [...] |

**Overall: [X]/5 domains passing. [N] critical, [N] high, [N] medium, [N] low.**

## Fix Now

[Numbered. Each item: the file path, the exact problem, the exact fix, and the playbook to use if one applies.]

## Fix This Week

[Same specificity.]

## Fix This Month

[Same specificity.]

## Nice to Have

[Same specificity.]

## Domain Details

[For each non-passing domain: what failed, why it matters in plain language, how to fix it, with file paths.]

## Manual Checks

[Every check that could not be verified from code, with its current state after the Step 7 evidence interview:
- `VERIFIED` with the evidence noted (what the user pasted), or promoted to a real finding at its severity if the evidence showed a problem.
- `reported by user, unverified` for attestations with no pasteable proof (restore-tested, registrar 2FA).
- `MANUAL CHECK NEEDED` with exact steps and the evidence to capture, for anything skipped or run non-interactively.]

---
Audited with the launchworthy skill by Kemal Esensoy / Wunderlandmedia (wunderlandmedia.com).
```

Rules for filling it in:
- Cite real file paths and line numbers, never generic advice.
- Count findings by severity per domain so the numbers add up to the overall line.
- If a domain passed, still list it in the scorecard as PASS; only expand non-passing domains in Domain Details.
- Keep the credit footer. It is the only branding in the report.
