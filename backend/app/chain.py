"""Async client for the public Blockscout Ethereum v2 API (no API key required).

The v2 API allows 180 requests a minute per IP. Requests are paced below that, and when a
429 does arrive, every request waits for the window the server reports.
"""
from __future__ import annotations

import asyncio
import bisect
import random
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import BLOCKSCOUT_URL, HISTORY_CAP, MAX_CONCURRENCY, RATE_PER_SEC

PAGE_SIZE = 50
CACHE_TTL_S = 600

# (block, unix time) anchors at known network upgrades, for estimating a block from a date.
_BLOCK_ANCHORS = [
    (1, 1438269988),
    (4_370_000, 1508131331),
    (7_280_000, 1551383524),
    (10_853_627, 1600000000),
    (12_965_000, 1628166822),
    (15_537_394, 1663224179),
]
_SECONDS_PER_BLOCK_NOW = 12


def estimate_block(ts: int) -> int:
    """Approximate block at a time. Good to within days, which is enough for sampling."""
    times = [t for _, t in _BLOCK_ANCHORS]
    if ts >= times[-1]:
        return _BLOCK_ANCHORS[-1][0] + (ts - times[-1]) // _SECONDS_PER_BLOCK_NOW
    i = max(1, bisect.bisect_right(times, ts))
    (b0, t0), (b1, t1) = _BLOCK_ANCHORS[i - 1], _BLOCK_ANCHORS[i]
    return b0 + int((b1 - b0) * (max(ts, t0) - t0) / (t1 - t0))


class ChainError(RuntimeError):
    """The chain data source could not answer after retries."""


class BlockscoutClient:
    def __init__(self, concurrency: int = MAX_CONCURRENCY, timeout: float = 45.0, rate_per_sec: float = RATE_PER_SEC):
        self._sem = asyncio.Semaphore(concurrency)
        self._client = httpx.AsyncClient(
            base_url=BLOCKSCOUT_URL,
            timeout=timeout,
            headers={"User-Agent": "wallet-risk-triage-academic-project/1.0"},
        )
        self._interval = 1.0 / rate_per_sec
        self._next_slot = 0.0
        self._resume_at = 0.0
        self._slot_lock = asyncio.Lock()
        self._cache: dict[str, tuple[float, dict]] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _pace(self) -> None:
        async with self._slot_lock:
            now = time.monotonic()
            slot = max(now, self._next_slot, self._resume_at)
            self._next_slot = slot + self._interval
        if slot > now:
            await asyncio.sleep(slot - now)

    async def _get(self, path: str, params: dict | None = None, retries: int = 6) -> Any:
        last = "no attempt"
        for attempt in range(retries):
            await self._pace()
            async with self._sem:
                try:
                    r = await self._client.get(path, params=params)
                except (httpx.TransportError, ValueError) as exc:
                    last = f"{type(exc).__name__}: {exc}"
                    r = None
            if r is not None:
                if r.status_code == 200:
                    return r.json()
                if r.status_code in (404, 422):
                    return None
                last = f"HTTP {r.status_code}"
                if r.status_code == 429:
                    try:
                        wait = int(r.headers.get("x-ratelimit-reset", "5000")) / 1000
                    except ValueError:
                        wait = 5.0
                    self._resume_at = max(self._resume_at, time.monotonic() + min(wait, 120) + random.random())
                    continue
            await asyncio.sleep(min(20, 2**attempt) + random.random())
        raise ChainError(f"{path} failed after {retries} attempts ({last})")

    async def _pages(self, path: str, cap: int, params: dict | None = None) -> list[dict]:
        """Newest-first items across pages, stopping at the cap."""
        items: list[dict] = []
        query = dict(params or {})
        while len(items) < cap:
            data = await self._get(path, query)
            if not data:
                break
            items.extend(data.get("items") or [])
            next_page = data.get("next_page_params")
            if not next_page:
                break
            query = {**(params or {}), **next_page}
        return items[:cap]

    async def transaction(self, tx_hash: str) -> dict | None:
        return await self._get(f"/api/v2/transactions/{tx_hash}")

    async def block_transactions(self, block: int) -> list[dict]:
        data = await self._get(f"/api/v2/blocks/{block}/transactions")
        return (data or {}).get("items") or []

    async def activity_estimate(self, address: str, cap: int = HISTORY_CAP) -> int | None:
        """One-call estimate of a wallet's capped activity count, cheaper than fetching its history."""
        data = await self._get(f"/api/v2/addresses/{address}/counters")
        if not data:
            return None
        return min(_int(data.get("transactions_count")), cap) + min(_int(data.get("token_transfers_count")), cap)

    async def history(self, address: str, cap: int = HISTORY_CAP, skip_contracts: bool = False) -> dict:
        """Recent normal, internal and token activity in compact form, plus an is_contract flag."""
        address = address.lower()
        cached = self._cache.get(address)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_S and not skip_contracts:
            return cached[1]

        base = f"/api/v2/addresses/{address}"
        raw_txs = await self._pages(f"{base}/transactions", cap)
        is_contract = _contract_flag(address, raw_txs)
        if is_contract and skip_contracts:
            return {"is_contract": True, "txs": [], "internal": [], "tokens": []}

        raw_internal, raw_tokens = await asyncio.gather(
            self._pages(f"{base}/internal-transactions", cap),
            self._pages(f"{base}/token-transfers", cap, {"type": "ERC-20"}),
        )
        if is_contract is None:
            is_contract = _contract_flag(address, raw_internal) or _contract_flag(address, raw_tokens)
        result = {
            "is_contract": bool(is_contract),
            "txs": [compact_tx(t) for t in raw_txs],
            "internal": [compact_internal(t) for t in raw_internal],
            "tokens": [compact_token(t) for t in raw_tokens],
        }
        self._cache[address] = (time.monotonic(), result)
        return result


def _hash(party: Any) -> str:
    return ((party or {}).get("hash") or "").lower() if isinstance(party, dict) else ""


def _contract_flag(address: str, items: list[dict]) -> bool | None:
    for item in items:
        for side in ("from", "to"):
            party = item.get(side)
            if _hash(party) == address:
                return bool(party.get("is_contract"))
    return None


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _ts(value: Any) -> int:
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).timestamp())
    except ValueError:
        return 0


def compact_tx(t: dict) -> dict:
    return {
        "h": t.get("hash"),
        "f": _hash(t.get("from")),
        "t": _hash(t.get("to")),
        "v": _int(t.get("value")),
        "ts": _ts(t.get("timestamp")),
        "gu": _int(t.get("gas_used")),
        "gp": _int(t.get("gas_price")),
        "e": t.get("status") == "error" or t.get("result") not in (None, "success"),
        "c": (t.get("raw_input") or "0x") != "0x",
    }


def compact_internal(t: dict) -> dict:
    return {
        "h": t.get("transaction_hash"),
        "f": _hash(t.get("from")),
        "t": _hash(t.get("to")),
        "v": _int(t.get("value")),
        "ts": _ts(t.get("timestamp")),
        "e": t.get("success") is False,
    }


def compact_token(t: dict) -> dict:
    token = t.get("token") or {}
    total = t.get("total") or {}
    return {
        "h": t.get("transaction_hash"),
        "f": _hash(t.get("from")),
        "t": _hash(t.get("to")),
        "v": _int(total.get("value")),
        "d": _int(total.get("decimals") or token.get("decimals")),
        "ts": _ts(t.get("timestamp")),
        "s": token.get("symbol") or "",
        "a": (token.get("address_hash") or token.get("address") or "").lower(),
    }
