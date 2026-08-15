"""Unit tests for synchroniser.py."""
import json
import sqlite3

import pytest
import requests

import synchroniser


# --- Path fixtures: never touch the real state.db / decision_log.json ------

@pytest.fixture
def state_db_path(tmp_path, monkeypatch):
    path = tmp_path / "state.db"
    monkeypatch.setattr(synchroniser, "STATE_DATABASE", path)
    return path


@pytest.fixture
def decision_log_path(tmp_path, monkeypatch):
    path = tmp_path / "decision_log.json"
    monkeypatch.setattr(synchroniser, "DECISION_LOG", path)
    return path


# --- calculate_hash ----------------------------------------------------------

def test_calculate_hash_is_deterministic_regardless_of_key_order():
    a = {"asset_id": 1, "location_source": {"a": 1, "b": 2}}
    b = {"location_source": {"b": 2, "a": 1}, "asset_id": 1}
    assert synchroniser.calculate_hash(a) == synchroniser.calculate_hash(b)


def test_calculate_hash_differs_for_different_data():
    a = {"asset_id": 1, "location_source": {"status": "operational"}}
    b = {"asset_id": 1, "location_source": {"status": "under_repair"}}
    assert synchroniser.calculate_hash(a) != synchroniser.calculate_hash(b)


# --- build_asset_records -----------------------------------------------------

def test_build_asset_records_joins_by_asset_id():
    location = [{"asset_id": 1001, "location": "Site Alpha"}]
    maintenance = [{"asset_id": 1001, "condition": "good"}]
    inventory = [{"asset_id": 1001, "quantity": 1}]

    records = synchroniser.build_asset_records(location, maintenance, inventory)

    assert len(records) == 1
    assert records[0] == {
        "asset_id": 1001,
        "location_source": {"asset_id": 1001, "location": "Site Alpha"},
        "maintenance_source": {"asset_id": 1001, "condition": "good"},
        "inventory_source": {"asset_id": 1001, "quantity": 1},
    }


def test_build_asset_records_handles_asset_missing_from_a_source():
    location = [{"asset_id": 1001}]
    maintenance = []
    inventory = [{"asset_id": 1001}]

    records = synchroniser.build_asset_records(location, maintenance, inventory)

    assert records[0]["maintenance_source"] is None
    assert records[0]["location_source"] is not None
    assert records[0]["inventory_source"] is not None


def test_build_asset_records_sorted_by_asset_id():
    location = [{"asset_id": 1003}, {"asset_id": 1001}]
    maintenance = [{"asset_id": 1002}]
    inventory = []

    records = synchroniser.build_asset_records(location, maintenance, inventory)

    assert [r["asset_id"] for r in records] == [1001, 1002, 1003]


# --- state database ------------------------------------------------------

def test_initialise_state_database_creates_table(state_db_path):
    synchroniser.initialise_state_database()

    connection = sqlite3.connect(state_db_path)
    cursor = connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processed_assets'")
    assert cursor.fetchone() is not None
    connection.close()


def test_initialise_state_database_is_idempotent(state_db_path):
    synchroniser.initialise_state_database()
    synchroniser.initialise_state_database()  # must not raise


def test_get_previous_hash_returns_none_when_absent(state_db_path):
    synchroniser.initialise_state_database()
    assert synchroniser.get_previous_hash(1001) is None


def test_save_and_get_processed_asset_roundtrip(state_db_path):
    synchroniser.initialise_state_database()
    synchroniser.save_processed_asset(1001, "hash-abc", "accept", {"status": "operational"})

    assert synchroniser.get_previous_hash(1001) == "hash-abc"


def test_save_processed_asset_upserts_on_conflict(state_db_path):
    synchroniser.initialise_state_database()
    synchroniser.save_processed_asset(1001, "hash-1", "accept", {"status": "operational"})
    synchroniser.save_processed_asset(1001, "hash-2", "merge", {"status": "under_repair"})

    connection = sqlite3.connect(state_db_path)
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM processed_assets")
    assert cursor.fetchone()[0] == 1
    connection.close()

    assert synchroniser.get_previous_hash(1001) == "hash-2"


# --- decision log ----------------------------------------------------------

def test_initialise_decision_log_creates_empty_list(decision_log_path):
    synchroniser.initialise_decision_log()

    with open(decision_log_path, "r", encoding="utf-8") as file:
        assert json.load(file) == []


def test_initialise_decision_log_does_not_overwrite_existing_file(decision_log_path):
    decision_log_path.write_text(json.dumps([{"asset_id": 1}]), encoding="utf-8")

    synchroniser.initialise_decision_log()

    with open(decision_log_path, "r", encoding="utf-8") as file:
        assert json.load(file) == [{"asset_id": 1}]


