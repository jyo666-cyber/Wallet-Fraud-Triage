"""Wallet behaviour features.

This single function is used for both training and live scoring, so the model sees the
same definitions in both. It deliberately has no absolute timestamps and no list
membership: the model should learn behaviour, not when a wallet existed or which list
it appears on.
"""
from __future__ import annotations

import math
from statistics import median, pstdev

from .config import HISTORY_CAP

WEI = 1e18
GWEI = 1e9
STABLECOINS = {
    "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
    "0x6b175474e89094c44da98b954eedeac495271d0f",  # DAI
}

# name -> (plain-language description, unit used when explaining an alert)
FEATURES: dict[str, tuple[str, str]] = {
    "log_tx_out": ("Outgoing transactions", "log"),
    "log_tx_in": ("Incoming transactions", "log"),
    "log_internal_in": ("Incoming contract payments", "log"),
    "out_share": ("Share of transactions that are outgoing", "ratio"),
    "log_uniq_out": ("Distinct addresses paid", "log"),
    "log_uniq_in": ("Distinct addresses paying in", "log"),
    "fan_in_ratio": ("Share of counterparties that only send funds in", "ratio"),
    "repeat_out_ratio": ("Repeat payments to the same address", "ratio"),
    "log_eth_in": ("Total ETH received", "log"),
    "log_eth_out": ("Total ETH sent", "log"),
    "log_eth_in_median": ("Typical ETH received per transaction", "log"),
    "log_eth_out_median": ("Typical ETH sent per transaction", "log"),
    "log_eth_in_max": ("Largest ETH receipt", "log"),
    "log_eth_out_max": ("Largest ETH payment", "log"),
    "out_concentration": ("Share of outflow in the largest payment", "ratio"),
    "pass_through_ratio": ("How much received ETH was passed straight on", "ratio"),
    "zero_value_ratio": ("Zero-value transactions", "ratio"),
    "log_gas_price": ("Average gas price paid", "log"),
    "log_fee": ("Average transaction fee", "log"),
    "failed_ratio": ("Failed transactions", "ratio"),
    "contract_call_ratio": ("Transactions calling a contract", "ratio"),
    "log_span_days": ("Length of activity history", "log"),
    "log_interval_median": ("Typical time between transactions", "log"),
    "interval_cv": ("Irregularity of transaction timing", "num"),
    "log_max_tx_hour": ("Busiest hour of activity", "log"),
    "active_day_ratio": ("Share of days with activity", "ratio"),
    "log_first_out_delay": ("Delay before first outgoing payment", "log"),
    "log_hold_median": ("Typical time funds sit before moving on", "log"),
    "recent_change": ("Change in activity over the last 7 active days", "num"),
    "log_token_transfers": ("Token transfers", "log"),
    "log_uniq_tokens": ("Distinct tokens handled", "log"),
    "token_out_share": ("Share of token transfers that are outgoing", "ratio"),
    "log_token_counterparties": ("Distinct token counterparties", "log"),
    "stablecoin_ratio": ("Share of token transfers in stablecoins", "ratio"),
    "history_truncated": ("History exceeds the analysis window", "flag"),
}
FEATURE_NAMES = list(FEATURES)
ACTIVITY_BAND_EDGES = (10, 30, 100, 300)
ACTIVITY_BAND_NAMES = ("3-9 items", "10-29 items", "30-99 items", "100-299 items", "300+ items")


def _log(x: float) -> float:
    return math.log1p(max(0.0, x))


def _ratio(a: float, b: float) -> float:
    return a / b if b else 0.0


def activity_count(history: dict) -> int:
    return len(history.get("txs", [])) + len(history.get("internal", [])) + len(history.get("tokens", []))


def activity_band(count: int) -> int:
    """Coarse activity level. Controls are matched to flagged wallets on this, so that
    being quiet or busy cannot by itself separate the two classes."""
    return sum(count >= edge for edge in ACTIVITY_BAND_EDGES)


