# Fix: Input Validation

Every endpoint that changes data (POST/PUT/PATCH/DELETE, server actions, edge functions) must validate its input before using it. AI-generated handlers usually trust the request body completely, which means a malformed or malicious payload flows straight into your database or an expensive API call. Validation is also the cheapest place to reject abuse.

## Default: Zod

```bash
npm install zod
```

Define the schema next to the handler and parse at the top. If parsing fails, return 400 with the issues, never a stack trace.

```ts
// app/api/todos/route.ts (Next.js example)
import { z } from "zod"

const CreateTodo = z.object({
  title: z.string().min(1).max(200),
  dueDate: z.string().datetime().optional(),
  priority: z.enum(["low", "medium", "high"]).default("medium"),
})

export async function POST(req: Request) {
  const body = await req.json().catch(() => null)
  const parsed = CreateTodo.safeParse(body)

  if (!parsed.success) {
    return Response.json(
      { error: "Invalid input", issues: parsed.error.flatten() },
      { status: 400 },
    )
  }

  const { title, dueDate, priority } = parsed.data   // now typed and safe
  // ... write to the database
}
```

## Server actions (Next.js)

```ts
"use server"
import { z } from "zod"

const Schema = z.object({ email: z.string().email(), message: z.string().min(1).max(2000) })

export async function submitContact(formData: FormData) {
  const parsed = Schema.safeParse({
    email: formData.get("email"),
    message: formData.get("message"),
  })
  if (!parsed.success) return { error: parsed.error.flatten() }
  // ... proceed
}
```

## SvelteKit (form actions and `+server.ts`)

Validate in the form `action` and return `fail(400, ...)` so the page can show the errors without losing the user's input.

```ts
// src/routes/contact/+page.server.ts
import { fail } from "@sveltejs/kit"
import { z } from "zod"

const Schema = z.object({ email: z.string().email(), message: z.string().min(1).max(2000) })

export const actions = {
  default: async ({ request }) => {
    const form = Object.fromEntries(await request.formData())
    const parsed = Schema.safeParse(form)
    if (!parsed.success) {
      return fail(400, { issues: parsed.error.flatten(), values: form })
    }
    // ... proceed with parsed.data
  },
}
```

API endpoints validate the same way:

```ts
// src/routes/api/todos/+server.ts
import { json, error } from "@sveltejs/kit"
import { z } from "zod"

const Body = z.object({ title: z.string().min(1).max(200) })

export async function POST({ request }) {
  const parsed = Body.safeParse(await request.json().catch(() => null))
  if (!parsed.success) throw error(400, "Invalid input")
  // ... proceed
}
```

## TanStack Start (server functions)

`createServerFn` has validation built in. The `.validator()` runs before the handler, so `data` is already parsed and typed. This is the idiomatic place, do not skip it.

```ts
import { createServerFn } from "@tanstack/react-start"
import { z } from "zod"

const CreateTodo = z.object({ title: z.string().min(1).max(200) })

export const createTodo = createServerFn({ method: "POST" })
  .validator((input: unknown) => CreateTodo.parse(input))  // throws on bad input
  .handler(async ({ data }) => {
    // data is typed and validated
    // ... write to the database
  })
```

## Express / Node

```ts
import { z } from "zod"

const Body = z.object({ name: z.string().min(1), amount: z.number().positive() })

app.post("/api/charge", (req, res) => {
  const parsed = Body.safeParse(req.body)
  if (!parsed.success) return res.status(400).json({ issues: parsed.error.flatten() })
  // ... proceed with parsed.data
})
```

## Principles

- **Validate on the server, always.** Client-side validation is a UX nicety; it is trivially bypassed. The server is the only place that counts.
- **Whitelist, do not blacklist.** Define the exact shape you accept and reject everything else, rather than trying to strip bad values.
- **Bound strings and numbers.** `max()` on strings and sane ranges on numbers stop giant payloads and negative-amount tricks.
- **Never echo raw errors.** Return the validation issues, not the exception or stack trace.

Valibot is a lighter-weight alternative with the same pattern if bundle size matters. Pick one and use it everywhere; do not mix validators.

## Verify

- Grep mutating handlers for ones that read `req.json()` / `req.body` / `formData` and use it without a schema.
- Send a malformed payload and confirm you get a 400 with issues, not a 500 with a stack trace.
