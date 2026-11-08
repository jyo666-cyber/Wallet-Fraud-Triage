"""Follow funds forward from a suspect wallet until they reach an exchange.

Breadth-first over outgoing transfers, keeping these rules:
  * Time order: a transfer is followed only if it happened after the funds reached that address.
  * Same asset: ETH is followed as ETH, USDT as USDT. A swap to another asset ends that path.
  * Real tokens only: spoofed tokens can copy the symbol "USDT", so tokens are matched by contract.
  * Bounded: limited hops, largest branches first, limited total addresses.

Amounts on a route are upper bounds: an address mixes funds from many sources, so the on-chain
record can show that value could have reached an exchange, not that it was the victim's money.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import AsyncIterator

from .chain import BlockscoutClient
from .config import (
    DEPOSIT_SWEEP_SHARE,
    HISTORY_CAP,
    TRACE_HIGH_ACTIVITY,
    TRACE_MAX_HOPS,
    TRACE_MAX_NODES,
    TRACE_TOP_K,
)
from .labels import Registry

ETH = "ETH"
TRACKED_TOKENS = {
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
    "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
    "0x4fabb145d64652a948d72533023f6e7a623c7c53": "BUSD",
}
# Rough dust floors per asset, so that poisoning dust does not create branches.
MIN_AMOUNT = {ETH: 0.001, "WETH": 0.001, "WBTC": 0.0001, "USDT": 1.0, "USDC": 1.0, "DAI": 1.0, "BUSD": 1.0}


@dataclass
class Transfer:
    tx: str
    src: str
    dst: str
    asset: str
    amount: float
    ts: int


@dataclass
class Frontier:
    address: str
    hop: int
    asset: str | None
    arrived_ts: int
    route_amount: float
    route: list[Transfer] = field(default_factory=list)


def outgoing_transfers(address: str, history: dict, since_ts: int) -> list[Transfer]:
    """Successful ETH and tracked-token transfers leaving this address at or after a time."""
    me = address.lower()
    found: list[Transfer] = []
    for t in history["txs"]:
        if t["f"] == me and t["t"] and not t["e"] and t["v"] > 0 and t["ts"] >= since_ts:
            found.append(Transfer(t["h"], me, t["t"], ETH, t["v"] / 1e18, t["ts"]))
    for t in history["internal"]:
        if t["f"] == me and t["t"] and not t["e"] and t["v"] > 0 and t["ts"] >= since_ts:
            found.append(Transfer(t["h"], me, t["t"], ETH, t["v"] / 1e18, t["ts"]))
    for t in history["tokens"]:
        symbol = TRACKED_TOKENS.get(t["a"])
        if symbol and t["f"] == me and t["t"] and t["v"] > 0 and t["ts"] >= since_ts:
            found.append(Transfer(t["h"], me, t["t"], symbol, t["v"] / 10 ** (t["d"] or 18), t["ts"]))
    return [f for f in found if f.amount >= MIN_AMOUNT.get(f.asset, 0)]


def aggregate(transfers: list[Transfer]) -> list[Transfer]:
    """One edge per (destination, asset), keeping the earliest time and first tx as evidence."""
    grouped: dict[tuple[str, str], Transfer] = {}
    for t in sorted(transfers, key=lambda x: x.ts):
        key = (t.dst, t.asset)
        if key in grouped:
            grouped[key].amount += t.amount
        else:
            grouped[key] = Transfer(t.tx, t.src, t.dst, t.asset, t.amount, t.ts)
    return list(grouped.values())


def sweep_target(address: str, history: dict, registry: Registry) -> tuple[str, float] | None:
    """Exchange deposit addresses forward almost everything to one exchange wallet.

    Returns (exchange wallet, share of outflow) when that pattern is present.
    """
    # Counted per transfer, because amounts in different assets are not comparable.
    totals: dict[str, int] = defaultdict(int)
    for t in outgoing_transfers(address, history, 0):
        totals[t.dst] += 1
    count = sum(totals.values())
    if count < 2:  # one transfer is not a pattern
        return None
    destination, hits = max(totals.items(), key=lambda item: item[1])
    entity = registry.entity(destination)
    share = hits / count
    if entity and entity.category == "exchange" and share >= DEPOSIT_SWEEP_SHARE:
        return destination, share
    return None


def _confidence(hops: int, deposit_seen: bool, share_of_traced: float) -> tuple[str, float]:
    """A simple transparent rule, not a statistical probability.

    Fewer hops, a recognisable deposit-address pattern, and a larger share of the wallet's
    outflow all make the link to the exchange more direct.
    """
    points = {1: 0.55, 2: 0.45, 3: 0.3}.get(hops, 0.2)
    points += 0.2 if deposit_seen else 0.0
    points += 0.25 * min(1.0, share_of_traced)
    points = min(points, 0.95)
    return ("high" if points >= 0.7 else "medium" if points >= 0.45 else "low"), round(points, 2)


def _short_route(route: list[Transfer]) -> list[dict]:
    return [{"tx": t.tx, "from": t.src, "to": t.dst, "asset": t.asset, "amount": t.amount, "ts": t.ts} for t in route]


async def trace(
    client: BlockscoutClient,
    registry: Registry,
    start: str,
    since_ts: int = 0,
    max_hops: int = TRACE_MAX_HOPS,
) -> AsyncIterator[dict]:
    """Yield progress events as the trace runs. The last event has type 'done'."""
    start = start.lower()
    # The first hop follows every asset; later hops stay on the asset that arrived.
    queue: list[Frontier] = [Frontier(start, 0, None, since_ts, float("inf"))]
    seen: dict[str, dict] = {}
    edges: list[dict] = []
    attributed: list[dict] = []
    terminals: list[dict] = []
    visited: set[tuple[str, str | None]] = set()
    traced_out: dict[str, float] = defaultdict(float)
    limits_hit: list[str] = []

    def add_node(address: str, hop: int, kind: str, name: str | None = None, flags: list[str] | None = None) -> dict:
        node = seen.get(address)
        if node is None:
            node = {"id": address, "hop": hop, "kind": kind, "name": name, "flags": flags or []}
            seen[address] = node
        return node

    add_node(start, 0, "suspect", flags=registry.flags(start))
    yield {"type": "node", "node": seen[start]}

    while queue:
        level, queue = queue, []
        hop = level[0].hop
        yield {"type": "status", "message": f"Reading {len(level)} address(es) at hop {hop}"}

        addresses = list({f.address for f in level})
        fetched = await asyncio.gather(*[client.history(a) for a in addresses], return_exceptions=True)
        histories = dict(zip(addresses, fetched))

        next_level: list[Frontier] = []
        for item in level:
            history = histories[item.address]
            if isinstance(history, Exception):
                limits_hit.append(f"Could not read {item.address}: {history}")
                continue
            if item.address != start and max(len(history["txs"]), len(history["tokens"])) >= min(TRACE_HIGH_ACTIVITY, HISTORY_CAP):
                seen[item.address]["kind"] = "high_activity"
                terminals.append({"address": item.address, "kind": "high_activity", "route": _short_route(item.route),
                                  "asset": item.asset, "amount": item.route_amount})
                yield {"type": "node", "node": seen[item.address]}
                continue

            if item.address == start and max(len(history["txs"]), len(history["tokens"])) >= HISTORY_CAP:
                limits_hit.append(f"The suspect wallet is busy, so only its latest {HISTORY_CAP} transfers per type were traced")

            transfers = outgoing_transfers(item.address, history, item.arrived_ts)
            if item.asset is not None:
                transfers = [t for t in transfers if t.asset == item.asset]
            edges_here = sorted(aggregate(transfers), key=lambda t: -t.amount)

            if item.address != start:
                target = sweep_target(item.address, history, registry)
                if target and item.route:
                    exchange_wallet, share = target
                    entity = registry.entity(exchange_wallet)
                    seen[item.address]["kind"] = "deposit_candidate"
                    seen[item.address]["name"] = f"Likely {entity.entity} deposit address"
                    yield {"type": "node", "node": seen[item.address]}

            for t in edges_here[:TRACE_TOP_K]:
                amount = t.amount if item.route_amount == float("inf") else min(t.amount, item.route_amount)
                route = [*item.route, Transfer(t.tx, t.src, t.dst, t.asset, amount, t.ts)]
                if item.route_amount == float("inf"):
                    traced_out[t.asset] += t.amount
                entity = registry.entity(t.dst)
                is_new = t.dst not in seen
                if entity:
                    add_node(t.dst, hop + 1, entity.category, f"{entity.name}")
                else:
                    add_node(t.dst, hop + 1, "wallet", flags=registry.flags(t.dst))
                edge = {"source": t.src, "target": t.dst, "asset": t.asset, "amount": amount, "tx": t.tx, "ts": t.ts}
                edges.append(edge)
                if is_new:
                    yield {"type": "node", "node": seen[t.dst]}
                yield {"type": "edge", "edge": edge}

                if entity and entity.category == "exchange":
                    hit = {"exchange": entity.entity, "wallet": t.dst, "wallet_name": entity.name, "hops": hop + 1,
                           "asset": t.asset, "amount": amount, "route": _short_route(route),
                           "deposit_address": item.address if seen[item.address]["kind"] == "deposit_candidate" else None}
                    attributed.append(hit)
                    yield {"type": "exchange", "hit": hit}
                    continue
                if entity:
                    terminals.append({"address": t.dst, "kind": entity.category, "name": entity.name,
                                      "route": _short_route(route), "asset": t.asset, "amount": amount})
                    continue
                if hop + 1 >= max_hops:
                    continue
                key = (t.dst, t.asset)
                if key in visited:
                    continue
                visited.add(key)
                if len(seen) >= TRACE_MAX_NODES:
                    if "address limit" not in limits_hit:
                        limits_hit.append("address limit")
                    continue
                next_level.append(Frontier(t.dst, hop + 1, t.asset, t.ts, amount, route))
            if len(edges_here) > TRACE_TOP_K:
                limits_hit.append(f"{item.address} had {len(edges_here)} destinations; followed the largest {TRACE_TOP_K}")
        queue = next_level

    summary = summarise(attributed, traced_out)
    yield {
        "type": "done",
        "result": {
            "start": start,
            "since_ts": since_ts,
            "nodes": list(seen.values()),
            "edges": edges,
            "exchanges": summary,
            "routes": attributed,
            "terminals": terminals,
            "outflow_traced": dict(traced_out),
            "limits": limits_hit,
        },
    }


def summarise(hits: list[dict], traced_out: dict[str, float]) -> list[dict]:
    """Per exchange, per asset. Amounts in different assets are never added together."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for hit in hits:
        groups[hit["exchange"]].append(hit)
    summary = []
    for exchange, items in groups.items():
        assets: dict[str, float] = defaultdict(float)
        for item in items:
            assets[item["asset"]] += item["amount"]
        share = max(min(1.0, amount / traced_out[asset]) if traced_out.get(asset) else 0.0 for asset, amount in assets.items())
        min_hops = min(i["hops"] for i in items)
        deposits = sorted({i["deposit_address"] for i in items if i["deposit_address"]})
        level, points = _confidence(min_hops, bool(deposits), share)
        summary.append({
            "exchange": exchange,
            "confidence": level,
            "confidence_score": points,
            "min_hops": min_hops,
            "assets": dict(assets),
            "share_of_traced_outflow": share,
            "deposit_addresses": deposits,
            "wallets": sorted({i["wallet"] for i in items}),
            "routes": len(items),
        })
    return sorted(summary, key=lambda s: -s["confidence_score"])
