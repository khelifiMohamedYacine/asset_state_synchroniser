"""Unit tests for create_databases.py."""
import sqlite3

import pytest

import create_databases


@pytest.fixture
def fresh_database_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(create_databases, "DATABASE_DIR", tmp_path)
    return tmp_path


def table_names(db_path):
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    names = {row[0] for row in cursor.fetchall()}
    connection.close()
    return names


def column_names(db_path, table):
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    names = [row[1] for row in cursor.fetchall()]
    connection.close()
    return names


def test_create_location_database_creates_expected_table(fresh_database_dir):
    create_databases.create_location_database()

    db_path = fresh_database_dir / "Location.db"
    assert db_path.exists()
    assert "asset_locations" in table_names(db_path)
    assert column_names(db_path, "asset_locations") == [
        "asset_id", "location", "latitude", "longitude",
        "status", "last_seen", "updated_at",
    ]


def test_create_maintenance_database_creates_expected_tables(fresh_database_dir):
    create_databases.create_maintenance_database()

    db_path = fresh_database_dir / "Maintenance.db"
    assert db_path.exists()
    names = table_names(db_path)
    assert "assets" in names
    assert "maintenance_records" in names
    assert column_names(db_path, "assets") == [
        "asset_id", "asset_name", "asset_type", "serial_number",
        "condition", "status", "updated_at",
    ]


def test_create_inventory_database_creates_expected_tables(fresh_database_dir):
    create_databases.create_inventory_database()

    db_path = fresh_database_dir / "Inventory.db"
    assert db_path.exists()
    names = table_names(db_path)
    assert "assets" in names
    assert "inventory_movements" in names
    assert column_names(db_path, "assets") == [
        "asset_id", "asset_name", "asset_type", "serial_number",
        "quantity", "availability", "updated_at",
    ]


def test_create_functions_are_idempotent(fresh_database_dir):
    create_databases.create_location_database()
    create_databases.create_location_database()  # must not raise

    db_path = fresh_database_dir / "Location.db"
    assert table_names(db_path) == {"asset_locations"}
