# Fix: Security Headers

Security headers tell the browser how to defend your users: force HTTPS, block clickjacking, stop MIME sniffing, and constrain what the page is allowed to load. Missing CSP and HSTS are `[HIGH]`; the rest are `[MEDIUM]`.

Start with the safe, high-value four (HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy). Add a Content-Security-Policy carefully, because a strict CSP can break a working app if it forgets a domain you actually use. Test in report-only mode first.

## Next.js

```js
// next.config.js
const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
]

module.exports = {
  poweredByHeader: false, // also stop leaking "X-Powered-By: Next.js"
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }]
  },
}
```

## Astro, Netlify, Cloudflare Pages (a `public/_headers` file)

```
/*
  Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
  X-Frame-Options: SAMEORIGIN
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
```

## Vite SPA on a static host

Vite has no server, so headers are set at the host. On Netlify/Cloudflare use the `public/_headers` file above. On Nginx/Caddy, add them to the server config. On Vercel use `vercel.json`:

```json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "Strict-Transport-Security", "value": "max-age=63072000; includeSubDomains; preload" },
        { "key": "X-Frame-Options", "value": "SAMEORIGIN" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" }
      ]
    }
  ]
}
```

## SvelteKit

SvelteKit sets the base headers in the `handle` hook, and has a built-in CSP generator that hashes your inline scripts for you, which is a real advantage over hand-writing one.

```js
// src/hooks.server.js
export async function handle({ event, resolve }) {
  const response = await resolve(event)
  response.headers.set("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
  response.headers.set("X-Frame-Options", "SAMEORIGIN")
  response.headers.set("X-Content-Type-Options", "nosniff")
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin")
  return response
}
```

```js
// svelte.config.js  (let SvelteKit build the CSP and hash inline scripts)
const config = {
  kit: {
    csp: {
      mode: "auto",
      directives: {
        "default-src": ["self"],
        "img-src": ["self", "data:", "https:"],
        "connect-src": ["self", "https://*.supabase.co"],
      },
    },
  },
}
export default config
```

## TanStack Start

TanStack Start has no static config file for headers, so set them where they are reliable:
- **Preferred: the host.** On Netlify/Cloudflare use `public/_headers` (the block above); on Vercel use `vercel.json`; on Nginx/Caddy use the server config. This covers every response including static assets.
- **App-level: a server middleware.** Set the base headers on the response inside a global server middleware so app routes are covered even before the host config. Keep the host config as the backstop for static files.

Verify the same way as any stack: check the response headers in the Network tab after deploy.

## Content-Security-Policy (do this one carefully)

A good CSP is worth it but is app-specific. Deploy it in report-only mode first so violations are logged, not enforced:

```
Content-Security-Policy-Report-Only: default-src 'self'; img-src 'self' data: https:; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://your-api.example.com https://*.supabase.co
```

Watch the console for a few days, add the domains your app legitimately uses (analytics, Supabase, Stripe, fonts), then switch the header from `-Report-Only` to enforcing. Do not ship a strict enforcing CSP blind; you will break something and not know why.

## Verify

- Deploy, then run the site through a header scanner (securityheaders.com) or check the Network tab response headers.
- Confirm HSTS and the four base headers are present. Confirm `X-Powered-By` is gone.
- If you added CSP, confirm the app still loads every third-party resource (images, fonts, API calls) with no console violations.
