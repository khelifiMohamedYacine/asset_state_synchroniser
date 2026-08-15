"""Unit tests for API/maintenance_api.py."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from API import maintenance_api


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "Maintenance.db"
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE assets (
            asset_id INTEGER PRIMARY KEY,
            asset_name VARCHAR(100) NOT NULL,
            asset_type VARCHAR(50) NOT NULL,
            serial_number VARCHAR(100) UNIQUE NOT NULL,
            condition VARCHAR(30),
            status VARCHAR(30),
            updated_at DATETIME NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE maintenance_records (
            maintenance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            maintenance_type VARCHAR(50) NOT NULL,
            description TEXT,
            service_date DATE,
            next_service_date DATE,
            technician VARCHAR(100),
            created_at DATETIME NOT NULL
        )
    """)
    cursor.execute("""
        INSERT INTO assets
        (asset_id, asset_name, asset_type, serial_number, condition, status, updated_at)
        VALUES (1001, 'Generator G1', 'Generator', 'GEN-001', 'good', 'operational',
                '2026-08-12 11:00:00')
    """)
    cursor.execute("""
        INSERT INTO maintenance_records
        (asset_id, maintenance_type, description, service_date, next_service_date, technician, created_at)
        VALUES (1001, 'inspection', 'Routine inspection.', '2026-07-30', '2026-10-30',
                'John Smith', '2026-07-30 14:00:00')
    """)
    connection.commit()
    connection.close()

    monkeypatch.setattr(maintenance_api, "DATABASE_PATH", db_path)
    return TestClient(maintenance_api.app)


def test_get_assets_returns_all_rows(client):
    response = client.get("/assets")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["asset_id"] == 1001
    assert body[0]["condition"] == "good"


def test_get_asset_includes_maintenance_records(client):
    response = client.get("/assets/1001")

    assert response.status_code == 200
    body = response.json()
    assert body["asset_id"] == 1001
    assert len(body["maintenance_records"]) == 1
    assert body["maintenance_records"][0]["technician"] == "John Smith"


def test_get_asset_returns_404_for_unknown_id(client):
    response = client.get("/assets/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Asset 9999 not found"
