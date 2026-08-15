import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import requests

from agent import AssetReconciliationAgent

BASE_DIR = Path(__file__).parent
STATE_DATABASE = BASE_DIR / "state.db"
DECISION_LOG = BASE_DIR / "decision_log.json"

LOCATION_API = "http://127.0.0.1:8001"
MAINTENANCE_API = "http://127.0.0.1:8002"
INVENTORY_API = "http://127.0.0.1:8003"


def initialise_state_database():
    """Create the persistent state database if it doesn't already exist."""
    connection = sqlite3.connect(STATE_DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_assets (
            asset_id INTEGER PRIMARY KEY,
            data_hash TEXT NOT NULL,
            processed_at TEXT NOT NULL,
            decision TEXT NOT NULL,
            authoritative_state TEXT NOT NULL
        )
    """)

    connection.commit()
    connection.close()


def initialise_decision_log():
    """Create the decision log file if it doesn't already exist."""
    if not DECISION_LOG.exists():
        with open(DECISION_LOG, "w", encoding="utf-8") as file:
            json.dump([], file, indent=4)


def save_decision(decision):
    """Append an agent decision to the persistent decision log."""
    with open(DECISION_LOG, "r", encoding="utf-8") as file:
        decisions = json.load(file)

    decision["logged_at"] = datetime.now().isoformat()
    decisions.append(decision)

    with open(DECISION_LOG, "w", encoding="utf-8") as file:
        json.dump(decisions, file, indent=4)


# --- API clients -------------------------------------------------------

def get_location_assets():
    response = requests.get(f"{LOCATION_API}/assets", timeout=10)
    response.raise_for_status()
    return response.json()


def get_maintenance_assets():
    response = requests.get(f"{MAINTENANCE_API}/assets", timeout=10)
    response.raise_for_status()
    return response.json()


def get_inventory_assets():
    response = requests.get(f"{INVENTORY_API}/assets", timeout=10)
    response.raise_for_status()
    return response.json()


def build_asset_records(location_assets, maintenance_assets, inventory_assets):
    """Join the three APIs' records together by asset_id."""
    location_by_id = {a["asset_id"]: a for a in location_assets}
    maintenance_by_id = {a["asset_id"]: a for a in maintenance_assets}
    inventory_by_id = {a["asset_id"]: a for a in inventory_assets}

    asset_ids = set(location_by_id) | set(maintenance_by_id) | set(inventory_by_id)

    records = []
    for asset_id in sorted(asset_ids):
        records.append({
            "asset_id": asset_id,
            "location_source": location_by_id.get(asset_id),
            "maintenance_source": maintenance_by_id.get(asset_id),
            "inventory_source": inventory_by_id.get(asset_id),
        })

    return records


def calculate_hash(asset_data):
    """Deterministic hash of the source data, used to detect changes."""
    serialised = json.dumps(asset_data, sort_keys=True)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def get_previous_hash(asset_id):
    """Look up the hash stored for this asset on the previous run, if any."""
    connection = sqlite3.connect(STATE_DATABASE)
    cursor = connection.cursor()

    cursor.execute(
        "SELECT data_hash FROM processed_assets WHERE asset_id = ?",
        (asset_id,)
    )
    result = cursor.fetchone()
    connection.close()

    return result[0] if result else None


def save_processed_asset(asset_id, data_hash, decision, authoritative_state):
    """Upsert the latest reconciled state for an asset."""
    connection = sqlite3.connect(STATE_DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO processed_assets
        (asset_id, data_hash, processed_at, decision, authoritative_state)
        VALUES (?, ?, ?, ?, ?)
    """, (
        asset_id,
        data_hash,
        datetime.now().isoformat(),
        decision,
        json.dumps(authoritative_state)
    ))

    connection.commit()
    connection.close()


def synchronise():
    print("=" * 60)
    print("ASSET STATE SYNCHRONISER")
    print("=" * 60)

    initialise_state_database()
    initialise_decision_log()

    print("\nQuerying source APIs...")
    location_assets = get_location_assets()
    maintenance_assets = get_maintenance_assets()
    inventory_assets = get_inventory_assets()

    print(f"Location API:    {len(location_assets)} assets")
    print(f"Maintenance API: {len(maintenance_assets)} assets")
    print(f"Inventory API:   {len(inventory_assets)} assets")

    assets = build_asset_records(location_assets, maintenance_assets, inventory_assets)
    print(f"\nTotal unique assets: {len(assets)}")

    agent = AssetReconciliationAgent()

    processed_count = 0
    skipped_count = 0

    for asset in assets:
        asset_id = asset["asset_id"]
        current_hash = calculate_hash(asset)
        previous_hash = get_previous_hash(asset_id)

        print("\n" + "-" * 60)
        print(f"Asset {asset_id}")

        # Nothing changed since last run - no need to re-reconcile.
        if previous_hash == current_hash:
            print("STATUS: UNCHANGED")
            print("ACTION: SKIPPED")
            skipped_count += 1
            continue

        print("STATUS: NEW" if previous_hash is None else "STATUS: CHANGED")
        print("ACTION: RECONCILING")

        decision = agent.reconcile(asset)
        print(f"DECISION: {decision.get('decision')}")
        print(f"REASONING: {decision.get('reasoning')}")

        authoritative_state = decision.get("authoritative_record", {})
        save_processed_asset(
            asset_id,
            current_hash,
            decision.get("decision", "flag"),
            authoritative_state
        )
        save_decision(decision)

        processed_count += 1

    print("\n" + "=" * 60)
    print("SYNCHRONISATION COMPLETE")
    print("=" * 60)
    print(f"Processed: {processed_count}")
    print(f"Skipped:   {skipped_count}")
    print(f"State DB:  {STATE_DATABASE}")
    print(f"Decision log: {DECISION_LOG}")


if __name__ == "__main__":
    synchronise()
