# MONEYLINE billing contract

## Tiers and features

`free`, `analyst`, and `pro` are stable tier identifiers. Free includes Today,
Desk, and Track Record. Analyst adds Players, Matchups, and Wire. Pro adds
Parlay and Season outlook. The API owns this matrix in `backend/billing.py`;
the browser never grants access by changing local state.

## Subscription policy

Only Stripe `active` and `trialing` subscriptions grant paid access. A
`past_due`, `incomplete`, `incomplete_expired`, `unpaid`, `canceled`, or
deleted subscription resolves to Free until a later authoritative webhook
reports an active subscription. Checkout return URLs only refresh status; they
never grant access.

Premium endpoints return `authentication_required` (401) when there is no
authenticated user and `entitlement_required` (403) when that user lacks the
feature. Locked panels may show a preview and an upgrade link, but never
premium response data.

The authentication layer should expose a stable user mapping as
`request.state.user = {"id": "...", "email": "..."}`. Stripe and MONEYLINE
persist only customer/subscription identifiers and billing state; card data is
handled by Stripe.