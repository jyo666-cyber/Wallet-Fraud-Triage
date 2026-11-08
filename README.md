# Wallet Fraud Triage

AI-based Ethereum wallet risk analysis, plus a live trace from a victim-reported wallet to fraud-linked exchanges.

Project titles covered:

- AI-Based Cryptocurrency Wallet Fraud Detection and Risk Analysis Using Ethereum Blockchain Transaction Data
- Real-Time Identification of Fraud-Linked Cryptocurrency Exchanges from Victim-Reported Suspect Wallet Addresses through Automated Blockchain Analytics

**Scores and traces are risk indications for human review. They are not proof of fraud or of anyone's identity or intent.**

## Run it

You need Python 3.13, Node 20 and an internet connection. No API key is required.

```powershell
.\start.ps1
```

This installs dependencies on first run and opens the backend and frontend in their own windows.

- App: http://localhost:5173
- API: http://127.0.0.1:8000

The trained model is already in `artifacts/`. To rebuild it:

```powershell
backend\.venv\Scripts\python.exe ml\collect_dataset.py --positives 300 --controls-per-positive 2
backend\.venv\Scripts\python.exe ml\train.py
```

Collection from scratch takes several hours at the public API's rate limit, mostly spent finding comparison wallets in the right activity band. Keep the computer awake: sleep pauses it. A stopped run resumes where it left off, and running it again retries any unfilled comparison slots. Training takes under a minute, and the running backend picks up the new model without a restart.

