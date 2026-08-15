# Asset State Synchroniser

Reconciles asset records that are split across three independent "systems of
record" — a location tracker, a maintenance system, and an inventory system —
into a single authoritative state per asset, using a fixed field-authority
model plus an LLM-generated explanation of each decision.

## How it works

```
Location API (8001)  ─┐
Maintenance API (8002)─┼─► synchroniser.py ─► agent.py ─► state.db + decision_log.json
Inventory API (8003) ─┘
```

1. **Three mock source APIs** (`API/location_api.py`, `maintenance_api.py`,
   `inventory_api.py`) are small FastAPI apps, each backed by its own SQLite
   database in `Database/`. They stand in for real external systems.
2. **`synchroniser.py`** polls all three APIs, joins their records by
   `asset_id`, and hashes each combined record. If the hash matches what was
   stored for that asset last run (in `state.db`), the asset is skipped
   (unchanged). Otherwise it's sent to the agent.
3. **`agent.py`** (`AssetReconciliationAgent`) does the actual reconciliation
   in plain deterministic Python, using a fixed `FIELD_AUTHORITY` map (e.g.
   `location` is only ever taken from the location source, `condition` only
   from maintenance, `quantity` only from inventory). Based on the result it
   decides:
   - `accept` — all sources agreed
   - `merge` — sources disagreed, but the authoritative source resolved it
   - `flag` — sources disagreed and the authoritative source had no value,
     so it can't be resolved automatically
   The LLM (Qwen3-235B, called via Hugging Face's `deepinfra` inference
   provider) is used **only** to turn that already-computed decision into a
   human-readable paragraph — it never influences the decision itself. If the
   model call fails, a deterministic fallback explanation is used instead and
   the failure is recorded as a `model_error`, not a reconciliation problem.
4. Every processed asset's decision is appended to **`decision_log.json`**
   (a full audit trail), and its latest hash/decision/state is upserted into
   **`state.db`** so the next run can skip it if nothing changed.

## Requirements

- Python 3.10+
- A free [Hugging Face](https://huggingface.co/settings/tokens) API token
  with inference access (for the explanation step)

## Setup

```powershell
# from the project root
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install python-dotenv huggingface_hub   # see "Known gaps" below
```

Create/verify `.env` in the project root:

```
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> `.env` is git-ignored and is never committed to this repo. The value
> above is a placeholder — put your own Hugging Face token in your local
> `.env`.

## Running it

**1. Create and seed the three source databases** (one-time, or whenever you
want to reset the sample data):

```powershell
python create_databases.py
python populate_databases.py
```

**2. Start the three source APIs**, each in its own terminal:

```powershell
uvicorn API.location_api:app --port 8001
uvicorn API.maintenance_api:app --port 8002
uvicorn API.inventory_api:app --port 8003
```

**3. Run the synchroniser** (in a fourth terminal, from the project root):

```powershell
python synchroniser.py
```

This prints a run summary to the console, writes/updates `state.db`, and
appends new decisions to `decision_log.json`. Run it again immediately and
you'll see every asset reported as `UNCHANGED / SKIPPED` — change a row in
one of the `Database/*.db` files (or re-run `populate_databases.py` with
different data) to see reconciliation happen again.

## Running the tests

Unit tests live in `tests/` (one file per source module) and run against
temporary SQLite databases and mocked HTTP/LLM calls — they never touch the
real `Database/*.db`, `state.db`, or `decision_log.json`, and don't need a
Hugging Face token or the APIs running.

```powershell
pip install pytest
pytest
```

`pytest.ini` sets `testpaths = tests` and adds the project root to
`sys.path`, so `pytest` can be run from the project root with no other
setup.

## Known gaps / things to fix with more time

- **`requirements.txt` is incomplete and partly wrong.** `agent.py` imports
  `python-dotenv` and `huggingface_hub`, but neither is listed. Conversely,
  `transformers`, `torch`, and `accelerate` are listed but nothing in the
  code actually uses them (the LLM call goes through the HF *Inference API*,
  not a local model) — they just make `pip install` slow and heavy. This
  needs a proper audit, and `pytest` (used by the test suite in `tests/`)
  should move into a `requirements-dev.txt` split.
- **Filename casing mismatch.** `create_databases.py` and the API modules
  use `Location.db` / `Maintenance.db` / `Inventory.db`, but
  `populate_databases.py` writes to lowercase `location.db` /
  `maintenance.db` / `inventory.db`. This only works today because Windows
  filesystems are case-insensitive — it will silently create *duplicate*,
  unpopulated databases on Linux/macOS or in a case-sensitive container.
  Should be a single shared constant.
- **Secret hygiene.** `.env` is excluded via `.gitignore` and was never
  committed. If a real token was ever pasted into a terminal, chat, or
  shared elsewhere, rotate it as a precaution — Hugging Face tokens are
  free to regenerate.
- **No process orchestration.** Today you need four manual terminals. A
  `docker-compose.yml` (one container per API + one for the synchroniser) or
  even a simple `honcho`/`Procfile` / PowerShell launcher script would remove
  the manual setup friction.
- **No scheduling.** `synchroniser.py` is run-once; there's no loop, cron,
  or `--watch` mode. For a real sync tool this would run on an interval or
  be triggered by webhooks from the source systems.
- **`flag`ged conflicts go nowhere.** They're recorded in `decision_log.json`
  but nothing surfaces them for human review (no CLI report, dashboard, or
  notification). A `python synchroniser.py --report-flags` command or a
  small read-only web view over `decision_log.json` would close the loop.
- **No retry/backoff on the API calls or the LLM call.** A transient network
  blip on any of the three source APIs currently aborts the whole run
  (`response.raise_for_status()` with no retry); the LLM call has a single
  attempt with no retry either (a failure just falls back to the
  deterministic explanation, which is fine, but a transient error shouldn't
  need to fall back at all).
- **`state.db` and `decision_log.json` have no rotation/size cap.** Fine for
  a demo with 5 assets; would need addressing (e.g. log rotation, or moving
  the decision log into the same SQLite database) before running against a
  real, continuously-changing asset fleet.
