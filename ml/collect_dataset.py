"""Build the labelled wallet dataset from live on-chain histories.

Positives: wallets on public phishing/scam lists.
Controls : random wallets active on-chain close to the time each positive first appeared, and in
           the same activity band. Matching on time stops the era separating the classes. Matching
           on activity is needed because sampling from blocks strongly favours busy wallets.

Output is one JSON line per wallet, appended as it goes, so a stopped run resumes cleanly:
    python ml/collect_dataset.py --positives 800 --controls-per-positive 2
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.chain import BlockscoutClient, ChainError, estimate_block  # noqa: E402
from app.config import LABEL_DIR, MIN_TX_FOR_SCORING, RAW_DIR  # noqa: E402
from app.features import activity_band, activity_count  # noqa: E402
from app.labels import get_registry  # noqa: E402

GH = "https://raw.githubusercontent.com"
LABEL_FILES = {
    "mew_darklist.json": f"{GH}/MyEtherWallet/ethereum-lists/master/src/addresses/addresses-darklist.json",
    "scamsniffer.json": f"{GH}/scamsniffer/scam-database/main/blacklist/address.json",
    "etherscan_labels.json": f"{GH}/brianleect/etherscan-labels/main/data/etherscan/combined/combinedAllLabels.json",
    "forta_phishing_scams.csv": f"{GH}/forta-network/labelled-datasets/main/labels/1/phishing_scams.csv",
    "forta_malicious_labels.csv": f"{GH}/forta-network/labelled-datasets/main/labels/1/etherscan_malicious_labels.csv",
}
OUT = RAW_DIR / "wallets.jsonl.gz"
BLOCKS_PER_JOB = 6
CANDIDATES_PER_BLOCK = 25
FETCHES_PER_JOB = 4


def fetch_labels() -> None:
    LABEL_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in LABEL_FILES.items():
        path = LABEL_DIR / name
        if not path.exists():
            print("downloading", name, flush=True)
            urllib.request.urlretrieve(url, path)


def load_done() -> dict[str, dict]:
    """Read earlier progress. A stopped run can leave a cut-off gzip block at the end of the file,
    and anything appended after that would be unreadable, so the file is rewritten clean first."""
    done: dict[str, dict] = {}
    if not OUT.exists():
        return done
    lines: list[str] = []
    damaged = False
    try:
        with gzip.open(OUT, "rt", encoding="utf8") as fh:
            for line in fh:
                row = json.loads(line)
                lines.append(line)
                done[row["address"]] = {k: row.get(k) for k in ("label", "anchor_ts", "pair", "skip")}
                if row.get("history"):
                    done[row["address"]]["band"] = activity_band(activity_count(row["history"]))
    except (EOFError, OSError, json.JSONDecodeError):
        damaged = True
    if damaged:
        temp = OUT.with_suffix(".tmp")
        with gzip.open(temp, "wt", encoding="utf8") as fh:
            fh.writelines(lines)
        temp.replace(OUT)
        print(f"repaired {OUT.name}: kept {len(lines)} rows", flush=True)
    return done


class Writer:
    def __init__(self):
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        self.fh = gzip.open(OUT, "at", encoding="utf8")
        self.count = 0

    def write(self, row: dict) -> None:
        # Reopened every 25 rows to close a gzip member, so a killed run loses at most 25 rows.
        self.fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        self.count += 1
        if self.count % 25 == 0:
            self.fh.close()
            self.fh = gzip.open(OUT, "at", encoding="utf8")

    def close(self) -> None:
        self.fh.close()


def positive_pool(rng: random.Random) -> list[tuple[str, str]]:
    """Wallet candidates per source. Known contracts are dropped up front to save API calls."""
    pool: dict[str, str] = {}
    with (LABEL_DIR / "forta_phishing_scams.csv").open(encoding="utf8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("is_contract", "").strip().lower() == "false":
                pool.setdefault(row["address"].lower(), "etherscan_phish")
    with (LABEL_DIR / "forta_malicious_labels.csv").open(encoding="utf8", newline="") as fh:
        for row in csv.DictReader(fh):
            pool.setdefault(row["banned_address"].lower(), "etherscan_malicious")
    for row in json.loads((LABEL_DIR / "mew_darklist.json").read_text(encoding="utf8")):
        pool.setdefault(row["address"].lower(), "mew_darklist")
    for address in json.loads((LABEL_DIR / "scamsniffer.json").read_text(encoding="utf8")):
        pool[address.lower()] = "scamsniffer"

    registry = get_registry()
    items = [(a, s) for a, s in pool.items() if a in registry.flagged and registry.entity(a) is None]
    rng.shuffle(items)
    # Round-robin across sources, so the largest list does not swallow the sample.
    by_source: dict[str, list[str]] = {}
    for address, source in items:
        by_source.setdefault(source, []).append(address)
    print("candidate wallets by source:", {k: len(v) for k, v in by_source.items()}, flush=True)
    ordered: list[tuple[str, str]] = []
    while any(by_source.values()):
        for source, addresses in by_source.items():
            if addresses:
                ordered.append((addresses.pop(), source))
    return ordered


async def fetch_wallet(client: BlockscoutClient, address: str) -> tuple[dict | None, str | None]:
    history = await client.history(address, skip_contracts=True)
    if history["is_contract"]:
        return None, "contract"
    if activity_count(history) < MIN_TX_FOR_SCORING:
        return None, "too_little_history"
    return history, None


def first_seen(history: dict) -> int:
    stamps = [t["ts"] for key in ("txs", "internal", "tokens") for t in history[key] if t["ts"]]
    return min(stamps) if stamps else 0


async def collect_positives(client, writer, done, target, rng) -> None:
    have = sum(1 for d in done.values() if d["label"] == 1 and not d["skip"])
    pool = [(a, s) for a, s in positive_pool(rng) if a not in done]
    print(f"positives: have {have}, want {target}", flush=True)
    idx, lock, started = 0, asyncio.Lock(), time.time()

    async def worker():
        nonlocal idx, have
        while True:
            async with lock:
                if have >= target or idx >= len(pool):
                    return
                address, source = pool[idx]
                idx += 1
            try:
                history, skip = await fetch_wallet(client, address)
            except ChainError as exc:
                print("skip", address, exc, flush=True)
                continue
            async with lock:
                if skip:
                    writer.write({"address": address, "label": 1, "source": source, "skip": skip})
                    done[address] = {"label": 1, "skip": skip, "anchor_ts": None, "pair": None}
                    continue
                anchor = first_seen(history)
                writer.write({"address": address, "label": 1, "source": source, "anchor_ts": anchor,
                              "pair": address, "history": history})
                done[address] = {"label": 1, "anchor_ts": anchor, "pair": address, "skip": None,
                                 "band": activity_band(activity_count(history))}
                have += 1
                if have % 50 == 0:
                    print(f"  positives {have}/{target} ({time.time() - started:.0f}s, tried {idx})", flush=True)

    await asyncio.gather(*[worker() for _ in range(5)])
    print(f"positives done: {have}", flush=True)


async def sample_candidates(client, ts: int, rng: random.Random) -> list[str]:
    """Plain externally-owned wallets seen in a random block close to the given time."""
    registry = get_registry()
    offset = rng.randint(-30 * 86400, 30 * 86400)
    block = estimate_block(max(1_438_300_000, min(int(time.time()) - 86400, ts + offset)))
    candidates: list[str] = []
    for tx in await client.block_transactions(block):
        for side in ("from", "to"):
            party = tx.get(side) or {}
            address = (party.get("hash") or "").lower()
            if address and not party.get("is_contract") and not registry.entity(address) and address not in registry.flagged:
                candidates.append(address)
    rng.shuffle(candidates)
    return candidates


async def collect_controls(client, writer, done, per_positive, rng) -> None:
    positives = {a: d for a, d in done.items() if d["label"] == 1 and not d["skip"] and d["anchor_ts"]}
    counts: dict[str, int] = {}
    for d in done.values():
        pair = positives.get(d["pair"])
        if d["label"] == 0 and not d["skip"] and pair and d.get("band") == pair["band"]:
            counts[d["pair"]] = counts.get(d["pair"], 0) + 1
    jobs = [(a, d["anchor_ts"], d["band"]) for a, d in positives.items()
            for _ in range(max(0, per_positive - counts.get(a, 0)))]
    rng.shuffle(jobs)
    print(f"matched controls: {sum(counts.values())} already, {len(jobs)} to go", flush=True)
    idx, lock, finished, unfilled, started = 0, asyncio.Lock(), 0, 0, time.time()
    checked: set[str] = set()

    async def matching_candidate(ts: int, band: int) -> str | None:
        """Screen a few random blocks with the one-call counter before paying for a full history."""
        for _ in range(BLOCKS_PER_JOB):
            for address in (await sample_candidates(client, ts, rng))[:CANDIDATES_PER_BLOCK]:
                async with lock:
                    if address in done or address in checked:
                        continue
                    checked.add(address)
                estimate = await client.activity_estimate(address)
                if estimate is not None and activity_band(estimate) == band:
                    return address
        return None

    async def worker():
        nonlocal idx, finished, unfilled
        while True:
            async with lock:
                if idx >= len(jobs):
                    return
                pair, ts, band = jobs[idx]
                idx += 1
            for _ in range(FETCHES_PER_JOB):
                try:
                    address = await matching_candidate(ts, band)
                    if not address:
                        break
                    async with lock:
                        done[address] = {"label": 0, "skip": "pending", "anchor_ts": ts, "pair": pair}
                    history, skip = await fetch_wallet(client, address)
                except ChainError as exc:
                    print("skip control", exc, flush=True)
                    continue
                # The counter leaves out contract payments, so the full history has the final say.
                if not skip and activity_band(activity_count(history)) != band:
                    skip = "band_mismatch"
                async with lock:
                    if skip:
                        writer.write({"address": address, "label": 0, "source": "random_active", "skip": skip})
                        done[address]["skip"] = skip
                        continue
                    writer.write({"address": address, "label": 0, "source": "random_active", "anchor_ts": ts,
                                  "pair": pair, "history": history})
                    done[address].update(skip=None, band=band)
                    finished += 1
                    if finished % 25 == 0:
                        print(f"  controls {finished}/{len(jobs)} ({time.time() - started:.0f}s, screened {len(checked)})", flush=True)
                    break
            else:
                unfilled += 1
                continue
            if not address:
                unfilled += 1

    await asyncio.gather(*[worker() for _ in range(5)])
    print(f"controls done: {finished}, left unfilled: {unfilled}", flush=True)


async def main(args) -> None:
    rng = random.Random(args.seed)
    fetch_labels()
    done = load_done()
    writer = Writer()
    # Paced below the API limit, so that the running app can make live calls at the same time.
    client = BlockscoutClient(rate_per_sec=2.6)
    try:
        await collect_positives(client, writer, done, args.positives, rng)
        await collect_controls(client, writer, done, args.controls_per_positive, rng)
    finally:
        writer.close()
        await client.aclose()
    print("COLLECTION COMPLETE", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--positives", type=int, default=800)
    parser.add_argument("--controls-per-positive", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    asyncio.run(main(parser.parse_args()))
