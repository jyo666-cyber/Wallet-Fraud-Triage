"""SQLite persistence and the tamper-evident audit chain.

Each audit entry's hash covers its own content and the previous entry's hash, so changing
any stored report or log entry breaks the chain from that point on. The chain shows a record
was not altered after it was written. It says nothing about whether the record is correct.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import DB_PATH

GENESIS = "0" * 64
_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    address TEXT NOT NULL,
    victim_tx TEXT,
    amount_lost TEXT,
    incident_date TEXT,
    description TEXT,
    reporter_ref TEXT,
    status TEXT NOT NULL,
    error TEXT,
    priority TEXT,
    review_status TEXT NOT NULL DEFAULT 'open',
    review_note TEXT,
    report_json TEXT,
    report_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_cases_created ON cases(created_at);
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    case_id TEXT,
    event TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def entry_digest(seq: int, ts: str, case_id: str | None, event: str, payload_hash: str, prev_hash: str) -> str:
    return sha256(canonical([seq, ts, case_id, event, payload_hash, prev_hash]))


class Store:
    def __init__(self, path: Path = DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def close(self) -> None:
        self._db.close()

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self._lock, self._db:
            self._db.execute(sql, params)

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, params).fetchall()]

    # Cases -------------------------------------------------------------------------------
    def create_case(self, case: dict) -> None:
        columns = ",".join(case)
        marks = ",".join("?" for _ in case)
        self.execute(f"INSERT INTO cases ({columns}) VALUES ({marks})", tuple(case.values()))

    def update_case(self, case_id: str, **fields) -> None:
        sets = ",".join(f"{k}=?" for k in fields)
        self.execute(f"UPDATE cases SET {sets} WHERE id=?", (*fields.values(), case_id))

    def get_case(self, case_id: str) -> dict | None:
        rows = self._rows("SELECT * FROM cases WHERE id=?", (case_id,))
        return rows[0] if rows else None

    def list_cases(self) -> list[dict]:
        return self._rows("SELECT * FROM cases ORDER BY created_at DESC, rowid DESC")

    # Audit chain -------------------------------------------------------------------------
    def append_audit(self, case_id: str | None, event: str, payload) -> dict:
        payload_hash = payload if isinstance(payload, str) else sha256(canonical(payload))
        ts = now_iso()
        with self._lock, self._db:
            last = self._db.execute("SELECT seq, entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
            seq = (last["seq"] + 1) if last else 1
            prev_hash = last["entry_hash"] if last else GENESIS
            entry_hash = entry_digest(seq, ts, case_id, event, payload_hash, prev_hash)
            self._db.execute(
                "INSERT INTO audit_log (seq, ts, case_id, event, payload_hash, prev_hash, entry_hash) VALUES (?,?,?,?,?,?,?)",
                (seq, ts, case_id, event, payload_hash, prev_hash, entry_hash),
            )
        return {"seq": seq, "ts": ts, "entry_hash": entry_hash, "payload_hash": payload_hash}

    def audit_entries(self, case_id: str | None = None) -> list[dict]:
        if case_id:
            return self._rows("SELECT * FROM audit_log WHERE case_id=? ORDER BY seq", (case_id,))
        return self._rows("SELECT * FROM audit_log ORDER BY seq")

    def verify(self) -> dict:
        """Recompute the chain, then check each stored report against its recorded hash."""
        problems: list[dict] = []
        entries = self.audit_entries()
        previous, expected_seq = GENESIS, 1
        for entry in entries:
            if entry["seq"] != expected_seq:
                problems.append({"seq": entry["seq"], "problem": f"expected entry {expected_seq}; entries are missing"})
                expected_seq = entry["seq"]
            if entry["prev_hash"] != previous:
                problems.append({"seq": entry["seq"], "problem": "link to the previous entry is broken"})
            digest = entry_digest(entry["seq"], entry["ts"], entry["case_id"], entry["event"],
                                  entry["payload_hash"], entry["prev_hash"])
            if digest != entry["entry_hash"]:
                problems.append({"seq": entry["seq"], "problem": "entry content does not match its hash"})
            previous = entry["entry_hash"]
            expected_seq += 1

        anchored = {e["case_id"]: e["payload_hash"] for e in entries if e["event"] == "report_sealed"}
        reports = self._rows("SELECT id, report_json, report_hash FROM cases WHERE report_json IS NOT NULL")
        for case in reports:
            if sha256(case["report_json"]) != anchored.get(case["id"]):
                problems.append({"case_id": case["id"], "problem": "stored report does not match the sealed hash"})
        return {"valid": not problems, "entries": len(entries), "reports_checked": len(reports),
                "head": previous if entries else None, "problems": problems}
