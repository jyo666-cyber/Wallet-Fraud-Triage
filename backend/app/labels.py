"""Address registry built from public label lists.

Two separate questions are answered here:
  * who is this address?  (exchange, mixer, bridge, DEX), used to stop and attribute a trace
  * has it been flagged?  (phishing/scam/sanctions lists), reported as evidence and also
    used as training labels, but never fed to the model as a feature
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from functools import lru_cache

from .config import LABEL_DIR

# Display name -> pattern matched at the START of an Etherscan name tag ("Binance 14").
EXCHANGES = {
    "Binance": r"binance",
    "Coinbase": r"coinbase",
    "Kraken": r"kraken",
    "OKX": r"okx|okex",
    "Huobi / HTX": r"huobi|htx",
    "Bitfinex": r"bitfinex",
    "KuCoin": r"kucoin",
    "Gate.io": r"gate\.?io",
    "Bybit": r"bybit",
    "Bitstamp": r"bitstamp",
    "Gemini": r"gemini",
    "Crypto.com": r"crypto\.com",
    "Bittrex": r"bittrex",
    "Poloniex": r"poloniex",
    "MEXC": r"mexc|mxc",
    "Bitget": r"bitget",
    "Upbit": r"upbit",
    "Bithumb": r"bithumb",
    "WazirX": r"wazirx",
    "CoinDCX": r"coindcx",
    "BitMEX": r"bitmex",
    "Deribit": r"deribit",
    "HitBTC": r"hitbtc",
    "Korbit": r"korbit",
    "Luno": r"luno",
    "BitMart": r"bitmart",
    "FTX": r"ftx",
    "ShapeShift": r"shapeshift",
    "ChangeNOW": r"changenow",
    "ZB.com": r"zb\.com",
}
_EXCHANGE_RES = {k: re.compile(rf"^({v})\b", re.I) for k, v in EXCHANGES.items()}
# Name tags that mention an exchange but are not wallets controlled by that exchange.
_NOT_EXCHANGE_WALLET = re.compile(
    r"token|peg|eth2|staking|bridge|alameda|exploit|hacker|fake|phish|scam|nft|delegate|"
    r"validator|multisend|contract|smart chain|lp\b|wrapped|deployer|unlock|commerce|funder",
    re.I,
)
_DEX_LABELS = {"dex", "uniswap", "sushiswap", "balancer", "bancor", "curve-fi", "1inch", "0x-protocol-ecosystem"}
# These tags mark affected users or token-level blocks, not fraudsters.
_NEVER_FRAUD_LABELS = {"take-action", "blocked"}


@dataclass(frozen=True)
class Entity:
    category: str  # exchange | mixer | bridge | dex
    entity: str
    name: str


@dataclass
class Registry:
    entities: dict[str, Entity]
    flagged: dict[str, list[str]]  # address -> ["source: detail", ...]
    sanctioned: set[str]

    def entity(self, address: str) -> Entity | None:
        return self.entities.get(address.lower())

    def flags(self, address: str) -> list[str]:
        return self.flagged.get(address.lower(), [])


def _classify(name: str, labels: list[str]) -> Entity | None:
    labelset = set(labels)
    if "tornado-cash" in labelset or "ethereum-mixer" in labelset:
        if "token" not in name.lower():
            return Entity("mixer", "Tornado Cash" if "tornado-cash" in labelset else "Mixer", name)
        return None
    for entity, pattern in _EXCHANGE_RES.items():
        if pattern.search(name) and not _NOT_EXCHANGE_WALLET.search(name):
            return Entity("exchange", entity, name)
    if "bridge" in labelset and "token" not in name.lower():
        return Entity("bridge", name.split(":")[0] or "Bridge", name)
    if labelset & _DEX_LABELS and re.search(r"router|exchange|aggregator|swap", name, re.I) and "token" not in name.lower():
        return Entity("dex", name.split(":")[0] or "DEX", name)
    return None


def _read_json(name: str):
    path = LABEL_DIR / name
    return json.loads(path.read_text(encoding="utf8")) if path.exists() else None


def _read_csv(name: str) -> list[dict]:
    path = LABEL_DIR / name
    if not path.exists():
        return []
    with path.open(encoding="utf8", newline="") as fh:
        return list(csv.DictReader(fh))


@lru_cache(maxsize=1)
def get_registry() -> Registry:
    entities: dict[str, Entity] = {}
    flagged: dict[str, list[str]] = {}
    sanctioned: set[str] = set()

    def flag(address: str, why: str) -> None:
        flagged.setdefault(address.lower(), []).append(why)

    for address, meta in (_read_json("etherscan_labels.json") or {}).items():
        address, name, labels = address.lower(), meta.get("name") or "", meta.get("labels") or []
        entity = _classify(name, labels)
        if entity:
            entities[address] = entity
        if "ofac-sanctions-lists" in labels:
            sanctioned.add(address)
            flag(address, "OFAC sanctions list (via Etherscan labels)")

    for row in _read_csv("forta_phishing_scams.csv"):
        flag(row["address"], f"Etherscan phish-hack: {row.get('etherscan_tag') or 'untagged'}")
    for row in _read_csv("forta_malicious_labels.csv"):
        flag(row["banned_address"], f"Etherscan malicious label: {row.get('wallet_tag') or 'untagged'}")
    for row in _read_json("mew_darklist.json") or []:
        flag(row["address"], f"MyEtherWallet darklist: {row.get('comment') or 'no comment'}")
    for address in _read_json("scamsniffer.json") or []:
        flag(address, "ScamSniffer blacklist")

    # An address a list also knows as a major service is a labelling conflict, not a scam wallet.
    for address in list(flagged):
        if address in entities and address not in sanctioned:
            del flagged[address]
    return Registry(entities, flagged, sanctioned)
