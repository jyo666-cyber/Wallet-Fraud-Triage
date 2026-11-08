"""FastAPI application: victim report intake, live trace streaming, model and audit APIs."""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from .chain import BlockscoutClient, ChainError
from .config import ARTIFACT_DIR
from .labels import get_registry
from .pipeline import EventBus, load_report, run_case
from .scoring import model_loaded, model_version, score_wallet
from .store import Store, now_iso

ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
TX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")


class CaseIn(BaseModel):
    address: str
    victim_tx: str | None = None
    amount_lost: str | None = Field(default=None, max_length=64)
    incident_date: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=4000)
    reporter_ref: str | None = Field(default=None, max_length=120)

    @field_validator("address")
    @classmethod
    def valid_address(cls, value: str) -> str:
        value = value.strip()
        if not ADDRESS.match(value):
            raise ValueError("Enter an Ethereum address: 0x followed by 40 hexadecimal characters")
        return value.lower()

    @field_validator("victim_tx")
    @classmethod
    def valid_tx(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        if not value:
            return None
        if not TX_HASH.match(value):
            raise ValueError("Enter a transaction hash: 0x followed by 64 hexadecimal characters")
        return value.lower()


class ReviewIn(BaseModel):
    review_status: Literal["open", "escalated", "dismissed", "resolved"]
    review_note: str | None = Field(default=None, max_length=2000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = Store(app.state.db_path) if getattr(app.state, "db_path", None) else Store()
    app.state.client = getattr(app.state, "client_override", None) or BlockscoutClient()
    app.state.bus = EventBus()
    app.state.tasks = set()
    app.state.registry = get_registry()
    # A case still marked as running here lost its worker when the server stopped.
    for case in app.state.store.list_cases():
        if case["status"] in ("queued", "running"):
            app.state.store.update_case(case["id"], status="failed", error="Server restarted during analysis. Please resubmit.")
    yield
    for task in list(app.state.tasks):
        task.cancel()
    await app.state.client.aclose()
    app.state.store.close()


app = FastAPI(title="Wallet Fraud Triage API", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def _summary(case: dict) -> dict:
    report = load_report(case) or {}
    risk = report.get("risk") or {}
    exchanges = (report.get("trace") or {}).get("exchanges") or []
    return {
        "id": case["id"], "created_at": case["created_at"], "address": case["address"], "status": case["status"],
        "error": case["error"], "priority": case["priority"], "review_status": case["review_status"],
        "amount_lost": case["amount_lost"], "reporter_ref": case["reporter_ref"], "score": risk.get("score"),
        "exchanges": [e["exchange"] for e in exchanges], "flagged": bool(report.get("list_flags")),
    }


def _case_or_404(case_id: str) -> dict:
    case = app.state.store.get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return case


@app.get("/api/health")
async def health():
    registry = app.state.registry
    categories: dict[str, int] = {}
    for entity in registry.entities.values():
        categories[entity.category] = categories.get(entity.category, 0) + 1
    return {"status": "ok", "model_loaded": model_loaded(), "model_version": model_version(),
            "labels": {"flagged_addresses": len(registry.flagged), **categories}}


@app.post("/api/cases", status_code=201)
async def create_case(body: CaseIn):
    case_id = "CASE-" + uuid.uuid4().hex[:8].upper()
    store: Store = app.state.store
    store.create_case({"id": case_id, "created_at": now_iso(), "address": body.address, "victim_tx": body.victim_tx,
                       "amount_lost": body.amount_lost, "incident_date": body.incident_date,
                       "description": body.description, "reporter_ref": body.reporter_ref, "status": "queued"})
    # The reporter reference stays out of the audit hash, and the report, as personal data.
    store.append_audit(case_id, "case_created", {"address": body.address, "victim_tx": body.victim_tx})
    task = asyncio.create_task(run_case(case_id, store, app.state.bus, app.state.client, app.state.registry))
    app.state.tasks.add(task)
    task.add_done_callback(app.state.tasks.discard)
    return {"id": case_id}


@app.get("/api/cases")
async def list_cases():
    return [_summary(c) for c in app.state.store.list_cases()]


@app.get("/api/cases/{case_id}")
async def get_case(case_id: str):
    case = _case_or_404(case_id)
    return {**_summary(case), "victim_tx": case["victim_tx"], "incident_date": case["incident_date"],
            "description": case["description"], "review_note": case["review_note"],
            "report": load_report(case), "report_hash": case["report_hash"],
            "audit": app.state.store.audit_entries(case_id)}


@app.get("/api/cases/{case_id}/events")
async def case_events(case_id: str):
    case = _case_or_404(case_id)

    async def stream():
        if case["status"] in ("complete", "failed"):
            # Finished before this viewer connected: the stored case already has everything.
            yield f"data: {json.dumps({'type': 'complete' if case['status'] == 'complete' else 'failed'})}\n\n"
            return
        async for event in app.state.bus.stream(case_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.patch("/api/cases/{case_id}")
async def review_case(case_id: str, body: ReviewIn):
    _case_or_404(case_id)
    app.state.store.update_case(case_id, review_status=body.review_status, review_note=body.review_note)
    app.state.store.append_audit(case_id, "review_updated", {"status": body.review_status, "note": body.review_note})
    return {"ok": True}


@app.get("/api/wallets/{address}/risk")
async def wallet_risk(address: str):
    if not ADDRESS.match(address):
        raise HTTPException(422, "Enter an Ethereum address: 0x followed by 40 hexadecimal characters")
    address = address.lower()
    client: BlockscoutClient = app.state.client
    try:
        history = await client.history(address)
    except ChainError as exc:
        raise HTTPException(502, f"The chain data source did not respond: {exc}") from exc
    risk = await asyncio.to_thread(score_wallet, address, history, history["is_contract"])
    registry = app.state.registry
    entity = registry.entity(address)
    return {"address": address, "risk": risk, "list_flags": registry.flags(address),
            "entity": {"category": entity.category, "entity": entity.entity, "name": entity.name} if entity else None}


@app.get("/api/model/metrics")
async def metrics():
    path = ARTIFACT_DIR / "metrics.json"
    if not path.exists():
        raise HTTPException(404, "No trained model yet. Run ml/train.py first.")
    return json.loads(path.read_text(encoding="utf8"))


@app.get("/api/audit")
async def audit():
    return list(reversed(app.state.store.audit_entries()))[:200]


@app.get("/api/audit/verify")
async def audit_verify():
    return app.state.store.verify()
