"""Runs one victim report from intake to a sealed report, publishing progress as it goes."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone

from .chain import BlockscoutClient, ChainError
from .labels import Registry
from .scoring import score_wallet
from .store import Store, canonical, now_iso, sha256
from .tracer import trace

DISCLAIMER = (
    "This report is a risk indication to support human review. It is not proof of fraud or of "
    "anyone's identity or intent. Amounts on a route are upper bounds, because an address can "
    "mix funds from many sources. Labels come from public lists and can be incomplete or out of date."
)
LEVELS = {"low": 0, "medium": 1, "high": 2}


class EventBus:
    """Keeps each running case's events, so a viewer who connects late still sees them all."""

    def __init__(self):
        self.events: dict[str, list[dict]] = defaultdict(list)
        self.waiters: dict[str, list[asyncio.Event]] = defaultdict(list)

    def publish(self, case_id: str, event: dict) -> None:
        self.events[case_id].append(event)
        for waiter in self.waiters[case_id]:
            waiter.set()

    async def stream(self, case_id: str):
        index = 0
        waiter = asyncio.Event()
        self.waiters[case_id].append(waiter)
        try:
            while True:
                while index < len(self.events[case_id]):
                    event = self.events[case_id][index]
                    index += 1
                    yield event
                    if event["type"] in ("complete", "failed"):
                        return
                waiter.clear()
                try:
                    await asyncio.wait_for(waiter.wait(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"type": "keepalive"}
        finally:
            self.waiters[case_id].remove(waiter)


def counterparty_signals(address: str, history: dict, registry: Registry) -> dict:
    """List-based evidence, kept apart from the model score on purpose."""
    me = address.lower()
    counterparties: set[str] = set()
    for key in ("txs", "internal", "tokens"):
        for t in history[key]:
            counterparties.update(x for x in (t["f"], t["t"]) if x and x != me)
    flagged = [{"address": c, "why": registry.flags(c)[0]} for c in sorted(counterparties) if registry.flags(c)]
    mixers = sorted({registry.entity(c).name for c in counterparties
                     if registry.entity(c) and registry.entity(c).category == "mixer"})
    return {"counterparties_checked": len(counterparties), "flagged_counterparties": flagged[:25],
            "flagged_count": len(flagged), "mixer_contacts": mixers}


def review_priority(risk: dict, flags: list[str], signals: dict) -> tuple[str, list[str]]:
    why: list[str] = []
    level = risk.get("level", "low") if risk.get("status") == "scored" else "low"
    if risk.get("status") == "scored":
        why.append(f"Model risk is {level}")
    if flags:
        level = "high"
        why.append(f"Address appears on {len(flags)} public fraud list entr{'y' if len(flags) == 1 else 'ies'}")
    if signals["mixer_contacts"]:
        level = max(level, "medium", key=LEVELS.get)
        why.append("Direct contact with a mixer")
    if signals["flagged_count"]:
        level = max(level, "medium", key=LEVELS.get)
        why.append(f"{signals['flagged_count']} counterpart{'y' if signals['flagged_count'] == 1 else 'ies'} on a public fraud list")
    return level, why


async def resolve_start_time(client: BlockscoutClient, case: dict) -> tuple[int, str | None, dict | None]:
    """Use the victim's transaction, when given, as the point the trace starts from."""
    if not case.get("victim_tx"):
        return 0, None, None
    tx = await client.transaction(case["victim_tx"])
    if not tx or not tx.get("timestamp"):
        return 0, "The reported transaction hash was not found on Ethereum, so all outflows were traced.", None
    ts = int(datetime.fromisoformat(tx["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp())
    sender = ((tx.get("from") or {}).get("hash") or "").lower()
    recipient = ((tx.get("to") or {}).get("hash") or "").lower()
    summary = {"hash": case["victim_tx"], "from": sender, "to": recipient, "timestamp": ts,
               "value_eth": int(tx.get("value") or 0) / 1e18}
    note = None
    transfers = [(t.get("to") or {}).get("hash", "").lower() for t in (tx.get("token_transfers") or [])]
    if case["address"] != recipient and case["address"] not in transfers:
        note = "The reported transaction does not pay the suspect wallet directly. Please check the details."
    return ts, note, summary


async def run_case(case_id: str, store: Store, bus: EventBus, client: BlockscoutClient, registry: Registry) -> None:
    case = store.get_case(case_id)
    address = case["address"]

    def emit(event: dict) -> None:
        bus.publish(case_id, event)

    try:
        store.update_case(case_id, status="running")
        emit({"type": "status", "message": "Reading the suspect wallet from Ethereum"})
        history = await client.history(address)

        emit({"type": "status", "message": "Scoring wallet behaviour"})
        # Model and SHAP work is CPU-bound, so it must not block other live traces.
        risk = await asyncio.to_thread(score_wallet, address, history, history["is_contract"])
        flags = registry.flags(address)
        entity = registry.entity(address)
        signals = counterparty_signals(address, history, registry)
        emit({"type": "risk", "risk": risk, "flags": flags, "signals": signals})

        since_ts, note, victim_tx = await resolve_start_time(client, case)
        emit({"type": "status", "message": "Tracing funds toward exchanges"})
        result = None
        async for event in trace(client, registry, address, since_ts):
            if event["type"] == "done":
                result = event["result"]
            else:
                emit(event)

        priority, priority_reasons = review_priority(risk, flags, signals)
        report = {
            "report_version": 1,
            "case_id": case_id,
            "generated_at": now_iso(),
            "chain": "ethereum-mainnet",
            "data_source": "Blockscout public API (eth.blockscout.com)",
            "suspect_address": address,
            "suspect_entity": {"category": entity.category, "entity": entity.entity, "name": entity.name} if entity else None,
            "incident": {"victim_tx": victim_tx, "reported_tx": case["victim_tx"], "amount_lost": case["amount_lost"],
                         "incident_date": case["incident_date"], "description": case["description"]},
            "notes": [note] if note else [],
            "review_priority": priority,
            "priority_reasons": priority_reasons,
            "risk": risk,
            "list_flags": flags,
            "signals": signals,
            "trace": result,
            "disclaimer": DISCLAIMER,
        }
        body = canonical(report)
        report_hash = sha256(body)
        store.update_case(case_id, status="complete", priority=priority, report_json=body, report_hash=report_hash)
        sealed = store.append_audit(case_id, "report_sealed", report_hash)
        emit({"type": "complete", "report_hash": report_hash, "audit": sealed})
    except (ChainError, OSError, ValueError, KeyError, TypeError) as exc:
        message = f"{type(exc).__name__}: {exc}"
        store.update_case(case_id, status="failed", error=message)
        store.append_audit(case_id, "case_failed", {"error": message})
        emit({"type": "failed", "message": message})


def load_report(case: dict) -> dict | None:
    return json.loads(case["report_json"]) if case.get("report_json") else None
