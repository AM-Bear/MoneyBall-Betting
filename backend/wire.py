"""The Wire: merged transactions + headlines + desk notes, and team pulse.

Every item traces to an API response or to structured data the desk already
owns (graded picks, daily records). Desk notes are template-generated from
real fields only — if a template lacks a real value, the note isn't written.
Neither the wire nor the pulse ever moves a price.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from backend.analytics import score_pulse_items
from backend.feeds import (
    EASTERN,
    get_news,
    get_team_directory,
    get_transactions,
)

WIRE_TYPES = {"TRADE", "SIGNING", "IL", "ACTIVATED", "RESULT", "NEWS"}


def _desk_notes(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Notes the desk writes itself from graded picks — real fields only."""
    notes: list[dict[str, Any]] = []
    by_date: dict[str, dict[str, float]] = {}
    for entry in record.get("entries", []):
        if entry.get("result") not in {"WIN", "LOSS"}:
            continue
        required = (
            entry.get("away_team"),
            entry.get("home_team"),
            entry.get("final_away"),
            entry.get("final_home"),
            entry.get("pick_team"),
            entry.get("model_probability"),
            entry.get("game_date"),
        )
        if any(value is None for value in required):
            continue  # a template without a real value writes no note
        grade = "✓W" if entry["result"] == "WIN" else "✗L"
        probability = round(float(entry["model_probability"]) * 100)
        notes.append(
            {
                "id": f"desk-result-{entry['game_pk']}",
                "type": "RESULT",
                "text": (
                    f"{entry['away_team']} {entry['final_away']} @ "
                    f"{entry['home_team']} {entry['final_home']} — FINAL · "
                    f"DESK HAD {entry['pick_team']} {probability}% · GRADED {grade}"
                ),
                "team": entry["home_team"],
                "teams": [entry["away_team"], entry["home_team"]],
                "date": entry["game_date"],
                "source": "DESK",
                "link": None,
                "result": entry["result"],
            }
        )
        day = by_date.setdefault(
            entry["game_date"], {"wins": 0, "losses": 0, "units": 0.0}
        )
        day["wins"] += entry["result"] == "WIN"
        day["losses"] += entry["result"] == "LOSS"
        day["units"] += float(entry.get("units_pnl") or 0.0)

    for day, tally in by_date.items():
        units = tally["units"]
        notes.append(
            {
                "id": f"desk-summary-{day}",
                "type": "RESULT",
                "text": (
                    f"DESK RECORD {day}: {int(tally['wins'])}–{int(tally['losses'])} "
                    f"· {'+' if units >= 0 else ''}{units:.1f}u"
                ),
                "team": None,
                "date": day,
                "source": "DESK",
                "link": None,
            }
        )
    return notes


def _sort_key(item: dict[str, Any]) -> str:
    return str(item.get("date") or "")


async def get_wire(
    record: dict[str, Any] | None,
    team: str | None = None,
    types: list[str] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Merged, deduped, filterable wire feed with per-source degradation."""
    sources_up: dict[str, bool] = {}

    async def safe(name: str, coroutine: Any) -> list[dict[str, Any]]:
        try:
            items = await coroutine
            sources_up[name] = True
            return items
        except Exception:
            sources_up[name] = False
            return []

    transactions, news = await asyncio.gather(
        safe("transactions", get_transactions()),
        safe("news", get_news()),
    )
    notes = _desk_notes(record) if record else []
    sources_up["desk"] = record is not None

    merged = [*transactions, *news, *notes]

    # Dedupe on normalized text, keeping the first (transactions outrank RSS).
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in merged:
        key = " ".join(str(item.get("text", "")).lower().split())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    if team:
        team = team.upper()
        directory = await get_team_directory()
        names = [
            entry["name"]
            for entry in directory.values()
            if entry["code"] == team
        ]
        deduped = [item for item in deduped if _item_mentions(item, team, names)]
    if types:
        wanted = {t.upper() for t in types if t.upper() in WIRE_TYPES}
        if wanted:
            deduped = [item for item in deduped if item["type"] in wanted]

    deduped.sort(key=_sort_key, reverse=True)
    return {
        "items": deduped[: max(1, min(limit, 250))],
        "total_before_limit": len(deduped),
        "sources_up": sources_up,
        "updated_at": datetime.now(EASTERN).isoformat(),
        "types": sorted(WIRE_TYPES),
        "note": (
            "Every item traces to an MLB API response or to the desk's own "
            "graded record. Nothing here moves a price."
        ),
    }


def _item_mentions(item: dict[str, Any], code: str, names: list[str]) -> bool:
    if item.get("team") == code or code in (item.get("teams") or []):
        return True
    text = str(item.get("text", ""))
    return any(name and name in text for name in names)


async def get_team_pulse(team_id: int, record: dict[str, Any] | None) -> dict[str, Any]:
    """7-day lexicon pulse for one team, with the full evidence list."""
    directory = await get_team_directory()
    entry = directory.get(team_id)
    if entry is None:
        raise LookupError("Unknown MLB team id.")
    wire = await get_wire(record, team=entry["code"], limit=250)
    cutoff = (datetime.now(EASTERN) - timedelta(days=7)).date().isoformat()
    recent = [
        item for item in wire["items"] if str(item.get("date") or "")[:10] >= cutoff
    ]
    pulse = score_pulse_items(recent)
    return {
        "team": entry["code"],
        "team_id": team_id,
        "window_days": 7,
        **pulse,
        "hard_rule": "The pulse never moves a price; it is disclosed context only.",
    }
