"""Unit tests for API/inventory_api.py."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from API import inventory_api


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "Inventory.db"
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE assets (
            asset_id INTEGER PRIMARY KEY,
            asset_name VARCHAR(100) NOT NULL,
            asset_type VARCHAR(50) NOT NULL,
            serial_number VARCHAR(100) UNIQUE NOT NULL,
            quantity INTEGER NOT NULL,
            availability VARCHAR(30),
            updated_at DATETIME NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE inventory_movements (
            movement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            movement_type VARCHAR(30) NOT NULL,
            quantity INTEGER NOT NULL,
            from_location VARCHAR(100),
            to_location VARCHAR(100),
            movement_time DATETIME NOT NULL
        )
    """)
    cursor.execute("""
        INSERT INTO assets
        (asset_id, asset_name, asset_type, serial_number, quantity, availability, updated_at)
        VALUES (1001, 'Generator G1', 'Generator', 'GEN-001', 1, 'available',
                '2026-08-12 12:00:00')
    """)
    cursor.execute("""
        INSERT INTO inventory_movements
        (asset_id, movement_type, quantity, from_location, to_location, movement_time)
        VALUES (1001, 'IN', 1, NULL, 'Site Alpha', '2026-07-01 09:00:00')
    """)
    connection.commit()
    connection.close()

    monkeypatch.setattr(inventory_api, "DATABASE_PATH", db_path)
    return TestClient(inventory_api.app)


def test_get_assets_returns_all_rows(client):
    response = client.get("/assets")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["asset_id"] == 1001
    assert body[0]["quantity"] == 1


def test_get_asset_includes_inventory_movements(client):
    response = client.get("/assets/1001")

    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == 1001
    assert len(body["inventory_movements"]) == 1
    assert body["inventory_movements"][0]["movement_type"] == "IN"


def test_get_asset_returns_404_for_unknown_id(client):
    response = client.get("/assets/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Asset 9999 not found"
