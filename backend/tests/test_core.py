"""Offline tests: no network and no trained model needed."""
import asyncio
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features import FEATURE_NAMES, activity_band, extract_features  # noqa: E402
from app.labels import Entity, Registry, _classify  # noqa: E402
from app.store import Store, canonical, sha256  # noqa: E402
from app.tracer import outgoing_transfers, sweep_target, trace  # noqa: E402

SUSPECT = "0x" + "a" * 40
MULE = "0x" + "b" * 40
DEPOSIT = "0x" + "c" * 40
HOT = "0x" + "d" * 40
MIXER = "0x" + "e" * 40
USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
FAKE = "0x" + "f" * 40


def tx(src, dst, eth, ts, error=False, h="0xtx"):
    return {"h": h, "f": src, "t": dst, "v": int(eth * 1e18), "ts": ts, "gu": 21000, "gp": 10**10, "e": error, "c": False}


def token(src, dst, amount, ts, contract=USDT, symbol="USDT"):
    return {"h": "0xtk", "f": src, "t": dst, "v": int(amount * 1e6), "d": 6, "ts": ts, "s": symbol, "a": contract}


def history(txs=(), tokens=(), internal=()):
    return {"txs": list(txs), "tokens": list(tokens), "internal": list(internal)}


REGISTRY = Registry(
    entities={HOT: Entity("exchange", "Binance", "Binance 14"), MIXER: Entity("mixer", "Tornado Cash", "Tornado.Cash: 1 ETH")},
    flagged={MULE: ["test list"]},
    sanctioned=set(),
)


class FakeClient:
    def __init__(self, histories):
        self.histories = histories

    async def history(self, address):
        return self.histories.get(address, history())


def run_trace(histories, since=0, **kw):
    async def go():
        return [e async for e in trace(FakeClient(histories), REGISTRY, SUSPECT, since, **kw)]
    events = asyncio.run(go())
    return events, events[-1]["result"]


# Features --------------------------------------------------------------------------------
def test_features_complete_and_finite_on_empty_history():
    features = extract_features(SUSPECT, history())
    assert list(features) == FEATURE_NAMES
    assert all(v == v and abs(v) != float("inf") for v in features.values())


def test_activity_band_edges():
    assert [activity_band(n) for n in (3, 9, 10, 29, 30, 99, 100, 299, 300, 600)] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]


def test_features_measure_behaviour():
    h = history([tx(MULE, SUSPECT, 2, 1000), tx(HOT, SUSPECT, 2, 2000), tx(SUSPECT, DEPOSIT, 4, 5600)])
    f = extract_features(SUSPECT, h)
    assert f["out_share"] == pytest.approx(1 / 3)
    assert f["pass_through_ratio"] == pytest.approx(1.0)
    assert f["fan_in_ratio"] == pytest.approx(2 / 3)
    assert f["out_concentration"] == pytest.approx(1.0)


def test_failed_transfers_move_no_value():
    f = extract_features(SUSPECT, history([tx(SUSPECT, MULE, 5, 100, error=True), tx(MULE, SUSPECT, 1, 50)]))
    assert f["log_eth_out"] == 0
    assert f["failed_ratio"] == 0.5


# Labels ----------------------------------------------------------------------------------
@pytest.mark.parametrize("name,labels,expected", [
    ("Binance 14", ["binance"], "exchange"),
    ("Coinbase 1", ["coinbase"], "exchange"),
    ("Binance Wrapped FIL", ["binance"], None),
    ("Huobi: HBTC Token", ["huobi"], None),
    ("Alameda Research: Binance Deposit", ["alameda-research"], None),
    ("Fake_Binance", [], None),
    ("Multichain Hack Alert 1003", ["take-action"], None),
    ("Tornado.Cash: 1 ETH", ["tornado-cash"], "mixer"),
])
def test_entity_classification(name, labels, expected):
    entity = _classify(name, labels)
    assert (entity.category if entity else None) == expected


# Tracing ---------------------------------------------------------------------------------
def test_reaches_exchange_through_mule_and_deposit():
    events, result = run_trace({
        SUSPECT: history([tx(SUSPECT, MULE, 10, 100)]),
        MULE: history([tx(MULE, DEPOSIT, 10, 200)]),
        DEPOSIT: history([tx(DEPOSIT, HOT, 5, 300), tx(DEPOSIT, HOT, 5, 310)]),
    })
    assert [e["exchange"] for e in result["exchanges"]] == ["Binance"]
    hit = result["exchanges"][0]
    assert hit["min_hops"] == 3
    assert hit["deposit_addresses"] == [DEPOSIT]
    assert hit["assets"]["ETH"] == pytest.approx(10)
    assert any(e["type"] == "exchange" for e in events)


