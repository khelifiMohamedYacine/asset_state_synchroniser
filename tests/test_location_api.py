"""Unit tests for API/location_api.py."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from API import location_api


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "Location.db"
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE asset_locations (
            asset_id INTEGER PRIMARY KEY,
            location VARCHAR(100) NOT NULL,
            latitude REAL,
            longitude REAL,
            status VARCHAR(30),
            last_seen DATETIME,
            updated_at DATETIME NOT NULL
        )
    """)
    cursor.execute("""
        INSERT INTO asset_locations
        (asset_id, location, latitude, longitude, status, last_seen, updated_at)
        VALUES (1001, 'Site Alpha', 51.5001, -0.1201, 'operational',
                '2026-08-12 10:00:00', '2026-08-12 10:00:00')
    """)
    connection.commit()
    connection.close()

    monkeypatch.setattr(location_api, "DATABASE_PATH", db_path)
    return TestClient(location_api.app)


def test_get_assets_returns_all_rows(client):
    response = client.get("/assets")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["asset_id"] == 1001
    assert body[0]["location"] == "Site Alpha"


def test_get_asset_returns_single_asset(client):
    response = client.get("/assets/1001")

    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == 1001
    assert body["status"] == "operational"


def test_get_asset_returns_404_for_unknown_id(client):
    response = client.get("/assets/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Asset 9999 not found"