Run the offline tests:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests -q
```

## What it does

1. **Report:** a victim submits a suspect wallet, with an optional transaction hash, amount and date.
2. **Score:** the wallet's history is read from Blockscout and turned into 34 behaviour features. The model gives a calibrated score, a low/medium/high level and SHAP reasons.
3. **Trace:** funds are followed forward in time until they reach a labelled exchange, mixer, DEX or bridge, or a limit is hit. Deposit addresses are detected from sweep patterns.
4. **Review:** a person records the decision. List matches are shown separately and are never model inputs.
5. **Seal:** the report's SHA-256 hash goes into a hash-chained audit log, so later edits can be detected.

| Part | Location |
|---|---|
| API and case pipeline | `backend/app/main.py`, `pipeline.py` |
| Chain data client | `backend/app/chain.py` |
| Features (same code for training and scoring) | `backend/app/features.py` |
| Scoring and explanations | `backend/app/scoring.py` |
| Fund tracer | `backend/app/tracer.py` |
| Audit log | `backend/app/store.py` |
| Dataset collection and training | `ml/collect_dataset.py`, `ml/train.py` |
| User interface | `frontend/src/` |

## Dataset

Model version `20261108-0118`, built from live chain histories. Details are also on the app's Model page and in `artifacts/metrics.json`.

- **Flagged (301):** wallets on public lists. Etherscan phish-hack via Forta 116, ScamSniffer 81, Etherscan malicious labels via Forta 63, MyEtherWallet darklist 41.
- **Controls (451):** for each flagged wallet, up to two random wallets that:
  - appeared in blocks within 30 days of the flagged wallet's first activity
  - are in the same **activity band**: 3–9, 10–29, 30–99, 100–299 or 300+ items read from its history
  - are on none of the lists
- **Excluded:** 156 contracts and 189 wallets with fewer than 3 transactions. Another 384 wallets passed the counter check but turned out to be in a different band once their full history was read.
- **Set aside:** 506 comparison wallets from the first, unmatched collection are still in the data file but outside their flagged wallet's band, so training skips them. That collection is backed up as `data/raw/wallets_v1_unmatched.jsonl.gz`, with its model and metrics in `artifacts/*_v1_unmatched.*`.
- **Unfilled:** 151 of the 602 comparison slots, because no wallet in the right band was found within the search limit.
- **Dates:** 2017-06-25 to 2023-03-15.

| Split | Wallets | Flagged | From | To |
|---|---|---|---|---|
| Train | 502 | 210 | 2017-06-25 | 2022-04-30 |
| Validation | 128 | 45 | 2022-05-04 | 2022-10-11 |
| Test | 122 | 46 | 2022-10-14 | 2023-03-15 |

The split is chronological. Each wallet appears in one partition only, and a flagged wallet stays with its controls. SMOTE is applied to training data only. Model choice, calibration and cut-offs use validation data.

## Results

**Selected model:** Gradient Boosting + SMOTE, chosen by validation PR-AUC among the tree models that support SHAP explanations.

Test set, at the cut-off chosen on validation data (0.409):

| Metric | Value |
|---|---|
| PR-AUC, calibrated scores | 0.674 |
| PR-AUC, before calibration | 0.719 |
| ROC-AUC, calibrated scores | 0.779 |
| Precision | 68% |
| Recall | 70% |
| F1 | 0.688 |
| Accuracy | 76% |
| False-alert rate | 20% |
| False alerts / missed | 15 / 14 |
| Correctly passed / correctly alerted | 61 / 32 |

Baselines on the same split, with thresholds chosen on validation data:

| Model | Val PR-AUC | Test PR-AUC | Precision | Recall | F1 | False alerts |
|---|---:|---:|---:|---:|---:|---:|
| **Gradient Boosting + SMOTE** | 0.739 | 0.719 | 68% | 70% | 0.688 | 15 |
| Gradient Boosting | 0.735 | 0.718 | 61% | 72% | 0.660 | 21 |
| Random Forest + SMOTE | 0.717 | 0.725 | 72% | 57% | 0.634 | 10 |
| Random Forest | 0.693 | 0.666 | 71% | 54% | 0.617 | 10 |
| K-Nearest Neighbors + SMOTE | 0.626 | 0.649 | 67% | 43% | 0.526 | 10 |
| K-Nearest Neighbors | 0.624 | 0.667 | 62% | 52% | 0.565 | 15 |
| Decision Tree + SMOTE | 0.521 | 0.568 | 49% | 83% | 0.613 | 40 |
| Decision Tree | 0.515 | 0.518 | 46% | 41% | 0.437 | 22 |

Gradient Boosting and Random Forest are close. The differences are too small on 122 test wallets to show that one is better, or that SMOTE helps.

Triage levels on the test set:

| Level | Wallets | Actually flagged | Share |
|---|---:|---:|---:|
| High | 7 | 6 | 86% |
| Medium | 40 | 26 | 65% |
| Low | 75 | 14 | 19% |

A low level does not clear a wallet: 14 of the 46 flagged test wallets landed there.

Results by activity band, from small groups:

| Activity | Flagged in data | Controls in data | Test false alerts | Test flagged caught |
|---|---:|---:|---:|---:|
| 3–9 items | 91 | 108 | 2 of 11 | 5 of 11 |
| 10–29 items | 72 | 84 | 2 of 19 | 6 of 12 |
| 30–99 items | 67 | 117 | 3 of 24 | 10 of 12 |
| 100–299 items | 58 | 116 | 5 of 14 | 7 of 7 |
| 300+ items | 13 | 26 | 3 of 8 | 4 of 4 |

The model catches fewer flagged wallets with low activity, and gives more false alerts on busy wallets.

Other checks:

- **Random split:** PR-AUC 0.830 against 0.719 on the chronological split, both before calibration. A random split makes the model look better than it is on future wallets.
- **Cross-validation on the training period:** ROC-AUC 0.861 ± 0.023.
- **Rare fraud:** precision falls as fraud gets rarer, with recall and false-alert rate held at their test values.

| Assumed share of fraudulent wallets | Expected precision |
|---:|---:|
| 1% | 3.4% |
| 5% | 15.6% |
| 10% | 28.1% |

## Before and after activity matching

The first model used comparison wallets taken straight from random blocks. That favours busy wallets, so the model partly learned that quiet means suspicious. Matching on activity removed most of that shortcut, and the reported numbers dropped:

| | Unmatched (`20261107-2024`) | Matched (`20261108-0118`) |
|---|---:|---:|
| Controls at the 200-item history cap (flagged: 10%) | 55% | 23% |
| Median history span of controls (flagged: 41 days) | 421 days | 295 days |
| Top feature | Outgoing transactions, 25% | History span, 10% |
| Validation PR-AUC | 0.695 | 0.739 |
| Test PR-AUC, before calibration | 0.816 | 0.719 |
| Test precision / recall | 74% / 74% | 68% / 70% |
| False-alert rate, test wallets under the cap | 30% | 17% |
| False-alert rate, test wallets at the cap | 2% | 29% |

The two test sets share the same flagged wallets but have different controls, so this is not an exact like-for-like comparison. Validation and test agree much more closely after matching, which suggests the matched figures are more realistic. The first model's figures were flattered by the sampling shortcut.

## Read before quoting these results

### 1. Matching is incomplete

151 comparison slots could not be filled, mostly for quiet wallets. Quiet bands therefore have about 1.2 controls per flagged wallet, against 2 in busy bands, so activity can still partly separate the classes. Running the collector again retries the unfilled slots.

### 2. History length is still the top feature

Histories include activity after a wallet was first seen. Flagged wallets may go quiet once listed, while controls carry on, so history length may partly reflect listing rather than behaviour beforehand. A cleaner design would cut every history at the date its wallet was listed. The lists used here do not record that date reliably.

### 3. The test set is no longer untouched

After the first training run, the results were inspected and four changes were made:

- `history_truncated` was removed.
- The medium level was set to start at the alert cut-off.
- Displayed scores were capped at 1–99%.
- Comparison wallets were recollected with activity matching.

The matched run was carried out under rules fixed in advance and was not tuned after its test results were seen. Even so, the decision to match came from looking at test results, so treat the test figures as slightly optimistic.

### 4. Other limitations

- **Small sample:** 46 flagged test wallets, so one wallet moves recall by about 2 points. Per-band figures come from groups of 4–24 wallets.
- **Labels:** controls may contain unreported fraud, and lists contain errors. "Flagged" means listed, not proven.
- **Age:** test data ends in March 2023, so performance on newer scam patterns is unmeasured.
- **Calibration:** it uses 128 validation wallets, so scores move in coarse steps. The high level needs the top step, which displays as 99%. Do not read that as a 99% chance of fraud.
- **Collection:** band screening uses Blockscout's address counters, which leave out contract payments; the full history decides the final band. A few requests failed after retries and those wallets were replaced.
- **Exchange labels:** they come from an old, incomplete public snapshot, so a route ending at an unlabelled exchange will be missed.
- **Tracing:** route amounts are upper bounds because addresses can mix funds. The confidence level is a transparent rule, not a probability. Multi-hop deposit routes are covered by offline tests but have not yet been seen on real data.
- **Scope:** Ethereum mainnet only, up to 200 items per history list. "Real time" means a live trace on demand, not continuous monitoring.
- **Not implemented:** testnet anchoring (the audit trail is a local hash chain), federated learning and social media signals.

## Requirements from the literature review

| Requirement | Where |
|---|---|
| Documented Ethereum dataset and behavioural features | `collect_dataset.py`, `features.py`, Model page |
| DT, RF, KNN and Gradient Boosting baselines | `train.py`, Model page |
| Split before resampling, SMOTE on training data only | SMOTE sits inside the training pipeline |
| Chronological holdout and wallet-aware split | `chronological_split` in `train.py` |
| Precision, recall, F1, confusion matrix, false alerts, PR curve, threshold comparison | Model page |
| Threshold chosen on validation data | `best_f1_threshold`, `triage_thresholds` |
| Calibrated low/medium/high triage with feature-based explanations | `scoring.py`, case page |
| Error-review log | `error_review` in `train.py`, Model page |
| Tamper-evident alert record | `store.py`, Audit log page |
| Risk indication, not proof | Shown on every report and score |
| Dataset version, labels, class distribution, split and parameters | `artifacts/metrics.json`, Model page |

## Demo

`0xf985aa8117999fa3f0f9e71a20d0fe7b88b9d706` shows a one-hop trace to HitBTC well. It is in the **training set**, so its score says nothing about accuracy on new wallets. With the current model it is rated medium.

Wallets from the held-out test period, for the Wallet check page:

- Flagged: `0x6e89cdf2622208ad58d10aad6ee0a6e93f777488`. The current model rates it low, so it is one of the misses.
- Control: `0x1bdd4ba87f88e16cfb55274851afbe84426ba5a1`. Rated low, which is correct.

Scores come from each wallet's latest history, so they can change over time.

Data sources: Blockscout, Forta labelled datasets, MyEtherWallet darklist, ScamSniffer and public Etherscan label snapshots.
