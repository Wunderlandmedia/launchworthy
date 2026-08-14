# Fix: Payments lifecycle

Charging a card once is the part the AI tool got right. The revenue leaks come after: a renewal that fails and is never chased, a refund the customer cannot self-serve, a dispute that auto-loses because nobody answered it. Most of this is provider dashboard configuration, but three things live in code and belong in the repo. Signature verification, honest status codes, and idempotency for the webhook itself are in `webhooks.md`; this playbook is the lifecycle on top of a handler that already verifies.

## Handle the failed renewal, not just the successful one

The common shape grants access on the success event and stops there:

```ts
// only the happy path
switch (event.type) {
  case "checkout.session.completed":
  case "invoice.paid":
    await grantAccess(event)          // never revisited when the next renewal fails
    break
}
```

Add the failure branch. Let the provider run its retry schedule (Stripe Smart Retries), and act on the terminal state, not on every failed attempt:

```ts
switch (event.type) {
  case "checkout.session.completed":
  case "invoice.paid":
    await grantAccess(event)
    break
  case "invoice.payment_failed":
    // one attempt failed; the provider will retry per the dunning schedule
    await flagPastDue(event)          // surface it, email the customer, but do not cut access yet
    break
  case "customer.subscription.updated":
    // terminal states after retries are exhausted
    if (event.data.object.status === "unpaid" || event.data.object.status === "canceled") {
      await revokeAccess(event)
    }
    break
}
```

The retry schedule and the dunning emails are dashboard settings, not code:

- **Stripe:** Billing > Revenue recovery. Turn on Smart Retries and the failed-payment email sequence, and set what happens when all retries fail (cancel the subscription or leave it unpaid). Decide it deliberately; the default may keep a non-paying subscription alive.
- Confirm the customer actually receives the dunning email (from address verified, not going to spam).

## Give the customer a refund and cancellation path

Two parts, both cheap.

Link the policy from where money changes hands. A `refund` / `/terms` / `/cancellation` link next to the pay button. "No refunds" is a valid policy, but it has to be visible before the charge, not discovered after.

Let the customer cancel without emailing you. The Stripe Billing customer portal is a hosted page for updating the card, downloading invoices, and cancelling:

```ts
const session = await stripe.billingPortal.sessions.create({
  customer: customerId,
  return_url: `${origin}/account`,
})
return Response.json({ url: session.url })
```

A self-serve cancel is the single biggest dispute reducer: a customer who can cancel in one click does not file a chargeback to make the charges stop.

## Be ready to answer a dispute

A chargeback starts a short clock (often about 7 days) and an unanswered dispute is lost by default. First make sure you learn about it in time:

```ts
case "charge.dispute.created":
  await alertTeam(event)              // Slack, email, PagerDuty; do not wait to notice the balance drop
  break
```

Then have the evidence ready to submit: proof of what was sold, the delivery or first-access timestamp, access and usage logs tying the account to the charge, and the recorded ToS acceptance. Stripe's dispute view has fields for exactly these; the point is that the data exists and you can retrieve it under time pressure, not that you assemble it from scratch during the window. Radar and clear billing descriptors reduce how many disputes you get in the first place.

## Verify

- Use a test card that simulates a failed renewal (Stripe test card `4000 0000 0000 0341`) and confirm the `invoice.payment_failed` branch fires and the customer gets the dunning email.
- Drive a subscription to the terminal unpaid/canceled state and confirm access is actually revoked.
- Open the billing portal link as a test customer and confirm cancel and card-update work.
- Trigger a test dispute (`stripe trigger charge.dispute.created`) and confirm the alert reaches a human, not just the dashboard.
- Load the checkout page and confirm the refund/cancellation policy link is present and resolves.
