"""Load the trained model and turn a wallet history into an explained risk score."""
from __future__ import annotations

from functools import lru_cache

import joblib
import numpy as np
import shap

from .config import ARTIFACT_DIR, MIN_TX_FOR_SCORING
from .features import FEATURES, activity_count, extract_features


@lru_cache(maxsize=1)
def _load_file(path: str, modified: int) -> dict:
    bundle = joblib.load(path)
    explainer = shap.TreeExplainer(bundle["tree"], data=bundle["background"], model_output="probability")
    return {**bundle, "explainer": explainer}


def _load() -> dict | None:
    """The file's timestamp is part of the cache key, so a newly trained model is used without a restart."""
    path = ARTIFACT_DIR / "model.joblib"
    if not path.exists():
        return None
    return _load_file(str(path), path.stat().st_mtime_ns)


def model_loaded() -> bool:
    return _load() is not None


def model_version() -> str | None:
    bundle = _load()
    return bundle["version"] if bundle else None


def _shap_values(explainer, row: np.ndarray) -> np.ndarray:
    values = explainer.shap_values(row, check_additivity=False)
    values = np.asarray(values[1] if isinstance(values, list) else values)
    if values.ndim == 3:  # (rows, features, classes)
        values = values[:, :, 1]
    return values[0]


LOG_UNITS = {
    "log_span_days": (" days", 0),
    "log_interval_median": (" hours", 1),
    "log_first_out_delay": (" hours", 1),
    "log_hold_median": (" hours", 1),
    "log_max_tx_hour": (" transactions", 0),
    "log_gas_price": (" gwei", 1),
    "log_fee": (" milli-ETH", 2),
    "log_eth_in": (" ETH", 3),
    "log_eth_out": (" ETH", 3),
    "log_eth_in_median": (" ETH", 3),
    "log_eth_out_median": (" ETH", 3),
    "log_eth_in_max": (" ETH", 3),
    "log_eth_out_max": (" ETH", 3),
}


def _shown_score(value: float) -> float:
    """Calibration on a small validation set produces flat steps that can reach exactly 0 or 1. Neither is certainty."""
    return min(max(value, 0.01), 0.99)


def _display(name: str, value: float) -> str:
    unit = FEATURES[name][1]
    if unit == "log":
        suffix, decimals = LOG_UNITS.get(name, ("", 0))
        return f"{np.expm1(value):,.{decimals}f}{suffix}"
    if unit == "ratio":
        return f"{value * 100:.0f}%"
    if unit == "flag":
        return "yes" if value else "no"
    return f"{value:.2f}"


def score_wallet(address: str, history: dict, is_contract: bool = False) -> dict:
    """Risk indication for a wallet. Never a finding of fraud."""
    if is_contract:
        return {"status": "not_applicable",
                "message": "This address is a smart contract. The model was trained on wallets only, so no score is given."}
    if activity_count(history) < MIN_TX_FOR_SCORING:
        return {"status": "insufficient_history",
                "message": f"Fewer than {MIN_TX_FOR_SCORING} transactions, which is too little behaviour to score."}
    bundle = _load()
    if bundle is None:
        return {"status": "model_missing", "message": "No trained model found. Run ml/train.py first."}

    features = extract_features(address, history)
    row = np.array([[features[name] for name in bundle["features"]]], dtype=float)
    probability = float(bundle["calibrated"].predict_proba(row)[0, 1])
    thresholds = bundle["thresholds"]
    level = "high" if probability >= thresholds["high"] else "medium" if probability >= thresholds["medium"] else "low"

    contributions = _shap_values(bundle["explainer"], row)
    ranked = sorted(zip(bundle["features"], contributions), key=lambda item: -abs(item[1]))[:6]
    medians = bundle["reference_medians"]
    reasons = [
        {
            "feature": name,
            "description": FEATURES[name][0],
            "value": _display(name, features[name]),
            "typical": _display(name, medians[name]),
            "contribution": float(contribution),
            "pushes": "up" if contribution > 0 else "down",
        }
        for name, contribution in ranked
    ]
    return {
        "status": "scored",
        "score": _shown_score(probability),
        "level": level,
        "reasons": reasons,
        "model_version": bundle["version"],
        "model_name": bundle["name"],
        "thresholds": {"medium": _shown_score(thresholds["medium"]), "high": _shown_score(thresholds["high"])},
        "history_truncated": bool(features["history_truncated"]),
    }
