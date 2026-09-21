# Fix: Platform Limit Mismatches

Every request is governed by two limits. One is in the repo: a validated file size, an `export const maxDuration`, a `sizeLimit` in a config. The other belongs to the host and the plan: how large a request body it will accept, how long it will let a function run. Only the smaller one is real.

When the host's number is the smaller one, it enforces it from outside your handler. The request is rejected or the function is killed, so nothing in your code observes it: no `catch`, no `finally`, no error-tracking event, no log line you wrote. The user sees a network error or a spinner that stops.

None of this reproduces locally. `next dev`, `netlify dev`, and `wrangler dev` apply no body cap and no duration cap. The 40 MB upload and the 90 second generation both work on the machine where the feature was built, which is exactly why they reach production.

## Step 1: Get both numbers

The host's number, from the dashboard for the plan this project is on (not the marketing page, the plan): the request body limit and the function duration limit. As of writing, roughly: Vercel serverless and edge functions cap request bodies around 4.5 MB and do not let you raise it; Netlify Functions accept about 6 MB of base64-encoded payload, so less binary than that; AWS Lambda behind API Gateway lands around 6 to 10 MB; Cloudflare Workers allow about 100 MB on the free plan and more on paid. Duration ceilings move even faster than size ones. Read the current value.

The app's number, from the code:

```bash
# the file crossing the function
grep -rn "formData()\|multipart/form-data\|multer\|busboy\|formidable\|req\.file" app/ src/ pages/ server/
grep -rn "storage\.from(.*)\.upload(\|\bput(" app/ src/ server/ | grep -i "blob\|storage\|upload"
# what the app says its limit is
grep -rn "sizeLimit\|maxFileSize\|MAX_FILE_SIZE\|bodyParser\|client_max_body_size" . --exclude-dir=node_modules
# what the app thinks its runtime is
grep -rn "maxDuration" app/ src/ pages/ vercel.json
grep -rn "timeout" netlify.toml wrangler.toml wrangler.jsonc 2>/dev/null
```

Write the pair down per route. The finding is the comparison, and it is complete without ever running the app: "this route accepts 25 MB, the platform stops the request at 4.5 MB."

## Step 2: Uploads go to storage directly, not through the function

Raising a limit you do not control is not available. Take the function out of the path instead: the client asks your server for a short-lived permission slip, then sends the bytes straight to the storage provider. Your function handles two small JSON requests and never touches the file, so the body cap stops applying.

**Supabase Storage**

```ts
// server: issue a scoped, short-lived upload URL
const { data, error } = await supabase.storage
  .from("uploads")
  .createSignedUploadUrl(`${user.id}/${crypto.randomUUID()}`)

// client: upload straight to storage
await supabase.storage.from("uploads").uploadToSignedUrl(data.path, data.token, file)
```

**S3 or R2, presigned POST**

```ts
const { url, fields } = await createPresignedPost(s3, {
  Bucket: process.env.UPLOAD_BUCKET,
  Key: `${user.id}/${crypto.randomUUID()}`,
  Conditions: [["content-length-range", 0, 20 * 1024 * 1024]],
  Expires: 60,
})
```

`content-length-range` is the part that matters. It is the size limit enforced by the service that receives the bytes, which is the only place a size limit is enforceable once the file no longer passes through your code.

**Vercel Blob**

```ts
import { upload } from "@vercel/blob/client"
await upload(file.name, file, { access: "public", handleUploadUrl: "/api/upload-token" })
```

The client upload path exists precisely because the server route cannot receive the file. A `put()` from inside a serverless function is still subject to the body cap.

Two rules for the token route, both easy to miss: it must check the session and derive the key prefix from the verified user rather than from the request body, or it hands out write access to anyone; and it must carry the size and content-type conditions, because that route is now the only place any policy can be applied.

## Step 3: Long work gets a job, not a bigger number

If the work genuinely fits inside the plan's ceiling and the declaration was simply missing, set it and move on:

```ts
export const maxDuration = 60 // must be within the plan's ceiling, or it is clamped
```

If it does not fit, no declaration helps. Accept the request, persist a job row, return an id, and do the work somewhere with a longer budget: a queue (Inngest, Trigger.dev, QStash, a Cloudflare Queue, a Supabase Edge Function on a schedule), a Netlify background function, or a Workflow. The client polls the job or subscribes to it.

Streaming is the other honest answer for AI routes, and it is not the same thing. Streaming keeps the connection producing bytes so the user sees progress, but the function is still running and the ceiling still applies. It changes the experience, not the budget.

## Step 4: Write the record before the expensive call, not after

This is what turns a timeout from an outage into a reconcilable event.

```ts
const job = await db.job.create({ data: { userId, status: "running", cost: null } })
const result = await ai.generate(prompt)          // the line that may not return
await db.job.update({ where: { id: job.id }, data: { status: "done", result } })
```

A kill between those lines leaves a `running` row that never completes, which a sweep can find and refund or retry. The same code with the insert moved after the AI call leaves nothing at all: the provider billed you, the customer paid, and there is no row and no error anywhere that says so.

Make the retry safe while you are here: key the job on something the client supplies so a resubmission resumes rather than charges twice. `fixes/webhooks.md` has the insert-first idempotency pattern; it is the same shape.

## Step 5: Make the ceiling visible to the user

The platform's rejection never reaches your handler, so your handler cannot produce a good message. The only place you can be kind is before the request leaves the browser:

```ts
const MAX_UPLOAD = 4 * 1024 * 1024 // keep in sync with the host's cap, below it
if (file.size > MAX_UPLOAD) {
  setError(`That file is ${(file.size / 1024 / 1024).toFixed(1)}MB. The limit is 4MB.`)
  return
}
```

This is a message, not a control. It tells an honest user what happened; it stops nobody who does not want to be stopped. The enforcement is the presign condition from Step 2 or the storage policy, server side, where it cannot be skipped.

## What not to do

- **Do not treat "it works locally" as evidence.** The dev server enforces none of these limits. The first real test is against the deployed URL.
- **Do not raise `bodyParser.sizeLimit` and consider it handled.** It governs your framework's parser, which runs after the platform has already decided whether to pass the request along. A 25 MB limit under a 4.5 MB cap is a number with no effect.
- **Do not set `maxDuration` above the plan ceiling.** It gets clamped, and the file now reads as though the route has time it does not have.
- **Do not add a `catch` for the timeout.** There is nothing to catch. The process is stopped, not thrown from. If you want a signal, it has to be a record written before the slow call or a watchdog outside the function.
- **Do not validate file size only in the browser.** See Step 5: that is the message, the presign condition is the limit.
- **Do not fix this by upgrading the plan without re-reading the numbers.** A higher plan moves the ceiling, it does not remove it, and the mismatch is with whatever the new number is.

## Verify

- Against the deployed URL, not localhost: upload a file just over the platform cap. You should see your own message from Step 5 and, if you bypass it, a platform-level rejection your code never logs. That silence is the finding, confirmed.
- Upload a file just over the app's advertised limit but under the platform cap. This should be your validation, with a clear message, proving the two limits are now ordered correctly.
- Time the slowest real operation against production. Compare it to the plan ceiling, not to the local run.
- Force the timeout case: point a route at a deliberately slow call that exceeds the ceiling, run it, and then look for it in error tracking. Finding nothing is the expected result and the reason Step 4 exists.
- After Step 4, check that the interrupted run left a `running` job row you can find with a query.