def extract_features(address: str, history: dict, cap: int = HISTORY_CAP) -> dict[str, float]:
    me = address.lower()
    txs = sorted((t for t in history.get("txs", [])), key=lambda t: t["ts"])
    internal = [t for t in history.get("internal", []) if not t.get("e")]
    tokens = history.get("tokens", [])

    out = [t for t in txs if t["f"] == me]
    inc = [t for t in txs if t["t"] == me]
    int_in = [t for t in internal if t["t"] == me]
    int_out = [t for t in internal if t["f"] == me]

    # A failed transaction moved no value, but it still counts as behaviour and paid gas.
    out_ok = [t for t in out if not t["e"]]
    inc_ok = [t for t in inc if not t["e"]]
    out_vals = [t["v"] / WEI for t in out_ok] + [t["v"] / WEI for t in int_out]
    in_vals = [t["v"] / WEI for t in inc_ok] + [t["v"] / WEI for t in int_in]
    out_pos = [v for v in out_vals if v > 0]
    in_pos = [v for v in in_vals if v > 0]
    total_out, total_in = sum(out_vals), sum(in_vals)

    uniq_out = {t["t"] for t in out if t["t"]}
    uniq_in = {t["f"] for t in inc} | {t["f"] for t in int_in}

    times = sorted(t["ts"] for t in txs) or sorted(t["ts"] for t in tokens) or [0]
    gaps = [b - a for a, b in zip(times, times[1:])]
    span_s = times[-1] - times[0]

    hours: dict[int, int] = {}
    days: set[int] = set()
    for ts in times:
        hours[ts // 3600] = hours.get(ts // 3600, 0) + 1
        days.add(ts // 86400)

    in_times = sorted([t["ts"] for t in inc_ok if t["v"] > 0] + [t["ts"] for t in int_in if t["v"] > 0])
    out_times = sorted(t["ts"] for t in out_ok if t["v"] > 0)
    first_out_delay = 0.0
    holds: list[float] = []
    if in_times and out_times:
        first_out_delay = max(0, out_times[0] - in_times[0]) / 3600
        j = 0
        for ts in in_times:
            while j < len(out_times) and out_times[j] < ts:
                j += 1
            if j == len(out_times):
                break
            holds.append((out_times[j] - ts) / 3600)

    # Activity in the wallet's final 7 days against the 7 days before them.
    end = times[-1]
    last7 = sum(1 for ts in times if ts > end - 7 * 86400)
    prev7 = sum(1 for ts in times if end - 14 * 86400 < ts <= end - 7 * 86400)

    fees = [t["gu"] * t["gp"] / WEI for t in out]
    gas_prices = [t["gp"] / GWEI for t in out]
    tok_out = [t for t in tokens if t["f"] == me]
    tok_cp = {t["t"] if t["f"] == me else t["f"] for t in tokens}

    n_tx = len(txs)
    return {
        "log_tx_out": _log(len(out)),
        "log_tx_in": _log(len(inc)),
        "log_internal_in": _log(len(int_in)),
        "out_share": _ratio(len(out), n_tx),
        "log_uniq_out": _log(len(uniq_out)),
        "log_uniq_in": _log(len(uniq_in)),
        "fan_in_ratio": _ratio(len(uniq_in - uniq_out), len(uniq_in | uniq_out)),
        "repeat_out_ratio": 1 - _ratio(len(uniq_out), len(out)) if out else 0.0,
        "log_eth_in": _log(total_in),
        "log_eth_out": _log(total_out),
        "log_eth_in_median": _log(median(in_pos)) if in_pos else 0.0,
        "log_eth_out_median": _log(median(out_pos)) if out_pos else 0.0,
        "log_eth_in_max": _log(max(in_pos)) if in_pos else 0.0,
        "log_eth_out_max": _log(max(out_pos)) if out_pos else 0.0,
        "out_concentration": _ratio(max(out_pos), total_out) if out_pos else 0.0,
        "pass_through_ratio": _ratio(min(total_in, total_out), max(total_in, total_out)),
        "zero_value_ratio": _ratio(sum(1 for t in txs if t["v"] == 0), n_tx),
        "log_gas_price": _log(sum(gas_prices) / len(gas_prices)) if gas_prices else 0.0,
        "log_fee": _log(1000 * sum(fees) / len(fees)) if fees else 0.0,
        "failed_ratio": _ratio(sum(1 for t in txs if t["e"]), n_tx),
        "contract_call_ratio": _ratio(sum(1 for t in out if t["c"]), len(out)),
        "log_span_days": _log(span_s / 86400),
        "log_interval_median": _log(median(gaps) / 3600) if gaps else 0.0,
        "interval_cv": _ratio(pstdev(gaps), sum(gaps) / len(gaps)) if len(gaps) > 1 and sum(gaps) else 0.0,
        "log_max_tx_hour": _log(max(hours.values())),
        "active_day_ratio": _ratio(len(days), span_s / 86400 + 1),
        "log_first_out_delay": _log(first_out_delay),
        "log_hold_median": _log(median(holds)) if holds else 0.0,
        "recent_change": _ratio(last7 - prev7, last7 + prev7),
        "log_token_transfers": _log(len(tokens)),
        "log_uniq_tokens": _log(len({t["a"] for t in tokens})),
        "token_out_share": _ratio(len(tok_out), len(tokens)),
        "log_token_counterparties": _log(len(tok_cp)),
        "stablecoin_ratio": _ratio(sum(1 for t in tokens if t["a"] in STABLECOINS), len(tokens)),
        "history_truncated": float(max(len(txs), len(tokens), len(history.get("internal", []))) >= cap),
    }
