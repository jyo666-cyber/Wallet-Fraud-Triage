"""Train and evaluate the wallet risk models, following the review's evaluation design.

  * Chronological holdout: oldest 70% train, next 15% validation, newest 15% test.
    A positive and its matched controls always stay in one partition.
  * Each wallet is one row in exactly one partition, so no wallet overlaps across splits.
  * SMOTE, when used, sits inside the pipeline and only ever sees training data.
  * Model choice, calibration and alert thresholds use validation data only.
  * The test set is scored once at the end, and its results are what gets reported.

    python ml/train.py
"""
from __future__ import annotations

import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shap  # noqa: E402
from imblearn.over_sampling import SMOTE  # noqa: E402
from imblearn.pipeline import Pipeline  # noqa: E402
from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier  # noqa: E402
from sklearn.frozen import FrozenEstimator  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split  # noqa: E402
from sklearn.neighbors import KNeighborsClassifier  # noqa: E402
from sklearn.preprocessing import MinMaxScaler  # noqa: E402
from sklearn.tree import DecisionTreeClassifier  # noqa: E402

from app.config import ARTIFACT_DIR, RAW_DIR  # noqa: E402
from app.features import ACTIVITY_BAND_NAMES, FEATURES, activity_band, activity_count, extract_features  # noqa: E402

# history_truncated only says a wallet passed our own collection cap. Controls come from random
# blocks, which favours busy wallets, so this flag mostly identified how a wallet was sampled.
FEATURE_NAMES = [name for name in FEATURES if name != "history_truncated"]
SEED = 42
CONTROLS_PER_POSITIVE = 2
# Fraud is far rarer in real traffic than in this study's sample, so precision is also
# restated at these assumed base rates. Recall and false-positive rate carry over; precision does not.
ASSUMED_PREVALENCE = [0.01, 0.05, 0.10]


def load_dataset() -> pd.DataFrame:
    rows = []
    skipped: dict[str, int] = {}
    try:
        with gzip.open(RAW_DIR / "wallets.jsonl.gz", "rt", encoding="utf8") as fh:
            for line in fh:
                row = json.loads(line)
                if row.get("skip"):
                    skipped[row["skip"]] = skipped.get(row["skip"], 0) + 1
                    continue
                features = extract_features(row["address"], row["history"])
                rows.append({"address": row["address"], "label": row["label"], "source": row["source"],
                             "anchor_ts": row["anchor_ts"], "pair": row["pair"],
                             "band": activity_band(activity_count(row["history"])), **features})
    except (EOFError, json.JSONDecodeError):
        print("Dataset file ends mid-write (collection may be running); using the complete rows.")
    df = match_controls(pd.DataFrame(rows).drop_duplicates("address").reset_index(drop=True))
    print(f"{len(df)} wallets ({df.label.sum()} flagged). Skipped during collection: {skipped}")
    return df