def test_save_decision_appends_and_stamps_logged_at(decision_log_path):
    synchroniser.initialise_decision_log()
    synchroniser.save_decision({"asset_id": 1001, "decision": "accept"})

    with open(decision_log_path, "r", encoding="utf-8") as file:
        decisions = json.load(file)

    assert len(decisions) == 1
    assert decisions[0]["asset_id"] == 1001
    assert "logged_at" in decisions[0]


def test_save_decision_appends_to_existing_entries(decision_log_path):
    synchroniser.initialise_decision_log()
    synchroniser.save_decision({"asset_id": 1001})
    synchroniser.save_decision({"asset_id": 1002})

    with open(decision_log_path, "r", encoding="utf-8") as file:
        decisions = json.load(file)

    assert [d["asset_id"] for d in decisions] == [1001, 1002]


# --- API client functions ---------------------------------------------------

class FakeResponse:
    def __init__(self, payload, status_error=None):
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    def json(self):
        return self._payload


def test_get_location_assets_calls_correct_url_and_returns_json(monkeypatch):
    captured = {}

    def fake_get(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return FakeResponse([{"asset_id": 1001}])

    monkeypatch.setattr(synchroniser.requests, "get", fake_get)

    result = synchroniser.get_location_assets()

    assert captured["url"] == "http://127.0.0.1:8001/assets"
    assert result == [{"asset_id": 1001}]


def test_get_maintenance_assets_calls_correct_url(monkeypatch):
    monkeypatch.setattr(
        synchroniser.requests, "get",
        lambda url, timeout: FakeResponse([], None) if url == "http://127.0.0.1:8002/assets" else None,
    )
    assert synchroniser.get_maintenance_assets() == []


def test_get_inventory_assets_calls_correct_url(monkeypatch):
    monkeypatch.setattr(
        synchroniser.requests, "get",
        lambda url, timeout: FakeResponse([], None) if url == "http://127.0.0.1:8003/assets" else None,
    )
    assert synchroniser.get_inventory_assets() == []


def test_get_location_assets_propagates_http_errors(monkeypatch):
    error = requests.exceptions.HTTPError("500 error")
    monkeypatch.setattr(
        synchroniser.requests, "get",
        lambda url, timeout: FakeResponse(None, status_error=error),
    )

    with pytest.raises(requests.exceptions.HTTPError):
        synchroniser.get_location_assets()


# --- synchronise() end-to-end with everything mocked -------------------------

class FakeAgent:
    def __init__(self, *args, **kwargs):
        pass

    def reconcile(self, asset_data):
        return {
            "asset_id": asset_data["asset_id"],
            "decision": "accept",
            "reasoning": "all agreed",
            "authoritative_record": {"asset_id": asset_data["asset_id"]},
            "conflicts": [],
            "model_status": "skipped",
        }


def test_synchronise_processes_new_assets_and_skips_unchanged(
    state_db_path, decision_log_path, monkeypatch
):
    location_assets = [{"asset_id": 1001, "location": "Site Alpha"}]
    maintenance_assets = [{"asset_id": 1001, "condition": "good"}]
    inventory_assets = [{"asset_id": 1001, "quantity": 1}]

    monkeypatch.setattr(synchroniser, "get_location_assets", lambda: location_assets)
    monkeypatch.setattr(synchroniser, "get_maintenance_assets", lambda: maintenance_assets)
    monkeypatch.setattr(synchroniser, "get_inventory_assets", lambda: inventory_assets)
    monkeypatch.setattr(synchroniser, "AssetReconciliationAgent", FakeAgent)

    synchroniser.synchronise()

    with open(decision_log_path, "r", encoding="utf-8") as file:
        decisions = json.load(file)
    assert len(decisions) == 1
    assert decisions[0]["asset_id"] == 1001

    # Second run with identical data should skip (no new decision logged).
    synchroniser.synchronise()

    with open(decision_log_path, "r", encoding="utf-8") as file:
        decisions_after_second_run = json.load(file)
    assert len(decisions_after_second_run) == 1


def test_synchronise_reprocesses_when_data_changes(
    state_db_path, decision_log_path, monkeypatch
):
    location_assets = [{"asset_id": 1001, "location": "Site Alpha"}]
    monkeypatch.setattr(synchroniser, "get_location_assets", lambda: location_assets)
    monkeypatch.setattr(synchroniser, "get_maintenance_assets", lambda: [])
    monkeypatch.setattr(synchroniser, "get_inventory_assets", lambda: [])
    monkeypatch.setattr(synchroniser, "AssetReconciliationAgent", FakeAgent)

    synchroniser.synchronise()

    # Change the location data so the hash changes.
    location_assets_changed = [{"asset_id": 1001, "location": "Site Beta"}]
    monkeypatch.setattr(synchroniser, "get_location_assets", lambda: location_assets_changed)

    synchroniser.synchronise()

    with open(decision_log_path, "r", encoding="utf-8") as file:
        decisions = json.load(file)
    assert len(decisions) == 2
