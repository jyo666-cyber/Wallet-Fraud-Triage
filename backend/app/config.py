"""Central paths and tunables."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
LABEL_DIR = DATA_DIR / "labels"
RAW_DIR = DATA_DIR / "raw"
ARTIFACT_DIR = ROOT / "artifacts"
DB_PATH = DATA_DIR / "cases.sqlite3"

BLOCKSCOUT_URL = "https://eth.blockscout.com"
MAX_CONCURRENCY = 6
# The public API allows 180 requests a minute per IP.
RATE_PER_SEC = 2.8
# Same cap at training and at inference, so features mean the same thing in both.
HISTORY_CAP = 200
MIN_TX_FOR_SCORING = 3

# Tracing limits: keep one trace to a bounded number of live API calls.
TRACE_MAX_HOPS = 4
TRACE_TOP_K = 3
TRACE_MAX_NODES = 40
# A wallet this busy with no label is treated as an unknown service and not followed.
TRACE_HIGH_ACTIVITY = HISTORY_CAP
# Share of an address's outflow to a single exchange wallet for it to count as a deposit address.
DEPOSIT_SWEEP_SHARE = 0.9
