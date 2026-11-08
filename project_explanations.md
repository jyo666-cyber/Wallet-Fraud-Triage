# Project Explanations: Wallet Fraud Triage

A complete guide to this project: what it is, how every part works, how the data was collected, how the model was trained and evaluated, and how each team member can run, retrain and extend it on their own computer.

**Project titles covered:**

1. *AI-Based Cryptocurrency Wallet Fraud Detection and Risk Analysis Using Ethereum Blockchain Transaction Data*
2. *Real-Time Identification of Fraud-Linked Cryptocurrency Exchanges from Victim-Reported Suspect Wallet Addresses through Automated Blockchain Analytics*

> **Golden rule of this project:** every score and every trace is a *risk indication for human review*. It is never proof of fraud, of anyone's identity, or of anyone's intent. The app says this on every page, and the team should say it in every presentation.

---

## Contents

1. [What the project does, in plain words](#1-what-the-project-does-in-plain-words)
2. [Quick start for teammates](#2-quick-start-for-teammates)
3. [Full setup on a new computer, step by step](#3-full-setup-on-a-new-computer-step-by-step)
4. [Sharing the project inside the team](#4-sharing-the-project-inside-the-team)
5. [Project structure: every file explained](#5-project-structure-every-file-explained)
6. [Architecture: how the pieces talk to each other](#6-architecture-how-the-pieces-talk-to-each-other)
7. [Where the data comes from](#7-where-the-data-comes-from)
8. [How the training dataset was built](#8-how-the-training-dataset-was-built)
9. [The 34 behaviour features](#9-the-34-behaviour-features)
10. [How the model is trained and evaluated](#10-how-the-model-is-trained-and-evaluated)
11. [How a wallet gets scored and explained](#11-how-a-wallet-gets-scored-and-explained)
12. [How funds are traced to exchanges](#12-how-funds-are-traced-to-exchanges)
13. [How a victim report becomes a sealed case](#13-how-a-victim-report-becomes-a-sealed-case)
14. [The tamper-evident audit log](#14-the-tamper-evident-audit-log)
15. [The user interface, page by page](#15-the-user-interface-page-by-page)
16. [The backend API](#16-the-backend-api)
17. [How to collect data and retrain the model](#17-how-to-collect-data-and-retrain-the-model)
18. [Results](#18-results)
19. [What we did and why: the project story](#19-what-we-did-and-why-the-project-story)
20. [Limitations to state honestly](#20-limitations-to-state-honestly)
21. [How this meets the literature review's requirements](#21-how-this-meets-the-literature-reviews-requirements)
22. [Testing](#22-testing)
23. [Troubleshooting](#23-troubleshooting)
24. [Ideas for future work](#24-ideas-for-future-work)
25. [Glossary](#25-glossary)

---

## 1. What the project does, in plain words

Someone loses cryptocurrency to a scam. They know one thing for certain: the Ethereum wallet address they sent money to. This project takes that address and does two jobs.

**Job 1: assess the wallet (title 1).**
It reads the wallet's public transaction history from the Ethereum blockchain, turns that history into 34 behaviour measurements (how many transactions, how quickly money is passed on, how many different people pay in, and so on), and gives them to a machine-learning model trained on known scam wallets and ordinary wallets. The model returns:

- a **risk score**, which says how closely this wallet behaves like wallets on public scam lists
- a **level**: low, medium or high
- the **reasons**: the six measurements that pushed the score up or down the most, compared with a typical ordinary wallet

**Job 2: follow the money (title 2).**
It follows the funds forward from the suspect wallet, hop by hop, until they reach a known cryptocurrency **exchange** (Binance, Coinbase, HitBTC and so on). Exchanges know who their customers are, so an exchange is the point where police can ask for the account holder's identity and request a freeze. The trace runs live, on demand, as soon as a report is submitted.

Everything ends in a **sealed report**: a document whose fingerprint (SHA-256 hash) is written into a chained audit log, so any later change to the report can be detected. A human reviewer then records a decision: escalate, dismiss or resolve.

---

## 2. Quick start for teammates

If the project folder is already on your computer, and Python 3.13 and Node.js 20 are installed:

```powershell
cd "path\to\project"
.\start.ps1
```

Then open **http://localhost:5173** in your browser.

That's it. The first run takes a few minutes because it installs packages. The trained model is already included in `artifacts/`, so you do **not** need to collect data or train anything to use the app.

If PowerShell refuses to run the script ("running scripts is disabled on this system"), run it this way instead, which allows it for this one run only:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

---

## 3. Full setup on a new computer, step by step

### 3.1 What you need to install

| Software | Version we used | Where to get it | How to check |
|---|---|---|---|
| Python | 3.13.3 | python.org/downloads. On Windows, tick **"Add python.exe to PATH"** during install. | `python --version` |
| Node.js (includes npm) | 20.11.0, npm 10.9.1 | nodejs.org (the LTS version) | `node --version` and `npm --version` |
| Internet connection | | | The app reads live blockchain data |

**You do not need:**

- an API key (the blockchain data source, Blockscout, is free and keyless)
- a database server (SQLite is a single file, built into Python)
- a GPU (the model is small and trains on a normal laptop CPU in under a minute)

Other Python versions may work, but 3.13 is the one the pinned package versions were tested with. If installation fails on another version, install 3.13.

### 3.2 Option A: the one-command way (Windows)

From the project folder:

```powershell
.\start.ps1
```

Here is exactly what `start.ps1` does:

1. If `backend\.venv` doesn't exist, it creates a Python virtual environment there and installs everything in `backend\requirements.txt`.
2. If `frontend\node_modules` doesn't exist, it runs `npm install` in `frontend`.
3. It opens **two new PowerShell windows**:
   - Backend: `python -m uvicorn app.main:app --port 8000`, run inside `backend`
   - Frontend: `npm run dev`, run inside `frontend`
4. It prints the two addresses:
   - Backend API docs: http://127.0.0.1:8000/docs
   - App: http://localhost:5173

**Keep both windows open** while using the app. Closing a window stops that server.

### 3.3 Option B: manual setup (Windows), useful for understanding or fixing problems

Open PowerShell in the project folder.

**Step 1: create the Python environment and install backend packages (once):**

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

**Step 2: install frontend packages (once):**

```powershell
cd frontend
npm install
cd ..
```

**Step 3: start the backend (terminal 1):**

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Wait for the line `Uvicorn running on http://127.0.0.1:8000`. The first start can take 10–30 seconds because the explanation library (SHAP) is slow to load.

**Step 4: start the frontend (terminal 2):**

```powershell
cd frontend
npm run dev
```

Wait for `Local: http://localhost:5173/`, then open that address.

### 3.4 Option C: macOS or Linux

`start.ps1` is Windows-only, so use the manual commands with Unix paths:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

Terminal 1, backend:

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000
```

Terminal 2, frontend:

```bash
cd frontend && npm run dev
```

### 3.5 How to know it is working

1. Open http://127.0.0.1:8000/api/health. You should see something like:
   `{"status":"ok","model_loaded":true,"model_version":"20261108-0118", ...}`
   - `model_loaded: true` means the trained model was found.
   - The `labels` counts should be around 10,036 flagged addresses and 342 exchange wallets. If they're zero, the `data/labels` folder is missing (see [Troubleshooting](#23-troubleshooting)).
2. Open http://localhost:5173. You should see the Cases page with **no yellow "No trained model yet" banner**.
3. Go to **Wallet check**, paste `0xf985aa8117999fa3f0f9e71a20d0fe7b88b9d706` and press **Check**. Within a few seconds you should see a score and six reasons.
4. Go to **New report**, paste the same address and submit. You should watch the trace build live and find **HitBTC** one hop away.

### 3.6 Stopping the app

Press `Ctrl + C` in each server window, or just close the windows. Nothing is lost: cases are stored in `data/cases.sqlite3`.

Close the app before shutting down. If the backend stops while a case is being analysed, that case is marked failed on the next start with the message "Server restarted during analysis. Please resubmit."

---

## 4. Sharing the project inside the team


### 4.3 Using a ZIP file instead

1. **Delete or leave out** `backend\.venv` and `frontend\node_modules` before zipping. They are large and won't work on another computer anyway.
2. Zip the folder and share it.
3. Each teammate unzips it and runs `.\start.ps1`, which recreates both folders.

### 4.4 Splitting the work in the team

A natural division if each person presents a part:

| Area | Files | Topics to explain |
|---|---|---|
| Data collection | `ml/collect_dataset.py`, `backend/app/chain.py`, `backend/app/labels.py` | Data sources, labels, activity-matched sampling |
| Machine learning | `ml/train.py`, `backend/app/features.py`, `backend/app/scoring.py` | Features, models, SMOTE, chronological split, calibration, SHAP |
| Tracing and reports | `backend/app/tracer.py`, `backend/app/pipeline.py`, `backend/app/store.py` | Fund tracing rules, exchange attribution, audit chain |
| Frontend | `frontend/src/` | Pages, live updates, charts |

---

## 5. Project structure: every file explained

```text
project/
├── start.ps1                    One-command launcher for Windows
├── README.md                    Short summary and results
├── project_explanations.md      This document
├── .gitignore                   Files Git should not track
├── .claude/launch.json          Server settings used by the Claude app (ignore otherwise)
│
├── backend/                     Python API server (FastAPI)
│   ├── requirements.txt         Exact Python package versions
│   ├── app/
│   │   ├── main.py              API endpoints, request validation, app start-up
│   │   ├── config.py            All paths and tunable limits in one place
│   │   ├── chain.py             Client for the Blockscout blockchain API
│   │   ├── labels.py            Loads label lists: who is an exchange, who is flagged
│   │   ├── features.py          Turns a wallet history into 35 measurements (34 used)
│   │   ├── scoring.py           Loads the model, scores a wallet, explains with SHAP
│   │   ├── tracer.py            Follows funds forward to exchanges
│   │   ├── pipeline.py          Runs a case from report to sealed report
│   │   └── store.py             SQLite database and the hash-chained audit log
│   └── tests/test_core.py       28 offline tests
│
├── ml/                          Machine-learning scripts (run by hand)
│   ├── collect_dataset.py       Builds the labelled dataset from live chain data
│   └── train.py                 Trains 8 models, evaluates them, saves the best
│
├── data/
│   ├── labels/                  Public label lists (downloaded automatically if missing)
│   │   ├── etherscan_labels.json         Exchange, DEX, bridge, mixer and sanctions name tags
│   │   ├── forta_phishing_scams.csv      Etherscan phish-hack addresses (via Forta)
│   │   ├── forta_malicious_labels.csv    Etherscan malicious labels (via Forta)
│   │   ├── mew_darklist.json             MyEtherWallet darklist
│   │   └── scamsniffer.json              ScamSniffer blacklist
│   ├── raw/
│   │   ├── wallets.jsonl.gz              The dataset: one wallet per line, with history
│   │   ├── wallets_v1_unmatched.jsonl.gz Backup of the first, unmatched dataset
│   │   ├── collect*.log, train*.log      Logs from collection and training runs
│   └── cases.sqlite3                     Cases and audit log (created on first start)
│
├── artifacts/
│   ├── model.joblib             The live trained model
│   ├── metrics.json             Every evaluation number shown on the Model page
│   └── *_v1_unmatched.*         Backup of the first model and its metrics
│
└── frontend/                    React user interface (Vite)
    ├── package.json             Exact JavaScript package versions
    ├── vite.config.js           Dev server on port 5173; forwards /api to port 8000
    ├── index.html               Page shell
    └── src/
        ├── main.jsx             App shell: top bar, navigation, banners, routes
        ├── api.js               Functions that call the backend
        ├── styles.css           All styling, light and dark mode, print layout
        ├── components/
        │   ├── bits.jsx         Shared pieces: tiles, badges, score display
        │   └── FlowGraph.jsx    The money-flow diagram
        └── pages/
            ├── Cases.jsx        List of all cases
            ├── NewCase.jsx      Victim report form
            ├── CaseDetail.jsx   One case: trace, score, reasons, review, sealed report
            ├── WalletCheck.jsx  Score one address without creating a case
            ├── Model.jsx        Model evaluation and dataset record
            └── Audit.jsx        Audit log and the integrity check
```

### Main technologies

| Layer | Technology | Why |
|---|---|---|
| Backend web framework | FastAPI 0.162 + Uvicorn | Fast, async, automatic API docs at `/docs`, request validation with Pydantic |
| HTTP client | httpx (async) | Many blockchain requests run concurrently during a trace |
| Database | SQLite | Zero setup, one file, enough for a single-office tool |
| ML | scikit-learn 1.9, imbalanced-learn (SMOTE), pandas, numpy | Standard, well-documented, matches the literature review's models |
| Explanations | SHAP 0.54 (TreeExplainer) | Exact per-feature contributions for tree models |
| Model storage | joblib | Saves the trained model, calibrator and explainer data in one file |
| Frontend | React 18 + React Router 6, built with Vite 5 | Fast dev server, simple component structure |
| Live updates | Server-Sent Events (SSE) | The browser watches a trace build in real time over one HTTP connection |

---

## 6. Architecture: how the pieces talk to each other

```text
 Browser (React app, port 5173)
        │  /api/... requests (Vite forwards them to port 8000)
        ▼
 FastAPI backend (port 8000) ──────────────► Blockscout public API (eth.blockscout.com)
   │  main.py: endpoints                        live Ethereum transaction data
   │  pipeline.py: runs each case
   │     ├─ chain.py    read wallet histories
   │     ├─ scoring.py  model score + SHAP reasons ◄── artifacts/model.joblib
   │     ├─ labels.py   exchange and fraud lists  ◄── data/labels/*
   │     └─ tracer.py   follow funds to exchanges
   └─ store.py: cases + audit chain ──────────► data/cases.sqlite3

 Offline, run by hand:
   ml/collect_dataset.py ──► data/raw/wallets.jsonl.gz ──► ml/train.py ──► artifacts/model.joblib + metrics.json
```

Key design points:

- **The same feature code is used for training and for live scoring** (`backend/app/features.py`). The model sees exactly the same measurement definitions in both places. This prevents a common, hard-to-spot bug where features are computed one way in a notebook and another way in the app.
- **The model hot-reloads.** The backend checks the model file's modification time. Retrain, and the running backend uses the new model on its next request, with no restart.
- **The backend never blocks.** The CPU-heavy model and SHAP work runs in a background thread, so several traces can run at once.
- **The frontend never talks to Blockscout directly.** Only the backend does, which keeps rate limiting and caching in one place.

---

## 7. Where the data comes from

### 7.1 Blockchain data: Blockscout

All transaction data comes from the **Blockscout v2 public API** at `https://eth.blockscout.com/api/v2`. Blockscout is an open-source blockchain explorer. Its public Ethereum instance needs **no API key**.

For each wallet we read up to the **200 most recent items** of each of three kinds:

| Kind | Endpoint | What it is |
|---|---|---|
| Normal transactions | `/addresses/{address}/transactions` | Transactions the wallet sent or received directly |
| Internal transactions | `/addresses/{address}/internal-transactions` | ETH moved by smart contracts to or from the wallet |
| ERC-20 token transfers | `/addresses/{address}/token-transfers?type=ERC-20` | Token movements such as USDT and USDC |

Other endpoints we use:

- `/transactions/{hash}`: looks up the victim's payment, so a trace can start from that moment
- `/blocks/{number}/transactions`: picks random wallets for the comparison group
- `/addresses/{address}/counters`: a one-request activity count, used to screen comparison wallets cheaply

**Rate limit:** the public API allows 180 requests per minute (3 per second) per IP address. `chain.py` paces itself below that, at 2.8 per second for the app (`RATE_PER_SEC` in `config.py`) and 2.6 per second for the collector. If the server still answers "429 Too Many Requests", every request waits for the time the server says, then retries. Failed requests are retried up to 6 times with growing waits.

**Caching:** wallet histories are kept in memory for 10 minutes, so a trace that meets the same address twice doesn't fetch it twice.

**Data compaction:** each item is stored in a compact form with short keys, for example `{"h": tx hash, "f": from, "t": to, "v": value in wei, "ts": unix time, "gu": gas used, "gp": gas price, "e": error flag, "c": contract call flag}`. Token transfers also keep `d` (decimals), `s` (symbol) and `a` (token contract address).

**Why Blockscout and not Etherscan?** Etherscan requires an API key. Blockscout's older `/api` route is heavily throttled (about 10 requests per window), so we use only the v2 routes.

### 7.2 Label lists

Five public label files, stored in `data/labels/`. `ml/collect_dataset.py` downloads any that are missing from GitHub:

| File | Source | What it says | How we use it |
|---|---|---|---|
| `forta_phishing_scams.csv` | Forta Network labelled datasets (Etherscan "phish-hack" tags) | Addresses tagged as phishing or hack, with an `is_contract` column | Fraud label |
| `forta_malicious_labels.csv` | Forta Network labelled datasets (Etherscan malicious labels) | Addresses with malicious name tags | Fraud label |
| `mew_darklist.json` | MyEtherWallet `ethereum-lists` | Addresses reported for scams | Fraud label |
| `scamsniffer.json` | ScamSniffer scam database | Blacklisted scam addresses | Fraud label |
| `etherscan_labels.json` | brianleect/etherscan-labels (community snapshot of Etherscan name tags) | Names like "Binance 14", "Tornado Cash: Router", plus label categories | Identifies exchanges, DEXes, bridges and mixers; also OFAC sanctions |

`backend/app/labels.py` builds one in-memory **registry** from these files. The registry answers two separate questions:

1. **Who is this address?** For example, "exchange: Binance". The trace stops here and names the exchange.
   - **Exchanges** are matched by name with patterns such as `^binance`, `^coinbase` and `^hitbtc`, covering 30 exchanges.
   - Names that mention an exchange but are not that exchange's wallet are excluded, for example "Binance: Wrapped token", a deployer or a bridge.
   - The current registry has 342 exchange wallets, 3,656 DEX contracts, 187 bridges and 61 mixer contracts.
2. **Has it been flagged?** The four fraud lists plus OFAC sanctions, covering 10,036 flagged addresses.

Label traps we found and handled:

- Etherscan's **"take-action"** tags mark *victims* of a hack, not attackers, so they are never treated as fraud.
- **"blocked"** is a token-level flag, not a fraud label, and is also excluded.
- If a fraud list contains an address that the name tags identify as a major service (for example an exchange wallet), it is treated as a labelling conflict and not counted as fraud, unless the address is sanctioned.

**Important:** list membership is **never** a model input. A wallet being on a list is shown separately in the app ("Public list checks"), so the model has to learn from *behaviour*, not from the list itself.

---

## 8. How the training dataset was built

Script: `ml/collect_dataset.py`. Output: `data/raw/wallets.jsonl.gz`, a compressed file with one JSON object per line, one line per wallet.

### 8.1 Flagged wallets (label = 1)

1. Take every address from the four fraud lists.
2. Drop addresses the Forta file marks as contracts, and addresses the registry knows as a service (exchange, DEX and so on).
3. Shuffle, then pick **round-robin across the four sources**, so the biggest list (Etherscan phish-hack, about 5,600 candidates) can't swamp the sample.
4. For each candidate, fetch its history and skip it if:
   - it turns out to be a smart contract (156 skipped across all collection runs)
   - it has fewer than 3 items of activity, too little behaviour to learn from
5. Record its **anchor time**: the timestamp of its earliest activity in the fetched history.
6. Stop at the target, which was **300 flagged wallets** (we got 301, because 5 workers run at once).

Final flagged sample by source:

| Source | Wallets |
|---|---:|
| Etherscan phish-hack (via Forta) | 116 |
| ScamSniffer | 81 |
| Etherscan malicious labels (via Forta) | 63 |
| MyEtherWallet darklist | 41 |
| **Total** | **301** |

### 8.2 Comparison wallets (label = 0), also called controls

For each flagged wallet we want **two ordinary wallets that are as similar as possible except for being flagged**. Two kinds of matching are applied:

**Matched on time.** Each control is picked from a random block within **±30 days** of the flagged wallet's anchor time. Without this, the model could learn "wallets from 2018 look different from wallets from 2023", which is about history, not fraud.

**Matched on activity.** Each control must be in the **same activity band** as its flagged wallet:

| Band | Activity (items read across the three history lists) |
|---|---|
| 0 | 3–9 |
| 1 | 10–29 |
| 2 | 30–99 |
| 3 | 100–299 |
| 4 | 300 or more |

Why activity matching is necessary: picking a random transaction from a random block naturally lands on **busy** wallets, because busy wallets appear in far more blocks. Without matching, our first dataset had 55% of controls at the 200-item cap against 10% of flagged wallets. The model then partly learned "quiet means suspicious", which is a sampling artifact rather than real fraud behaviour. See [section 19](#19-what-we-did-and-why-the-project-story) for the full story.

The control search, step by step:

1. Estimate the block number at a random time within ±30 days of the anchor (`estimate_block` interpolates between known block/time anchor points).
2. Read that block's transactions and collect every sender and receiver that is not a contract, not a known service and not on any fraud list.
3. Screen up to 25 candidates per block with the cheap `/counters` request (one call each). Keep the first whose estimated activity falls in the right band. Try up to 6 blocks per slot.
4. Fetch the chosen wallet's full history and **re-check the band** from the real history. The counter leaves out contract payments, so it can be slightly off. 384 candidates failed this re-check and were recorded as `band_mismatch`.
5. Save it with `pair` set to the flagged wallet's address and `anchor_ts` set to the flagged wallet's anchor time.

Result: **451 matched controls**. 96 came from the first collection and happened to be in the right band; 355 were newly collected. **151 of the 602 slots stayed unfilled** because no matching wallet turned up within the search limit, mostly in the quiet bands.

The 506 earlier controls that fell outside their flagged wallet's band are still in the file. `train.py` simply skips them (`match_controls`). Nothing was deleted.

### 8.3 What one dataset line looks like

```json
{
  "address": "0x…",
  "label": 1,
  "source": "etherscan_phish",
  "anchor_ts": 1650000000,
  "pair": "0x… (the flagged wallet this row belongs to; itself for a flagged wallet)",
  "history": {
    "is_contract": false,
    "txs":      [{"h": "0x…", "f": "0x…", "t": "0x…", "v": 120000000000000000, "ts": 1650000100, "gu": 21000, "gp": 30000000000, "e": false, "c": false}],
    "internal": [{"h": "0x…", "f": "0x…", "t": "0x…", "v": 0, "ts": 0, "e": false}],
    "tokens":   [{"h": "0x…", "f": "0x…", "t": "0x…", "v": 5000000, "d": 6, "ts": 0, "s": "USDT", "a": "0xdac1…"}]
  }
}
```

Skipped wallets are also written, with a `skip` reason and no history, so a resumed run doesn't fetch them again.

### 8.4 Robustness of the collector

- **Resumable:** on start it reads everything already in the file and only does what's missing. You can stop it with `Ctrl + C` and run it again.
- **Damage-safe:** the file is closed and reopened every 25 rows, so a crash loses at most 25 rows. If the end of the file is damaged (cut off mid-write), it is repaired automatically on the next start.
- **Concurrent:** 5 workers run at once, sharing one rate limiter.
- **Sleep:** if the computer sleeps, collection pauses and continues on wake. Keep the computer awake for long runs.

---

## 9. The 34 behaviour features

Defined in `backend/app/features.py` (`extract_features`). "log" means the value is stored as log(1 + x), which keeps very large numbers from dominating. The app converts values back to normal units when it explains a score.

| # | Feature | What it measures |
|---|---|---|
| 1 | `log_tx_out` | Number of outgoing transactions |
| 2 | `log_tx_in` | Number of incoming transactions |
| 3 | `log_internal_in` | Number of ETH payments received from contracts |
| 4 | `out_share` | Share of transactions that are outgoing |
| 5 | `log_uniq_out` | Number of distinct addresses paid |
| 6 | `log_uniq_in` | Number of distinct addresses paying in |
| 7 | `fan_in_ratio` | Share of counterparties that only send money in (typical of collecting from many victims) |
| 8 | `repeat_out_ratio` | How often the wallet pays the same address again |
| 9 | `log_eth_in` | Total ETH received |
| 10 | `log_eth_out` | Total ETH sent |
| 11 | `log_eth_in_median` | Typical ETH received per payment |
| 12 | `log_eth_out_median` | Typical ETH sent per payment |
| 13 | `log_eth_in_max` | Largest single ETH receipt |
| 14 | `log_eth_out_max` | Largest single ETH payment |
| 15 | `out_concentration` | Share of all outflow in the single largest payment |
| 16 | `pass_through_ratio` | How much received ETH was passed straight on (smaller of in/out divided by larger) |
| 17 | `zero_value_ratio` | Share of transactions that moved no ETH |
| 18 | `log_gas_price` | Average gas price paid (gwei) |
| 19 | `log_fee` | Average transaction fee (milli-ETH) |
| 20 | `failed_ratio` | Share of transactions that failed |
| 21 | `contract_call_ratio` | Share of outgoing transactions that call a contract |
| 22 | `log_span_days` | Length of the activity history in days |
| 23 | `log_interval_median` | Typical time between transactions (hours) |
| 24 | `interval_cv` | Irregularity of transaction timing (coefficient of variation of gaps) |
| 25 | `log_max_tx_hour` | Most transactions in any single hour (bursts) |
| 26 | `active_day_ratio` | Share of days in the history with any activity |
| 27 | `log_first_out_delay` | Hours from the first incoming payment to the first outgoing payment |
| 28 | `log_hold_median` | Typical hours that received funds sit before moving on |
| 29 | `recent_change` | Change in activity in the last 7 active days against the 7 before |
| 30 | `log_token_transfers` | Number of ERC-20 token transfers |
| 31 | `log_uniq_tokens` | Number of distinct tokens handled |
| 32 | `token_out_share` | Share of token transfers that are outgoing |
| 33 | `log_token_counterparties` | Number of distinct token counterparties |
| 34 | `stablecoin_ratio` | Share of token transfers in USDT, USDC or DAI |

A 35th measurement, `history_truncated` (did the wallet hit the 200-item cap?), is still computed, but it is **excluded from the model** because it mostly reflected how wallets were sampled. The app still uses it to warn when a wallet's history was cut off.

What the features **deliberately do not include**:

- **Absolute dates or block numbers**, so the model can't learn "old wallet means control".
- **List membership**, so the model can't just memorise the label.
- **The wallet address itself.**

---

## 10. How the model is trained and evaluated

Script: `ml/train.py`. Run it with `backend\.venv\Scripts\python.exe ml\train.py` from the project root.

### 10.1 Step 1: load and match

- Read every non-skipped wallet from `data/raw/wallets.jsonl.gz` and compute its features and activity band.
- `match_controls`: keep only controls in their flagged wallet's band, at most 2 per flagged wallet.
- **Result: 752 wallets (301 flagged, 451 controls).**

### 10.2 Step 2: chronological, wallet-aware split

Flagged wallets are sorted by anchor time. The oldest 70% go to **train**, the next 15% to **validation** and the newest 15% to **test**. Each control goes to the **same partition as its flagged wallet**.

| Split | Wallets | Flagged | From | To |
|---|---:|---:|---|---|
| Train | 502 | 210 | 2017-06-25 | 2022-04-30 |
| Validation | 128 | 45 | 2022-05-04 | 2022-10-11 |
| Test | 122 | 46 | 2022-10-14 | 2023-03-15 |

Why this matters:

- **Chronological:** in real use, a model trained on the past scores wallets from the future. A random split lets the model peek at future patterns and inflates scores. We measured this: random split PR-AUC 0.830 against 0.719 chronological.
- **Wallet-aware:** every wallet is in exactly one partition, and a flagged wallet never shares a partition boundary with its own matched controls.

### 10.3 Step 3: eight candidate models

The four baselines named in the literature review, each trained twice, without and with SMOTE:

| Model | Settings |
|---|---|
| Decision Tree | max depth 8, at least 10 wallets per leaf |
| Random Forest | 300 trees, at least 3 wallets per leaf |
| K-Nearest Neighbors | k = 15, distance-weighted, features scaled to 0–1 (MinMax) first |
| Gradient Boosting | 250 trees, depth 3, learning rate 0.06, 80% subsample |

All use random seed 42, so results are reproducible.

**SMOTE** (Synthetic Minority Over-sampling Technique) creates synthetic examples of the smaller class by interpolating between real neighbours. It sits **inside the training pipeline** (imbalanced-learn `Pipeline`), so it only ever sees training data. Validation and test data are never resampled, because resampling them would make the results meaningless.

### 10.4 Step 4: selection on validation data only

For each model, the **alert cut-off** is the threshold that gives the best F1 score on validation data. The selected model is the one with the **highest validation PR-AUC** among Random Forest and Gradient Boosting, the tree models SHAP can explain exactly.

**Selected: Gradient Boosting + SMOTE** (validation PR-AUC 0.739).

### 10.5 Step 5: calibration

Raw model outputs are scores, not probabilities. **Isotonic calibration** maps them onto observed rates of flagged wallets in the validation set (scikit-learn `CalibratedClassifierCV` with `FrozenEstimator`, so the model itself is not retrained). Calibration on 128 wallets is coarse, so scores move in steps.

### 10.6 Step 6: triage thresholds (from validation data)

| Level | Rule |
|---|---|
| **High** | Score at or above the lowest cut-off that reached **≥ 90% precision** on validation |
| **Medium** | Score at or above the **alert cut-off** (best validation F1, currently 0.409) |
| **Low** | Below the alert cut-off |

Every alert is therefore medium or high, and high means "review this first".

### 10.7 Step 7: test, once

Only after everything above is fixed is the test set scored. The training script then also computes:

- precision, recall, F1, accuracy, false-alert rate and the confusion matrix
- PR-AUC and ROC-AUC
- the precision–recall curve and a comparison of cut-offs
- **precision at assumed real-world fraud rates** of 1%, 5% and 10%, because the test set is 38% flagged, far above reality
- the **random-split contrast**
- **5-fold cross-validated ROC-AUC** on the training period, to check stability
- an **error review**: which features most distinguish the model's false alerts and misses from what it got right, in standard deviations
- **results per activity band**, to check the sampling fix
- **global feature importance**

### 10.8 Step 8: save

- `artifacts/model.joblib`:
  - the calibrated model
  - the inner tree model and 200 background rows, for SHAP
  - the feature list and thresholds
  - the median feature values of training controls, shown as "typical control wallet" in explanations
  - the version, a UTC timestamp such as `20261108-0118`
- `artifacts/metrics.json`: every number shown on the Model page.

---

## 11. How a wallet gets scored and explained

File: `backend/app/scoring.py`, function `score_wallet`.

1. **Contract check:** if the address is a smart contract, no score is given ("not applicable"), because the model only learned wallets.
2. **Minimum history:** fewer than 3 items gives "insufficient history" and no score.
3. **Model check:** if no model file exists, the result says "model missing". This is what the yellow banner on the frontend is about.
4. **Features:** the same `extract_features` used in training.
5. **Score:** the calibrated probability from the model. For display, it is limited to **1–99%**, because the coarse calibration steps can reach exactly 0 or 1 and neither means certainty.
6. **Level:** low, medium or high from the thresholds in section 10.6.
7. **Reasons:** SHAP `TreeExplainer` computes how much each feature pushed this wallet's score up or down compared with the background set. The six largest are shown with:
   - the plain-language feature name
   - this wallet's value, in real units ("20.8 hours", "1,555 days", "0.804 ETH")
   - the typical value for a control wallet
   - whether it pushes risk up or down

Example from the app, for a wallet with a high score:

> **Share of counterparties that only send funds in.** This wallet: 93% · Typical control wallet: 33% · Pushes risk up

These reasons explain the *model*, not the *person*. Every reason can have an innocent cause, and the app says so.

---

## 12. How funds are traced to exchanges

File: `backend/app/tracer.py`. Settings in `config.py`.

### 12.1 The algorithm (breadth-first search)

Start at the suspect wallet (hop 0). At each hop, for every address in the current frontier:

1. **Read its history** (all addresses at the same hop are fetched at once).
2. **Stop at busy unknown addresses:** an unlabelled address with 200 or more transactions or token transfers is probably a service (an unlabelled exchange, a payment processor). It is marked "high activity" and not followed, because following it would spread into thousands of unrelated wallets.
3. **Collect outgoing transfers** that:
   - happened **after** the money arrived at this address (time order). At the start, this is the victim's payment time if a transaction hash was given.
   - **succeeded** and moved value
   - are ETH, or one of six **tracked tokens identified by contract address**: USDT, USDC, DAI, WETH, WBTC and BUSD. Matching by contract, not by symbol, stops fake tokens named "USDT" from creating false trails.
   - are above a **dust floor** (0.001 ETH, or 1 USDT/USDC/DAI/BUSD, or 0.0001 WBTC). This ignores tiny "address poisoning" transfers scammers send to confuse people.
4. **Same asset along a route:** after the first hop, a route follows only the asset that arrived. ETH stays ETH. A swap to another asset ends that path.
5. **Group** transfers per destination and asset, and follow the **3 largest** (`TRACE_TOP_K`).
6. For each destination:
   - **A known exchange:** record a hit (exchange name, wallet, hops, asset, amount, route) and stop that path.
   - **Another known service** (DEX, bridge or mixer): record it as an end point and stop.
   - **An ordinary wallet:** add it to the next hop's frontier, unless the hop limit (4) or the address limit (40) is reached.
7. **Deposit-address detection:** exchanges give each customer a personal deposit address, which forwards ("sweeps") almost everything to the exchange's main wallet. If an address made at least 2 outgoing transfers and **at least 90%** of them went to one exchange wallet, it is marked "Likely [exchange] deposit address". That is strong evidence the funds were credited to one customer account.

### 12.2 Amounts are upper bounds

An address can receive money from many sources. When the trace follows 10 ETH from a scammer to an exchange, the record shows that *up to* 10 ETH could have been the victim's money, not that it was. Route amounts are capped at the smallest amount along the route, and they are always labelled "Up to".

### 12.3 Confidence of an exchange link

A simple, transparent points rule, **not a probability**:

| Factor | Points |
|---|---|
| Closest route is 1 hop | 0.55 |
| Closest route is 2 hops | 0.45 |
| Closest route is 3 hops | 0.30 |
| Closest route is 4 or more hops | 0.20 |
| A deposit-address pattern was seen | + 0.20 |
| Share of the suspect's traced outflow (in that asset) that reached this exchange | + 0.25 × share |
| Maximum | 0.95 |

0.70 or more is **high**, 0.45–0.69 is **medium** and below 0.45 is **low**.

Example: one hop to HitBTC carrying 100% of the largest asset's outflow gives 0.55 + 0.25 = 0.80, which is **high**.

### 12.4 What the trace reports

- every node: suspect, wallets, exchanges and other services, deposit candidates, high-activity stops
- every edge, with asset, amount, transaction hash and time
- per exchange: confidence, minimum hops, amounts per asset (different assets are never added together), deposit addresses and the wallets reached
- **limits hit**, for example "had 12 destinations; followed the largest 3" or "address limit", so the reader knows what was *not* followed

---

## 13. How a victim report becomes a sealed case

File: `backend/app/pipeline.py`, function `run_case`.

1. **Intake** (`POST /api/cases`): the form is validated. The address must be `0x` plus 40 hex characters, and a transaction hash `0x` plus 64. A case ID such as `CASE-2369E613` is created, and a `case_created` audit entry is written. The victim's own reference number is **kept out** of the audit hash and the sealed report as personal data.
2. **Read** the suspect wallet's history.
3. **Score** it, in a background thread so other cases aren't blocked.
4. **List checks**, separate from the model:
   - Is the suspect on a fraud list?
   - How many of its counterparties are flagged?
   - Did it deal directly with a mixer?
5. **Start time:** if the victim gave their transaction hash, the trace only follows money that moved after that payment. If that transaction doesn't pay the suspect wallet, the report carries a note asking for the details to be checked.
6. **Trace** funds forward, streaming every new node and edge to the browser as it is found.
7. **Review priority:**
   - It starts at the model's level.
   - The suspect being on a fraud list makes it **high**.
   - A mixer contact or flagged counterparties raise it to at least **medium**.
   - Each reason is listed.
8. **Seal:** the full report (wallet, incident, risk, reasons, list checks, trace and disclaimer) is converted to canonical JSON. That JSON is hashed with SHA-256, and the hash goes into a `report_sealed` audit entry.
9. **Stream events:** the browser receives live updates over Server-Sent Events: `status`, `risk`, `node`, `edge`, `exchange` and finally `complete` or `failed`. A viewer who opens the page late still receives every event from the start.
10. **Human review:** an analyst sets the case to open, escalated, dismissed or resolved, with a note. Each change is written to the audit log (`review_updated`).

---

## 14. The tamper-evident audit log

File: `backend/app/store.py`.

Each audit entry stores:

- `seq`: a running number
- `ts`: the time
- `case_id`
- `event`: `case_created`, `report_sealed`, `review_updated` or `case_failed`
- `payload_hash`: the SHA-256 of the event's content (for `report_sealed`, the report's hash)
- `prev_hash`: the previous entry's hash. The very first entry uses 64 zeros.
- `entry_hash`: SHA-256 of `[seq, ts, case_id, event, payload_hash, prev_hash]`

Because every entry includes the previous entry's hash, changing any entry breaks every link after it, like a blockchain.

**Verify integrity** (`GET /api/audit/verify`, and the button on the Audit log page) recomputes the whole chain and checks every stored report against its sealed hash. It reports:

- missing entries
- broken links
- entries whose content doesn't match their hash
- reports edited after sealing

We tested this by editing a stored report in the database (changing "HitBTC" to "Kraken"). Verification reported "stored report does not match the sealed hash". After restoring the original, it reported the chain as valid again.

What it does **not** do: prove the report is *correct*. It proves the report hasn't been *changed* since it was sealed. Also, the chain is stored locally. Anchoring the head hash on a public testnet would make it tamper-evident even against the database owner. That was optional in the review and is not implemented.

---

## 15. The user interface, page by page

Top bar on every page: **Cases**, **Wallet check**, **Model**, **Audit log** and the **New report** button.

- A **red banner** appears if the backend is down.
- A **yellow banner** appears if no trained model exists.
- The footer repeats that output is a risk indication, not proof.

| Page | Address | What it shows |
|---|---|---|
| **Cases** | `/` | All cases, newest first: ID, address, status, review priority, score, exchanges reached, review status |
| **New report** | `/new` | The victim form. Suspect address (required); transaction hash, amount lost, incident date, what happened and your reference (all optional). Warns users never to share passwords or seed phrases. |
| **Case detail** | `/cases/CASE-…` | See the list below |
| **Wallet check** | `/wallet` | Quick score for one address, with no case, no trace and nothing stored |
| **Model** | `/model` | See the list below |
| **Audit log** | `/audit` | The audit entries with their hashes, and the **Verify integrity** button |

The **Case detail** page shows, from top to bottom:

1. The exchanges reached, each with:
   - its confidence
   - an upper-bound amount
   - hops and outflow share
   - the exchange wallet
   - route evidence
   - "what to do next" guidance (India: cybercrime.gov.in or helpline 1930)
2. The **money-flow diagram**, which builds live, with a table view.
3. The score, level and six reasons.
4. Public list checks.
5. Why this priority was given.
6. Analyst review.
7. The victim's report.
8. The sealed report hash and model version.
9. **Print report** and **Download JSON**.

The **Model page** shows:

- headline numbers and the bias warnings
- results by activity band
- the precision–recall chart with the medium and high cut-offs marked
- the confusion matrix
- triage levels on the test set
- the comparison of all 8 models
- feature importance
- precision at assumed real-world fraud rates
- the cut-off comparison
- the error review
- the dataset record

The layout works on phone screens (no sideways scrolling), supports light and dark mode, and has a print layout for the case report.

---

## 16. The backend API

Interactive documentation is available at **http://127.0.0.1:8000/docs** while the backend runs, so you can try every endpoint there.

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Status, whether a model is loaded, its version, label counts |
| POST | `/api/cases` | Create a case from a victim report and start the analysis. Returns `{"id": "CASE-…"}`. |
| GET | `/api/cases` | List all cases with summaries |
| GET | `/api/cases/{id}` | Full case: report, sealed hash, audit entries |
| GET | `/api/cases/{id}/events` | Live progress stream (Server-Sent Events) |
| PATCH | `/api/cases/{id}` | Record an analyst decision: `open`, `escalated`, `dismissed` or `resolved`, plus a note |
| GET | `/api/wallets/{address}/risk` | Score one wallet without creating a case |
| GET | `/api/model/metrics` | Everything in `artifacts/metrics.json` |
| GET | `/api/audit` | The latest 200 audit entries |
| GET | `/api/audit/verify` | Recompute the chain and check sealed reports |

Example: create a case from PowerShell.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/cases -ContentType "application/json" -Body '{"address":"0xf985aa8117999fa3f0f9e71a20d0fe7b88b9d706","description":"Test report"}'
```

---

## 17. How to collect data and retrain the model

**You usually don't need to.** The dataset and trained model are included. Retrain only if you change features, models or the data.

### 17.1 Retrain on the existing data (under a minute)

From the project root:

```powershell
backend\.venv\Scripts\python.exe ml\train.py
```

You will see each model's validation results, the selected model, the final test results and the top features. The new `artifacts/model.joblib` and `artifacts/metrics.json` replace the old ones, and the running backend switches to the new model automatically. Refresh the Model page to see the new numbers.

To keep the previous model, copy `artifacts\model.joblib` and `artifacts\metrics.json` somewhere first.

### 17.2 Collect more data, or continue an unfinished collection

```powershell
backend\.venv\Scripts\python.exe ml\collect_dataset.py --positives 300 --controls-per-positive 2
```

| Option | Meaning | Default |
|---|---|---|
| `--positives` | Target number of flagged wallets | 800 |
| `--controls-per-positive` | Matched controls per flagged wallet | 2 |
| `--seed` | Random seed for sampling | 42 |

Running it again with the same numbers **retries the 151 unfilled control slots**.

To grow the dataset, raise `--positives`, for example to 600. Expect several hours: finding wallets in the quiet activity bands takes many screening requests, at about 2.6 requests per second.

To run collection and then training in one go, logging to files:

```powershell
backend\.venv\Scripts\python.exe -u ml\collect_dataset.py --positives 300 --controls-per-positive 2 *> data\raw\collect.log; backend\.venv\Scripts\python.exe -u ml\train.py *> data\raw\train.log
```

Watch progress in another window:

```powershell
Get-Content data\raw\collect.log -Wait
```

**Before a long run:**

- Keep the computer **plugged in and awake**. Windows Settings → System → Power & battery → Screen and sleep → set sleep to "Never" while collecting. Sleep pauses collection; it resumes on wake.
- Using the app while collecting is fine, but both share the API's rate limit, so each slows the other a little.

### 17.3 Start a completely fresh dataset

Move the current dataset aside instead of deleting it:

```powershell
Rename-Item data\raw\wallets.jsonl.gz wallets_old.jsonl.gz
backend\.venv\Scripts\python.exe ml\collect_dataset.py --positives 300 --controls-per-positive 2
backend\.venv\Scripts\python.exe ml\train.py
```

Results will differ somewhat from ours, because the blockchain keeps growing and sampling is random within each time window.

### 17.4 If you change the features

1. Edit `backend/app/features.py`. Training and scoring both use it.
2. Run the tests (section 22).
3. Retrain with `ml\train.py`. No recollection is needed, because the dataset stores full histories and features are recomputed from them.

---

## 18. Results

Model version **20261108-0118**, Gradient Boosting + SMOTE, activity-matched dataset. All figures are on the **held-out test set** (the newest 122 wallets) at the alert cut-off chosen on validation data (0.409).

### 18.1 Headline

| Measure | Value | Meaning |
|---|---|---|
| Precision | 68% | Of wallets alerted, 68% were flagged ones |
| Recall | 70% | Of flagged wallets, 70% were alerted |
| F1 | 0.688 | Balance of precision and recall |
| Accuracy | 76% | Overall correct, less informative with imbalanced classes |
| PR-AUC (calibrated) | 0.674 | Ranking quality across all cut-offs; the baseline for random guessing is 0.38 here |
| PR-AUC (before calibration) | 0.719 | Same, without calibration's coarse steps |
| ROC-AUC (calibrated) | 0.779 | |
| False-alert rate | 20% | Share of controls wrongly alerted |
| Confusion matrix | 32 correctly alerted, 14 missed, 15 false alerts, 61 correctly passed | |

### 18.2 All eight models

| Model | Val PR-AUC | Test PR-AUC | Precision | Recall | F1 | False alerts |
|---|---:|---:|---:|---:|---:|---:|
| **Gradient Boosting + SMOTE** (selected) | 0.739 | 0.719 | 68% | 70% | 0.688 | 15 |
| Gradient Boosting | 0.735 | 0.718 | 61% | 72% | 0.660 | 21 |
| Random Forest + SMOTE | 0.717 | 0.725 | 72% | 57% | 0.634 | 10 |
| Random Forest | 0.693 | 0.666 | 71% | 54% | 0.617 | 10 |
| K-Nearest Neighbors + SMOTE | 0.626 | 0.649 | 67% | 43% | 0.526 | 10 |
| K-Nearest Neighbors | 0.624 | 0.667 | 62% | 52% | 0.565 | 15 |
| Decision Tree + SMOTE | 0.521 | 0.568 | 49% | 83% | 0.613 | 40 |
| Decision Tree | 0.515 | 0.518 | 46% | 41% | 0.437 | 22 |

The ensembles (Gradient Boosting, Random Forest) clearly beat single trees and KNN. The differences between the top models, and between with and without SMOTE, are too small on 122 test wallets to call one better.

### 18.3 Triage levels

| Level | Test wallets | Actually flagged | Share |
|---|---:|---:|---:|
| High | 7 | 6 | 86% |
| Medium | 40 | 26 | 65% |
| Low | 75 | 14 | 19% |

"Low" does not mean safe: 14 of 46 flagged test wallets landed there.

### 18.4 By activity band

| Activity | Flagged in data | Controls in data | Test false alerts | Test flagged caught |
|---|---:|---:|---:|---:|
| 3–9 items | 91 | 108 | 2 of 11 | 5 of 11 |
| 10–29 items | 72 | 84 | 2 of 19 | 6 of 12 |
| 30–99 items | 67 | 117 | 3 of 24 | 10 of 12 |
| 100–299 items | 58 | 116 | 5 of 14 | 7 of 7 |
| 300+ items | 13 | 26 | 3 of 8 | 4 of 4 |

The model misses more quiet flagged wallets and gives more false alerts on busy ones. Groups are small, so treat these figures as rough.

### 18.5 Precision if fraud is rare

The test set is 38% flagged. Real traffic has far less fraud. Holding recall and false-alert rate at their test values:

| Share of wallets that are fraudulent | Expected precision |
|---:|---:|
| 1% | 3.4% |
| 5% | 15.6% |
| 10% | 28.1% |

**This is the single most important number for a presentation.** In realistic conditions most alerts would be false, which is exactly why the system ranks wallets for a human instead of accusing anyone.

### 18.6 Other checks

- **Random split:** PR-AUC 0.830 against 0.719 chronological (before calibration). A random split overstates performance.
- **Cross-validation on the training period:** ROC-AUC 0.861 ± 0.023, so the model is stable across folds.
- **Most influential features:** history length (10%), delay before first outgoing payment (7%), share of counterparties that only pay in (6%), distinct addresses paying in (6%) and outgoing transactions (6%).

---

## 19. What we did and why: the project story

This is the order things happened in, useful for the report's methodology section and for the viva.

1. **Read the literature review.** It set the requirements: a documented Ethereum dataset; DT/RF/KNN/GB baselines; SMOTE on training data only after splitting; chronological and wallet-aware splits; full metrics with thresholds chosen on validation; calibrated triage with explanations; an error review; a tamper-evident record; and "risk indication, not proof" framing.
2. **Chose the data source.** Etherscan needs an API key, so we used Blockscout's free v2 API. Its old `/api` route was heavily throttled, so we used only v2, with our own rate limiter and retry logic.
3. **Built labels.** We combined four public fraud lists plus Etherscan name tags for exchanges. We found and fixed label traps: "take-action" tags mark victims, "blocked" is token-level, and some "exchange" names are actually token contracts or deployers.
4. **Designed features from live histories,** with one shared function for training and scoring, so they can never drift apart.
5. **Built the tracer and the case pipeline,** with live streaming, the deposit-address heuristic, spoof-resistant token matching, dust filtering and honest upper-bound amounts.
6. **Built the audit chain** and tested tamper detection by editing a stored report.
7. **Built the frontend:** case list, report form, live case page with the flow diagram, wallet check, model evaluation and audit log.
8. **First dataset and model (v1).** 301 flagged wallets and 602 controls taken straight from random blocks. Test precision 74%, recall 74%, PR-AUC 0.816 before calibration.
9. **Checked for leakage and bias, and found a real problem.** The top feature was "history exceeds the cap", and 55% of controls hit the cap against 10% of flagged wallets. Random-block sampling favours busy wallets, so the model had partly learned "quiet means suspicious". Among quiet test wallets, 30% of controls got false alerts.
10. **Quick fixes:**
    - removed the cap feature from the model
    - made medium start at the alert cut-off (it previously covered 81% of wallets)
    - capped displayed scores at 1–99%
    - added units to explanations
    - corrected an apples-to-oranges random-split comparison
11. **Proper fix: activity-matched controls (v2).** Each flagged wallet's controls must be in the same activity band. We screened over 17,000 candidate wallets with the cheap counter request to find matches. The rules were fixed before seeing the new results, and nothing was tuned afterwards.
12. **Result:**
    - Controls at the cap dropped from 55% to 23%.
    - The quiet-wallet false-alert rate dropped from 30% to 17%.
    - Validation and test now agree (0.739 against 0.719).
    - Headline numbers fell to precision 68% and recall 70%. That is **expected and more honest**: the first model's numbers were flattered by the sampling shortcut.

Both versions are kept (`*_v1_unmatched` files), so the before/after comparison can be shown:

| | v1, unmatched | v2, matched |
|---|---:|---:|
| Controls at history cap (flagged: 10%) | 55% | 23% |
| Top feature | Outgoing transactions, 25% | History length, 10% |
| Validation PR-AUC | 0.695 | 0.739 |
| Test PR-AUC, before calibration | 0.816 | 0.719 |
| Test precision / recall | 74% / 74% | 68% / 70% |
| False-alert rate, quiet test wallets | 30% | 17% |
| False-alert rate, busy test wallets | 2% | 29% |

---

## 20. Limitations to state honestly

1. **Matching is incomplete.** 151 control slots were unfilled, mostly quiet ones. Quiet bands have about 1.2 controls per flagged wallet against 2 in busy bands, so activity can still partly separate the classes.
2. **History after listing.** Histories include activity after a wallet was first seen. Flagged wallets may go quiet once listed while controls carry on, so "history length", the top feature, may partly reflect listing rather than behaviour beforehand. A cleaner design would cut each history at its listing date, but the lists don't record that date reliably.
3. **The test set has been looked at.** Changes were made after inspecting the first test results, so treat test figures as slightly optimistic.
4. **Small sample.** There are 46 flagged test wallets, so one wallet moves recall by about 2 points, and band results come from groups of 4–24.
5. **Labels are imperfect.** "Flagged" means *listed*, not proven. Controls may contain unreported fraud.
6. **Old data.** Test data ends in March 2023, because the lists are old snapshots. Newer scam patterns are unmeasured.
7. **Coarse calibration.** It uses 128 validation wallets. The high level is the top step, displayed as 99%, which is **not** a 99% chance of fraud.
8. **Exchange labels are incomplete.** A route to an exchange missing from the snapshot will not be identified. It may appear as a "high activity" stop instead.
9. **Trace amounts are upper bounds,** and confidence is a points rule, not a probability. Routes through a mule wallet and a deposit address are covered by offline tests, but were not seen on real data during testing.
10. **Scope.** Ethereum mainnet only; 200 items per history list; six tracked tokens. "Real time" means a live trace on demand, not continuous monitoring of the blockchain.
11. **Not implemented:** public testnet anchoring of the audit chain, federated learning and social-media signals.
12. **Collection gaps.** A few wallets failed to download after retries and were replaced. This may slightly under-represent very busy wallets.

---

## 21. How this meets the literature review's requirements

| Requirement | Done | Where |
|---|---|---|
| Documented Ethereum dataset and behavioural features | Yes | Sections 7–9, `metrics.json`, Model page |
| DT, RF, KNN, Gradient Boosting baselines | Yes, each with and without SMOTE | `ml/train.py`, Model page |
| Split before resampling; SMOTE on training data only | Yes | SMOTE inside the training pipeline |
| Chronological holdout and wallet-aware split | Yes | `chronological_split` |
| Precision, recall, F1, confusion matrix, false-alert counts, PR curve, threshold comparison | Yes | Model page |
| Threshold chosen on validation data | Yes | `best_f1_threshold`, `triage_thresholds` |
| Low/medium/high calibrated triage with feature-based explanations | Yes | Isotonic calibration, SHAP reasons |
| Error-review log | Yes | Error review on the Model page |
| Tamper-evident alert record | Yes, as a local SHA-256 chain (testnet anchoring optional, not done) | `store.py`, Audit log page |
| "Risk indication, not proof" framing | Yes | Every report, score and page footer |
| Record dataset version, labels, class distribution, split, parameters | Yes | `metrics.json`, Dataset record on the Model page |
| Victim-reported address to fraud-linked exchange (title 2) | Yes | Tracer, case pipeline, case page |

---

## 22. Testing

Run the 28 offline tests (no internet needed):

```powershell
cd backend
.venv\Scripts\python.exe -m pytest tests -q
```

Expected output: `28 passed`.

They use made-up wallet histories, so they never touch the internet. They cover:

- **Features:**
  - complete, finite values on an empty history
  - correct behaviour measurements
  - failed transfers moving no value
  - activity band edges
- **Labels:** exchange, mixer and other name tags are classified correctly, and look-alike names (tokens, deployers and so on) are not treated as exchange wallets.
- **Tracer:**
  - reaching an exchange through a mule wallet and a deposit address
  - ignoring transfers made before funds arrived
  - starting from the victim's payment time
  - not following spoofed tokens
  - keeping real tokens separate from ETH
  - keeping the same asset along a route
  - capping route amounts at the narrowest hop
  - ignoring dust and failed transfers
  - stopping at mixers
  - ending cycles
  - respecting the hop limit
  - not treating a single transfer as a deposit pattern
- **Audit chain:**
  - an intact chain verifies
  - an edited report is detected
  - an edited log entry is detected
  - a deleted log entry is detected

**Manual end-to-end check:** follow section 3.5.

---

## 23. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `running scripts is disabled on this system` | PowerShell execution policy | `powershell -ExecutionPolicy Bypass -File .\start.ps1` |
| `python` is not recognised | Python not installed or not on PATH | Reinstall Python 3.13 with "Add python.exe to PATH" ticked, then open a new terminal |
| `npm` is not recognised | Node.js not installed | Install Node.js 20 LTS, then open a new terminal |
| `pip install` fails building packages | Wrong Python version | Use Python 3.13. Delete `backend\.venv` and run `start.ps1` again. |
| Red banner: "backend is not responding on port 8000" | Backend not running, still starting, or crashed | Check the backend window for errors. The first start takes up to 30 seconds. |
| Yellow banner: "No trained model yet" | `artifacts/model.joblib` is missing | Copy the `artifacts` folder from a teammate, or run `ml\train.py` |
| `address already in use` / port 8000 or 5173 busy | Another copy is already running | Close the old server windows, or find the process: `Get-NetTCPConnection -LocalPort 8000` |
| Health shows 0 flagged addresses | `data/labels` missing | Copy it from the project, or run `ml\collect_dataset.py` once, which downloads missing lists |
| A case stays "running" for a long time | Large trace or slow API | Wait. Traces are limited to 4 hops and 40 addresses. Check the backend window for errors. |
| A case shows "Server restarted during analysis" | Backend stopped mid-case | Submit the report again |
| Errors mentioning HTTP 429 or ReadTimeout | Blockscout rate limit or slowness | Retries happen automatically. Avoid running two collectors at once. |
| Collection seems frozen | Computer went to sleep | It resumes on wake. Disable sleep for long runs. |
| Old cases have no score | They were created before a model existed | Submit them again |
| Audit verify reports problems | The database was edited by hand | This is the feature working. Restore the original `cases.sqlite3` |
| Want a clean case list | | Stop the backend and delete `data\cases.sqlite3` (and its `-shm`/`-wal` files). **This removes all cases and the audit log.** |

---

## 24. Ideas for future work

- **Cut histories at the listing date** to remove after-the-fact signals, using list sources that record when an address was reported.
- **Fill the remaining control slots** and grow the dataset (for example 800 flagged wallets) for tighter estimates.
- **Newer labels** (2024–2026 scam lists) to test on current scam patterns.
- **Anchor the audit chain's head hash on a public testnet** (for example Sepolia) for external tamper-evidence.
- **More chains** (BNB Smart Chain, Polygon, Tron), where many scams now operate.
- **Better exchange labels**, plus learning deposit-address patterns from data.
- **Continuous monitoring**: watch new blocks for transfers from known scam wallets.
- **Graph features**: counterparty network structure, which the review mentions as promising.

---

## 25. Glossary

| Term | Meaning |
|---|---|
| **Wallet / address** | An Ethereum account, written as `0x` plus 40 hexadecimal characters |
| **EOA** | Externally owned account: a wallet controlled by a private key, not a smart contract |
| **Smart contract** | Code deployed on the blockchain; it has an address but no owner key |
| **Transaction hash** | Unique ID of a transaction, `0x` plus 64 hexadecimal characters |
| **Internal transaction** | ETH moved by a smart contract, not directly by a wallet |
| **ERC-20 token** | A standard token type on Ethereum, such as USDT or USDC |
| **Wei / gwei** | Small units of ETH: 1 ETH = 10¹⁸ wei = 10⁹ gwei |
| **Gas** | The fee for running a transaction |
| **Hop** | One transfer step in a trace |
| **Deposit address** | A personal address an exchange gives each customer; it forwards funds to the exchange's main wallet |
| **Mixer** | A service (such as Tornado Cash) that pools funds to hide where they came from |
| **DEX** | Decentralised exchange, a smart contract for swapping tokens (no customer identity) |
| **Bridge** | A service that moves funds to another blockchain |
| **Flagged wallet** | A wallet on a public fraud list; label 1 in our data |
| **Control / comparison wallet** | A random wallet not on any list, matched on time and activity; label 0 |
| **Anchor time** | A flagged wallet's earliest seen activity, used to match controls in time |
| **Activity band** | Groups of wallets by how many history items they have (3–9, 10–29, 30–99, 100–299, 300+) |
| **SMOTE** | Creates synthetic examples of the smaller class to balance training data |
| **Chronological split** | Train on older data, test on newer data |
| **Precision** | Of the alerts raised, the share that were truly flagged |
| **Recall** | Of the truly flagged wallets, the share that were alerted |
| **F1** | The balance (harmonic mean) of precision and recall |
| **PR-AUC** | Area under the precision–recall curve; ranking quality, good for imbalanced data |
| **ROC-AUC** | Area under the ROC curve; chance a random flagged wallet scores above a random control |
| **Calibration** | Adjusting scores so they match observed rates |
| **Isotonic regression** | A calibration method that fits a step-shaped, increasing mapping |
| **SHAP** | A method that splits a prediction into each feature's contribution |
| **Hash / SHA-256** | A fixed-length fingerprint of data; any change gives a completely different hash |
| **Hash chain** | A list where each entry includes the previous entry's hash, so edits are detectable |
| **SSE** | Server-Sent Events: the server pushes updates to the browser over one connection |
| **Rate limit** | The maximum number of requests a server accepts per minute |