def match_controls(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only controls in their flagged wallet's activity band, up to the per-wallet quota."""
    pair_band = df[df.label == 1].set_index("pair").band
    controls = df[(df.label == 0) & (df.band == df.pair.map(pair_band))]
    controls = controls.groupby("pair", sort=False).head(CONTROLS_PER_POSITIVE)
    print(f"controls: kept {len(controls)} in-band, set aside {(df.label == 0).sum() - len(controls)}")
    return pd.concat([df[df.label == 1], controls]).reset_index(drop=True)


def chronological_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pairs = df[df.label == 1][["pair", "anchor_ts"]].sort_values("anchor_ts")
    first_val = int(len(pairs) * 0.70)
    first_test = int(len(pairs) * 0.85)
    partition = {p: "train" for p in pairs.pair.iloc[:first_val]}
    partition.update({p: "val" for p in pairs.pair.iloc[first_val:first_test]})
    partition.update({p: "test" for p in pairs.pair.iloc[first_test:]})
    groups = df.pair.map(partition)
    return df[groups == "train"], df[groups == "val"], df[groups == "test"]


def candidates() -> dict:
    def scaled(model):
        return [("scale", MinMaxScaler()), ("model", model)]

    def tree(model):
        return [("model", model)]

    def smote(steps):
        return Pipeline([*steps[:-1], ("smote", SMOTE(random_state=SEED)), steps[-1]])

    make = {
        "Decision Tree": lambda: tree(DecisionTreeClassifier(max_depth=8, min_samples_leaf=10, random_state=SEED)),
        "Random Forest": lambda: tree(RandomForestClassifier(n_estimators=300, min_samples_leaf=3, n_jobs=-1, random_state=SEED)),
        "K-Nearest Neighbors": lambda: scaled(KNeighborsClassifier(n_neighbors=15, weights="distance")),
        "Gradient Boosting": lambda: tree(GradientBoostingClassifier(n_estimators=250, max_depth=3, learning_rate=0.06,
                                                                     subsample=0.8, random_state=SEED)),
    }
    models = {}
    for name, steps in make.items():
        models[name] = Pipeline(steps())
        models[f"{name} + SMOTE"] = smote(steps())
    return models


def threshold_metrics(y, score, threshold: float) -> dict:
    pred = (score >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "accuracy": float((tp + tn) / len(y)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "fpr": float(fp / (fp + tn)) if fp + tn else 0.0,
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
    }


def score_summary(y, score, threshold: float) -> dict:
    return {
        "pr_auc": float(average_precision_score(y, score)),
        "roc_auc": float(roc_auc_score(y, score)),
        **threshold_metrics(y, score, threshold),
    }


def precision_at_prevalence(recall: float, fpr: float, prevalence: float) -> float:
    denominator = recall * prevalence + fpr * (1 - prevalence)
    return recall * prevalence / denominator if denominator else 0.0


def best_f1_threshold(y, score) -> float:
    precision, recall, thresholds = precision_recall_curve(y, score)
    f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    return float(thresholds[int(np.argmax(f1))])


def triage_thresholds(y, score) -> dict:
    """High = precise enough to review first. Medium = the alert cut-off, so every alert is medium or high."""
    precision, _, thresholds = precision_recall_curve(y, score)
    precision = precision[:-1]
    high_candidates = thresholds[precision >= 0.90]
    high = float(high_candidates.min()) if len(high_candidates) else float(thresholds[int(np.argmax(precision))])
    return {"medium": min(best_f1_threshold(y, score), high), "high": high}


def curve_points(y, score, n: int = 60) -> list[dict]:
    precision, recall, thresholds = precision_recall_curve(y, score)
    idx = np.unique(np.linspace(0, len(thresholds) - 1, n).astype(int))
    return [{"recall": float(recall[i]), "precision": float(precision[i]), "threshold": float(thresholds[i])} for i in idx]


def level_of(score: float, thresholds: dict) -> str:
    return "high" if score >= thresholds["high"] else "medium" if score >= thresholds["medium"] else "low"


def error_review(test: pd.DataFrame, score, threshold: float, reference: pd.DataFrame) -> dict:
    """Which behaviour most separates this model's mistakes from what it got right."""
    pred = score >= threshold
    y = test.label.values
    groups = {
        "false_positive": (pred & (y == 0), ~pred & (y == 0), "legitimate-looking wallets sent for review"),
        "false_negative": (~pred & (y == 1), pred & (y == 1), "flagged wallets the model missed"),
    }
    spread = reference[FEATURE_NAMES].std().replace(0, 1)
    review = {}
    for name, (mistakes, correct, meaning) in groups.items():
        patterns = []
        if mistakes.sum() and correct.sum():
            gap = (test.loc[mistakes, FEATURE_NAMES].mean() - test.loc[correct, FEATURE_NAMES].mean()) / spread
            for feature in gap.abs().sort_values(ascending=False).index[:5]:
                patterns.append({"feature": feature, "description": FEATURES[feature][0],
                                 "direction": "higher" if gap[feature] > 0 else "lower",
                                 "effect": float(abs(gap[feature]))})
        review[name] = {"count": int(mistakes.sum()), "meaning": meaning, "patterns": patterns}
    return review


def selection_check(df: pd.DataFrame, test: pd.DataFrame, score, threshold: float) -> dict:
    """How differently the two classes were sampled, and how the model does on wallets under the cap."""
    def profile(part: pd.DataFrame) -> dict:
        return {"wallets": int(len(part)), "at_cap_share": float(part.history_truncated.mean()),
                "median_span_days": float(np.expm1(part.log_span_days.median()))}

    y = test.label.values
    under_cap = test.history_truncated.values == 0
    by_band = []
    for band, name in enumerate(ACTIVITY_BAND_NAMES):
        mask = test.band.values == band
        by_band.append({
            "band": name,
            "dataset_flagged": int(((df.band == band) & (df.label == 1)).sum()),
            "dataset_controls": int(((df.band == band) & (df.label == 0)).sum()),
            **threshold_metrics(y[mask], score[mask], threshold),
        })
    return {
        "flagged": profile(df[df.label == 1]),
        "controls": profile(df[df.label == 0]),
        "test_under_cap": threshold_metrics(y[under_cap], score[under_cap], threshold),
        "test_at_cap": threshold_metrics(y[~under_cap], score[~under_cap], threshold),
        "test_by_band": by_band,
    }


def main() -> None:
    df = load_dataset()
    train, val, test = chronological_split(df)
    X = lambda frame: frame[FEATURE_NAMES].astype(float).values  # noqa: E731
    print(f"train {len(train)}, val {len(val)}, test {len(test)}")

    comparison = []
    fitted = {}
    for name, pipeline in candidates().items():
        pipeline.fit(X(train), train.label.values)
        fitted[name] = pipeline
        val_score = pipeline.predict_proba(X(val))[:, 1]
        threshold = best_f1_threshold(val.label.values, val_score)
        comparison.append({"model": name, "uses_smote": "SMOTE" in name, "threshold": threshold,
                           "validation": score_summary(val.label.values, val_score, threshold)})
        print(f"{name:32s} val PR-AUC {comparison[-1]['validation']['pr_auc']:.3f} F1 {comparison[-1]['validation']['f1']:.3f}")

    # Selection by validation PR-AUC, among models TreeExplainer can explain per alert.
    explainable = [c for c in comparison if "Forest" in c["model"] or "Boosting" in c["model"]]
    best = max(explainable, key=lambda c: c["validation"]["pr_auc"])
    best_name = best["model"]
    print("selected:", best_name)

    calibrated = CalibratedClassifierCV(FrozenEstimator(fitted[best_name]), method="isotonic")
    calibrated.fit(X(val), val.label.values)
    val_prob = calibrated.predict_proba(X(val))[:, 1]
    thresholds = triage_thresholds(val.label.values, val_prob)
    decision_threshold = best_f1_threshold(val.label.values, val_prob)

    # The test set is touched from here on, after every choice above is fixed.
    for entry in comparison:
        entry["test"] = score_summary(test.label.values, fitted[entry["model"]].predict_proba(X(test))[:, 1], entry["threshold"])
    test_prob = calibrated.predict_proba(X(test))[:, 1]
    test_summary = score_summary(test.label.values, test_prob, decision_threshold)
    triage_counts = {
        level: {"wallets": int(mask.sum()), "flagged": int(test.label.values[mask].sum())}
        for level, mask in {
            "high": test_prob >= thresholds["high"],
            "medium": (test_prob >= thresholds["medium"]) & (test_prob < thresholds["high"]),
            "low": test_prob < thresholds["medium"],
        }.items()
    }

    # Random split for contrast: shows how much an optimistic split would flatter the result.
    tr_r, te_r = train_test_split(df, test_size=0.3, stratify=df.label, random_state=SEED)
    random_model = candidates()[best_name].fit(X(tr_r), tr_r.label.values)
    random_score = random_model.predict_proba(X(te_r))[:, 1]
    random_split = {"pr_auc": float(average_precision_score(te_r.label, random_score)),
                    "roc_auc": float(roc_auc_score(te_r.label, random_score))}

    # Cross-validated ROC-AUC on the training partition: stability across folds.
    fold_scores = []
    for tr_idx, te_idx in StratifiedKFold(5, shuffle=True, random_state=SEED).split(X(train), train.label.values):
        model = candidates()[best_name].fit(X(train)[tr_idx], train.label.values[tr_idx])
        fold_scores.append(float(roc_auc_score(train.label.values[te_idx], model.predict_proba(X(train)[te_idx])[:, 1])))

    inner = fitted[best_name].named_steps["model"]
    importances = sorted(
        ({"feature": f, "description": FEATURES[f][0], "importance": float(v)}
         for f, v in zip(FEATURE_NAMES, inner.feature_importances_)),
        key=lambda item: -item["importance"],
    )

    def iso(ts) -> str:
        return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d")

    version = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    metrics = {
        "model_version": version,
        "selected_model": best_name,
        "selection_rule": "highest validation PR-AUC among tree models that support per-alert explanations",
        "feature_count": len(FEATURE_NAMES),
        "dataset": {
            "wallets": int(len(df)),
            "flagged": int(df.label.sum()),
            "controls": int((df.label == 0).sum()),
            "sources": {k: int(v) for k, v in df.source.value_counts().items()},
            "date_range": [iso(df.anchor_ts.min()), iso(df.anchor_ts.max())],
            "label_definition": "Flagged = address on a public phishing/scam list (Etherscan phish-hack via Forta, "
                                "MyEtherWallet darklist, ScamSniffer). Control = random externally-owned wallet active "
                                "near the same date, in the same activity band, and on none of those lists. "
                                "Controls may include unreported fraud.",
        },
        "splits": {
            name: {"wallets": int(len(part)), "flagged": int(part.label.sum()),
                   "from": iso(part.anchor_ts.min()), "to": iso(part.anchor_ts.max())}
            for name, part in {"train": train, "validation": val, "test": test}.items()
        },
        "comparison": comparison,
        "final_test": test_summary,
        "thresholds": {**thresholds, "decision": decision_threshold},
        "triage_on_test": triage_counts,
        "pr_curve": curve_points(test.label.values, test_prob),
        "threshold_table": [threshold_metrics(test.label.values, test_prob, t) for t in
                            sorted({thresholds["medium"], decision_threshold, thresholds["high"]})],
        "real_world_precision": [
            {"prevalence": p,
             "at_decision": precision_at_prevalence(test_summary["recall"], test_summary["fpr"], p)}
            for p in ASSUMED_PREVALENCE
        ],
        "random_split_contrast": random_split,
        "cv_train_roc_auc": {"mean": float(np.mean(fold_scores)), "std": float(np.std(fold_scores))},
        "feature_importance": importances,
        "error_review": error_review(test, test_prob, decision_threshold, train),
        "selection_check": selection_check(df, test, test_prob, decision_threshold),
    }

    ARTIFACT_DIR.mkdir(exist_ok=True)
    background = shap.sample(train[FEATURE_NAMES].astype(float), 200, random_state=SEED)
    joblib.dump(
        {
            "version": version,
            "name": best_name,
            "calibrated": calibrated,
            "tree": inner,
            "features": FEATURE_NAMES,
            "thresholds": metrics["thresholds"],
            "background": background.values,
            "reference_medians": train[train.label == 0][FEATURE_NAMES].median().to_dict(),
        },
        ARTIFACT_DIR / "model.joblib",
    )
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf8")
    print(json.dumps({k: metrics[k] for k in ("selected_model", "splits", "final_test", "thresholds",
                                               "triage_on_test", "real_world_precision", "random_split_contrast",
                                               "cv_train_roc_auc", "selection_check")}, indent=1))
    print("top features:", [i["feature"] for i in importances[:8]])


if __name__ == "__main__":
    main()
