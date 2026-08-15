"""Unit tests for populate_databases.py."""
import sqlite3

import pytest

import create_databases
import populate_databases


@pytest.fixture
def seeded_schema_dir(tmp_path, monkeypatch):
    # populate_databases.py writes to lowercase filenames (location.db, ...)
    # while create_databases.py creates them capitalised (Location.db, ...);
    # both modules must point at the same directory so the schema created
    # here is the one populate_* inserts into (relies on a case-insensitive
    # filesystem, matching how the two scripts are actually run together).
    monkeypatch.setattr(create_databases, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(populate_databases, "DATABASE_DIR", tmp_path)

    create_databases.create_location_database()
    create_databases.create_maintenance_database()
    create_databases.create_inventory_database()

    return tmp_path


def row_count(db_path, table):
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    count = cursor.fetchone()[0]
    connection.close()
    return count


def test_populate_location_database_inserts_five_assets(seeded_schema_dir):
    populate_databases.populate_location_database()

    db_path = seeded_schema_dir / "location.db"
    assert row_count(db_path, "asset_locations") == 5


def test_populate_maintenance_database_inserts_assets_and_records(seeded_schema_dir):
    populate_databases.populate_maintenance_database()

    db_path = seeded_schema_dir / "maintenance.db"
    assert row_count(db_path, "assets") == 5
    assert row_count(db_path, "maintenance_records") == 5


def test_populate_inventory_database_inserts_assets_and_movements(seeded_schema_dir):
    populate_databases.populate_inventory_database()

    db_path = seeded_schema_dir / "inventory.db"
    assert row_count(db_path, "assets") == 5
    assert row_count(db_path, "inventory_movements") == 5


def test_populate_location_database_values(seeded_schema_dir):
    populate_databases.populate_location_database()

    db_path = seeded_schema_dir / "location.db"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM asset_locations WHERE asset_id = 1001")
    row = dict(cursor.fetchone())
    connection.close()

    assert row["location"] == "Site Alpha"
    assert row["status"] == "operational"


def test_populate_asset_id_is_primary_key_conflict_on_double_populate(seeded_schema_dir):
    populate_databases.populate_location_database()

    with pytest.raises(sqlite3.IntegrityError):
        populate_databases.populate_location_database()
