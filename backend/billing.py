"""MONEYLINE billing catalog, entitlement policy, and Stripe adapter.

The auth task owns identity.  This module deliberately accepts a small user
mapping (id plus optional email) so the eventual auth dependency can be wired
without moving billing policy into the UI.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("moneyline")

FREE = "free"
ANALYST = "analyst"
PRO = "pro"
ACTIVE_STATUSES = {"active", "trialing"}
CATALOG = {
    FREE: {
        "name": "Free",
        "description": "A useful daily read of the model.",
        "price_monthly": 0,
        "features": ["today", "desk", "track_record"],
    },
    ANALYST: {
        "name": "Analyst",
        "description": "Player, matchup, and wire context for deeper research.",
        "price_monthly": 19,
        "features": ["today", "desk", "track_record", "players", "matchups", "wire"],
    },
    PRO: {
        "name": "Pro",
        "description": "The complete research terminal, including season and parlay tools.",
        "price_monthly": 49,
        "features": [
            "today", "desk", "track_record", "players", "matchups", "wire",
            "parlay", "season",
        ],
    },
}


def price_ids() -> dict[str, str]:
    return {
        ANALYST: os.getenv("STRIPE_ANALYST_PRICE_ID", ""),
        PRO: os.getenv("STRIPE_PRO_PRICE_ID", ""),
    }


def tier_for_price(price_id: str | None) -> str:
    for tier, configured in price_ids().items():
        if configured and configured == price_id:
            return tier
    return FREE


def has_feature(entitlement: dict[str, Any] | None, feature: str) -> bool:
    tier = (entitlement or {}).get("tier", FREE)
    status = (entitlement or {}).get("status", "free")
    return feature in CATALOG.get(tier, CATALOG[FREE])["features"] and (
        tier == FREE or status in ACTIVE_STATUSES
    )


def stripe_client():
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise RuntimeError("Stripe billing is not configured.")
    import stripe
    stripe.api_key = key
    return stripe


def event_created(event: dict[str, Any]) -> datetime:
    return datetime.fromtimestamp(int(event.get("created", 0)), tz=timezone.utc)


def subscription_state(subscription: dict[str, Any]) -> dict[str, Any]:
    items = subscription.get("items", {}).get("data", [])
    price_id = items[0].get("price", {}).get("id") if items else None
    status = str(subscription.get("status", "incomplete"))
    tier = tier_for_price(price_id) if status in ACTIVE_STATUSES else FREE
    return {
        "tier": tier,
        "status": status,
        "stripe_subscription_id": subscription.get("id"),
        "price_id": price_id,
        "current_period_start": _timestamp(subscription.get("current_period_start")),
        "current_period_end": _timestamp(subscription.get("current_period_end")),
        "cancel_at_period_end": bool(subscription.get("cancel_at_period_end", False)),
    }


def _timestamp(value: Any) -> datetime | None:
    return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None