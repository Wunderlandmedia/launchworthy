# Fix: Secrets in Git History

Deleting a secret from a file is a code change. It is not a security fix. The old blob is still in the history, reachable by anyone who can clone the repo, and if the repo is or ever was public, assume it is already in someone's dataset.

The order that matters: **rotate first, clean up second, and treat the cleanup as optional.** Almost everyone does this backwards, spends an afternoon rewriting history, and leaves the live key working the whole time.

## Step 1: Find what is actually in there

Prefer a real scanner. It knows credential formats you will not think to grep for, and it can tell you whether a key still works.

```bash
gitleaks detect --source . --redact            # full history by default, redacts values in output
trufflehog git file://. --results=verified     # "verified" means it called the provider and the key is live
```

No scanner and no appetite to install one? The targeted version catches the common prefixes:

```bash
git grep -nEI "sk_live_|sk-[A-Za-z0-9_-]{20,}|rk_live_|sb_secret_|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20}|github_pat_|AIza[0-9A-Za-z_-]{20}|xox[baprs]-|service_role|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|postgres(ql)?://[^:]+:[^@]+@" $(git rev-list --all) 2>/dev/null

# files that no longer exist but are intact in the commit that deleted them
git log --all --diff-filter=D --name-only -- '*.env' '*.env.*' '*.pem' '*.p12' '*-key.json'

# the history of one suspicious file, whatever it is called now
git log -p --all --follow -- path/to/config.ts
```

`git rev-list --all` covers every branch and tag, which is the point: the leak is often on a dead feature branch nobody remembers. On a very long history, bound it with `-n 500` and note that the scan was bounded.

Two things the grep will miss and the scanner catches: base64 or JWT-shaped values with no recognizable prefix (a Supabase `service_role` JWT looks like any other `eyJ...`), and credentials inside a committed lockfile, notebook output, or build artifact. To check a JWT by hand, decode its middle segment and read the `role` claim; the deployed-bundle probe in `evidence-interview.md` shows how.

## Step 2: Rotate every key you found

This is the fix. Everything after it is hygiene.

For each credential, in this order:

1. **Issue the new key** in the provider dashboard and put it in your deployment's env vars.
2. **Deploy and confirm the app works on the new key.**
3. **Revoke the old one.** Not "delete later." Revoked, in the dashboard, with the old value now returning 401.

The step people skip is 3. A rotated-but-not-revoked key is exactly as leaked as before.

Per provider, the thing to actually revoke:

- **Stripe:** roll the restricted or secret key (Developers > API keys > Roll). Rolling supports a grace window; set it short.
- **Supabase:** the `service_role` key is a signed JWT, so it cannot be revoked individually. You must rotate the project's JWT secret, which invalidates the anon key and every existing user session too. Plan for the forced logout; do it anyway.
- **AWS:** create a new access key, deploy, then delete the old one. Check CloudTrail for use of the old key before and after.
- **Database URL with a password:** change the password on the role, do not just move the URL to an env var. The password is the credential.
- **OAuth client secrets, SMTP passwords, webhook signing secrets:** each has its own rotate path; none of them rotate by editing your repo.

If a key cannot be rotated without downtime, schedule the downtime. The alternative is a live credential in a public blob.

## Step 3: Check whether it was used

Rotation stops the future. The provider's logs tell you about the past.

- Stripe: Developers > Logs, filter by the old key, look for requests from IPs that are not yours.
- AWS: CloudTrail, filter by the access key id.
- Supabase / Postgres: connection logs, and look for unexpected reads on user tables.
- GitHub tokens: the audit log for actions you did not take.

Nothing suspicious is good news and not proof; most providers keep a limited window. Say that in the report rather than declaring it clean.

## Step 4: Stop the next one

```gitignore
.env
.env.*
!.env.example
*.pem
*.p12
*-key.json
```

Then commit an `.env.example` with the *names* and no values, so the next person has no reason to paste a real key into a tracked file.

Add the scanner to CI so this check keeps running after today:

```yaml
# .github/workflows/secrets.yml
name: secret scan
on: [push, pull_request]
jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0        # without this it scans one commit and always passes
      - uses: gitleaks/gitleaks-action@v2
```

`fetch-depth: 0` is the whole job. A shallow checkout makes the scan green by making it blind.

If the repo is on GitHub, turn on Push Protection (Settings > Code security). It blocks the commit that contains a recognized key format before it ever reaches the remote, which is the only place in this playbook where a fix is cheap.

## Step 5: Rewriting history, if you still want to

Only after rotation, and only knowing what it does not do.

```bash
git filter-repo --replace-text secrets.txt     # each line: literal-value==>REDACTED
git push --force --all
git push --force --tags
```

What it does not reach: existing clones, forks, anyone's local reflog, CI caches, and provider-side caches of the old commits. On GitHub, a commit that has been force-pushed away can often still be fetched by its SHA and stays visible through fork networks and pull request refs; purging that requires asking GitHub Support. Every collaborator must re-clone, because a stale clone that gets pushed puts the old commits back.

That is why this is Step 5 and not Step 1.

## What not to do

- **Do not rewrite history and call the leak closed.** The clones you cannot see still have the value. Rotation is the fix; rewriting is tidying.
- **Do not amend the commit and force-push as your only response.** Same reason, less coverage.
- **Do not mark it resolved because the commit is old.** A key from 2023 that still authenticates today is a live key today.
- **Do not paste the found value into chat, an issue, or a commit message while fixing it.** That leaks it again into systems with different retention. Refer to it by variable name and file.
- **Do not assume a private repo is safe.** Every collaborator, every past collaborator, every CI runner, and every laptop backup has it. Private lowers the severity, it does not close the finding.
- **Do not skip the scan because the current tree is clean.** A clean tree is the normal state of a repo that leaked a key last month.

## Verify

- Run the scanner again and confirm zero findings, or that each remaining finding is a value that has been rotated and revoked.
- Try the old credential against the provider (a `curl` that used to work) and confirm it now returns 401 or 403. This is the only real proof the rotation landed.
- Confirm the new value lives only in the deployment's env vars and a password manager, and appears nowhere in `git grep`.
- Confirm CI runs the scanner with `fetch-depth: 0`, by pushing a branch with a dummy fake key and watching the job fail.
- Confirm `.env` is ignored and `.env.example` carries names only.