def test_ignores_transfers_before_funds_arrived():
    _, result = run_trace({
        SUSPECT: history([tx(SUSPECT, MULE, 10, 500)]),
        MULE: history([tx(MULE, HOT, 10, 100)]),  # happened before the mule received anything
    })
    assert result["exchanges"] == []


def test_since_filter_uses_victim_payment_time():
    _, result = run_trace({SUSPECT: history([tx(SUSPECT, HOT, 10, 100)])}, since=500)
    assert result["exchanges"] == []


def test_spoofed_token_is_not_followed():
    _, result = run_trace({SUSPECT: history(tokens=[token(SUSPECT, HOT, 1000, 100, contract=FAKE)])})
    assert result["exchanges"] == [] and result["edges"] == []


def test_real_token_is_followed_and_kept_separate_from_eth():
    _, result = run_trace({SUSPECT: history([tx(SUSPECT, HOT, 1, 100)], tokens=[token(SUSPECT, HOT, 500, 110)])})
    assert result["exchanges"][0]["assets"] == {"ETH": pytest.approx(1), "USDT": pytest.approx(500)}


def test_asset_stays_the_same_along_a_route():
    _, result = run_trace({
        SUSPECT: history([tx(SUSPECT, MULE, 1, 100)]),
        MULE: history(tokens=[token(MULE, HOT, 900, 200)]),  # USDT did not come from this ETH route
    })
    assert result["exchanges"] == []


def test_route_amount_is_capped_by_narrowest_hop():
    _, result = run_trace({
        SUSPECT: history([tx(SUSPECT, MULE, 2, 100)]),
        MULE: history([tx(MULE, HOT, 50, 200)]),
    })
    assert result["routes"][0]["amount"] == pytest.approx(2)


def test_dust_and_failed_transfers_create_no_branches():
    moves = outgoing_transfers(SUSPECT, history([tx(SUSPECT, MULE, 0.00001, 1), tx(SUSPECT, DEPOSIT, 3, 2, error=True)]), 0)
    assert moves == []


def test_stops_at_mixer_and_reports_it():
    _, result = run_trace({SUSPECT: history([tx(SUSPECT, MIXER, 1, 100)])})
    assert result["terminals"][0]["kind"] == "mixer" and result["exchanges"] == []


def test_cycle_terminates():
    _, result = run_trace({
        SUSPECT: history([tx(SUSPECT, MULE, 1, 100)]),
        MULE: history([tx(MULE, SUSPECT, 1, 200)]),
    })
    assert result["exchanges"] == []


def test_hop_limit_is_respected():
    _, result = run_trace({
        SUSPECT: history([tx(SUSPECT, MULE, 1, 100)]),
        MULE: history([tx(MULE, DEPOSIT, 1, 200)]),
        DEPOSIT: history([tx(DEPOSIT, HOT, 1, 300)]),
    }, max_hops=2)
    assert result["exchanges"] == []


def test_single_transfer_is_not_a_deposit_pattern():
    assert sweep_target(DEPOSIT, history([tx(DEPOSIT, HOT, 1, 1)]), REGISTRY) is None
    pair = history([tx(DEPOSIT, HOT, 1, 1), tx(DEPOSIT, HOT, 1, 2)])
    assert sweep_target(DEPOSIT, pair, REGISTRY) == (HOT, 1.0)


# Audit chain -----------------------------------------------------------------------------
@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.sqlite3")
    body = canonical({"finding": "original"})
    s.create_case({"id": "C1", "created_at": "t", "address": SUSPECT, "status": "complete",
                   "report_json": body, "report_hash": sha256(body)})
    s.append_audit("C1", "case_created", {"a": 1})
    s.append_audit("C1", "report_sealed", sha256(body))
    s.append_audit("C1", "review_updated", {"s": "open"})
    yield s
    s.close()


def test_intact_chain_verifies(store):
    result = store.verify()
    assert result["valid"] and result["entries"] == 3 and result["reports_checked"] == 1


def test_edited_report_is_detected(store):
    store.execute("UPDATE cases SET report_json=? WHERE id='C1'", (canonical({"finding": "changed"}),))
    assert not store.verify()["valid"]


def test_edited_log_entry_is_detected(store):
    store.execute("UPDATE audit_log SET event='something_else' WHERE seq=2")
    assert not store.verify()["valid"]


def test_deleted_log_entry_is_detected(store):
    store.execute("DELETE FROM audit_log WHERE seq=2")
    assert not store.verify()["valid"]
